from sentence_transformers import SentenceTransformer
from flask import Flask, request, jsonify
from flask_cors import CORS  # Import Flask-CORS
import requests, os, json

app = Flask(__name__)

# Enable CORS for all routes
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

LOG_FILE_PATH = "new_signals.json"

# Load existing counts from file
if os.path.exists(LOG_FILE_PATH):
    try:
        with open(LOG_FILE_PATH, 'r') as log_file:
            click_counts = json.load(log_file)
    except json.JSONDecodeError:
        click_counts = {}

# Endpoint to log clicked IDs
@app.route('/log_click', methods=['POST'])
def log_click():
    try:
        data = request.get_json()
        doc_id = data.get('id')
        if not doc_id:
            return jsonify({"error": "Invalid or missing document ID"}), 400
        
        # Update the count for the clicked ID
        if doc_id in click_counts:
            click_counts[doc_id] += 1
        else:
            click_counts[doc_id] = 1

        # Save the updated counts to the file
        with open(LOG_FILE_PATH, 'w') as log_file:
            json.dump(click_counts, log_file)

        print("Click counts:", click_counts)  # Debug log

        return jsonify({"message": "ID logged successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
# Fetch single document with id
@app.route('/fetch_document_by_id', methods=['POST'])
def fetch_document_by_id():
    """
    API endpoint to fetch a single Solr document by ID.
    Expected 'id' as a query parameter.
    """
    try:
        doc_id = request.get_json().get("id")
        if not doc_id:
            return jsonify({"error": "Invalid or missing document ID"}), 400
        
        # Construct Solr query
        query_params = {
            "q": f"id:{doc_id}",
            "fl": "id, title, description, transcript, channel, channel_id, upload_date, category, tags, views, likes, comments_count, description_links, transcript_keywords, transcript_entity_values, transcript_entity_types",
            "rows": 1
        }

        response = fetch_query(query_params)
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/fetch_documents', methods=['POST'])
def fetch_documents():
    """
    API endpoint to fetch Solr documents.
    Expects JSON payload with 'query' parameter.
    """
    try:
        data = request.get_json()
        print("Request data:", data)  # Debug log
        if not data or 'query' not in data:
            return jsonify({"error": "Invalid or missing query parameter"}), 400
        query = data.get("query", "*:*")  # Default to match all if no query

        # Query parameters for Solr
        query_params = {
            "q": query,
            "defType": "edismax",
            "qf": "transcript^2 transcript_keywords transcript_entity_values title^3 description",
            "fl": "id, score, title, channel",
            "rows": 30
        }

        # Debug log
        print("Solr request parameters:", query_params)

        # Call the function to fetch results from Solr
        response = fetch_query(query_params, semantic=True)

        return jsonify(response)    
    except requests.RequestException as e:
        return jsonify({"error": f"Error querying Solr: {e}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/fetch_video_details', methods=['POST'])
def fetch_video_details():
    """
    API endpoint to fetch details of a video.
    Expected 'id' as a query parameter.
    """
    try:
        data = request.get_json()
        print("Request data:", data)  # Debug log
        video_id = data.get("query", "*:*")  # Default to match all if no query
        print ("Query:", video_id)  # Debug log
        # Construct Solr query
        # Construct Solr query parameters
        query_params = {
            "q": f"id:{video_id}",
            "fl": "id, title, description, transcript, transcript_keywords, channel, channel_id, upload_date, category, tags, views, likes, comments_count, description_links",
            "rows": 1,  # Limit to 1 result
            "wt": "json"  # Response format
        }

        # Solr endpoint and collection
        solr_uri = "http://localhost:8983/solr"
        collection = "tech_videos"
        url = f"{solr_uri}/{collection}/select"

        # Send request to Solr
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        response = requests.post(url, data=query_params, headers=headers)
        response.raise_for_status()

        # Parse Solr response
        solr_response = response.json()
        video_docs = solr_response.get("response", {}).get("docs", [])

        # Return the first document or a 404 error if no document is found
        if not video_docs:
            return jsonify({"error": "Video not found"}), 404

        # Directly return the first document
        print("Video details:", video_docs[0])  # Debug log
        return jsonify(video_docs[0])
    except requests.RequestException as e:
        print(f"Solr request exception: {e}")
        return jsonify({"error": f"Solr request failed: {e}"}), 500
    except Exception as e:
        print(f"General exception: {e}")
        return jsonify({"error": str(e)}), 500


def text_to_embedding(text):
    model = SentenceTransformer('all-MiniLM-L6-v2')
    embedding = model.encode(text, convert_to_tensor=False).tolist()
    
    # Convert the embedding to the expected format
    embedding_str = "[" + ",".join(map(str, embedding)) + "]"
    return embedding_str

def solr_knn_query(endpoint, collection, embedding, rows, fl):
    url = f"{endpoint}/{collection}/select"

    data = {
        "q": f"{{!knn f=vector topK={rows}}}{embedding}",
        "fl": fl,
        "rows": rows,
        "wt": "json",
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    response = requests.post(url, data=data, headers=headers)
    response.raise_for_status()
    return response.json()

def solr_query(endpoint, collection, query_text, defType, qf, rows, fl):
    url = f"{endpoint}/{collection}/select"

    data = {
        "q": query_text,
        "defType": defType,
        "qf": qf,
        "fl": fl,
        "rows": rows,
        "wt": "json",
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    response = requests.post(url, data=data, headers=headers)
    response.raise_for_status()
    return response.json()

def merge_results(lexical_results, knn_results, rows, lexical_weight=0.9, semantic_weight=0.1):
    merged_results = {}

    # Debug log
    print("Merging results...")

    # Normalize lexical scores
    lexical_docs = lexical_results.get("response", {}).get("docs", [])
    max_lexical_score = max((doc["score"] for doc in lexical_docs), default=1)  # Avoid division by zero
    for doc in lexical_docs:
        doc["normalized_score"] = doc["score"] / max_lexical_score  # Scale to [0, 1]

    # Use semantic scores as-is (already in [0, 1])
    knn_docs = knn_results.get("response", {}).get("docs", [])
    for doc in knn_docs:
        doc["normalized_score"] = doc["score"]  # No further normalization needed

    # Merge and weight results
    for doc in lexical_docs:
        doc_id = doc["id"]
        merged_results[doc_id] = {
            "id": doc_id,
            "title": doc.get("title"),
            "score": lexical_weight * doc["normalized_score"],  # Weighted lexical score
            "channel": doc.get("channel")
        }

    for doc in knn_docs:
        doc_id = doc["id"]
        if doc_id in merged_results:
            merged_results[doc_id]["score"] += semantic_weight * doc["normalized_score"]  # Add weighted semantic score
        else:
            merged_results[doc_id] = {
                "id": doc_id,
                "title": doc.get("title"),
                "score": semantic_weight * doc["normalized_score"],  # Semantic score only
                "channel": doc.get("channel")
            }

    # Convert merged results to a list and sort by score
    merged_results_list = list(merged_results.values())

    # Add clicks to the score
    for doc in merged_results_list:
        doc_id = doc["id"]
        if doc_id in click_counts:
            doc["score"] += click_counts[doc_id] * 1  # Add 1 points per click    

    # Sort by score in descending order
    merged_results_list.sort(key=lambda x: x["score"], reverse=True)

    # Reduce to the number of rows
    merged_results_list = merged_results_list[:rows]

    # Ensure the merged results are properly formatted as a JSON object
    merged_results_json = {
        "response": {
            "docs": merged_results_list
        }
    }

    print(merged_results_json)
    return merged_results_json

def fetch_query(query_params, semantic=False):
    try:
        solr_uri = "http://localhost:8983/solr"  # Solr URI
        collection = "tech_videos"  # Solr collection name

        if(semantic):
            lexical_results = solr_query(solr_uri, collection, query_params["q"], query_params["defType"], query_params["qf"], query_params["rows"], query_params["fl"])
            embedding = text_to_embedding(query_params["q"])
            knn_results = solr_knn_query(solr_uri, collection, embedding, query_params["rows"], query_params["fl"])
            response = merge_results(lexical_results, knn_results, query_params["rows"])
        else:
            response = solr_query(solr_uri, collection, query_params["q"], "", "", query_params["rows"], query_params["fl"])
        
        return response
    except requests.RequestException as e:
        print("Solr request exception:", e)  # Debug log
        return jsonify({"error": f"Solr request failed: {e}"}), 500
    except ValueError as e:
        print("JSON decoding exception:", e)  # Debug log
        return jsonify({"error": f"Error parsing Solr response: {e}"}), 500
    except Exception as e:
        print("General exception:", e)  # Debug log
        return jsonify({"error": f"Server error: {e}"}), 500

if __name__ == "__main__":
    app.run(debug=True)
