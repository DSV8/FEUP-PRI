#!/usr/bin/env python3

import requests
import argparse
from pathlib import Path
import json
import sys
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')

def text_to_embedding(text):
    embedding = model.encode(text, convert_to_tensor=False).tolist()
    
    # Convert the embedding to the expected format
    embedding_str = "[" + ",".join(map(str, embedding)) + "]"
    return embedding_str

def solr_knn_query(endpoint, collection, embedding, rows):
    url = f"{endpoint}/{collection}/select"

    data = {
        "q": f"{{!knn f=vector topK={rows}}}{embedding}",
        "fl": "id,title,score",
        "rows": rows,
        "wt": "json",
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    response = requests.post(url, data=data, headers=headers)
    response.raise_for_status()
    return response.json()

def solr_query(endpoint, collection, query_text, defType, qf, rows):
    url = f"{endpoint}/{collection}/select"

    data = {
        "q": query_text,
        "defType": defType,
        "qf": qf,
        "fl": "id,title,score",
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
            }

    # Convert merged results to a list and sort by score
    merged_results_list = list(merged_results.values())
    merged_results_list.sort(key=lambda x: x["score"], reverse=True)

    # Reduce to the number of rows
    merged_results_list = merged_results_list[:rows]

    # Ensure the merged results are properly formatted as a JSON object
    merged_results_json = {
        "response": {
            "docs": merged_results_list
        }
    }
    
    return merged_results_json


def main(query_file, solr_endpoint, collection):
    try:
        query = json.load(open(query_file))
    except FileNotFoundError:
        print(f"Error: Query file {query_file} not found.")
        sys.exit(1)

    query_text = query.get('query', '*:*')
    params = query.get('params', {})
    defType = params.get('defType', 'edismax')
    rows = params.get('rows', 10)
    qf = params.get('qf', 'transcript^2 transcript_keywords transcript_entity_values title^2 description')
    embedding = text_to_embedding(query_text)

    try:
        semantic_results = solr_knn_query(solr_endpoint, collection, embedding, rows)
        lexical_results = solr_query(solr_endpoint, collection, query_text, defType, qf, rows)

        results = merge_results(semantic_results, lexical_results, rows)
        print(json.dumps(results, indent=2))
    except requests.HTTPError as e:
        print(f"Error {e.response.status_code}: {e.response.text}")

if __name__ == "__main__":
    # Set up argument parsing for the command-line interface
    parser = argparse.ArgumentParser(
        description="Fetch search results from Solr and output them in JSON format."
    )

    # Add arguments for query file, Solr URI, and collection name
    parser.add_argument(
        "--query",
        type=Path,
        required=True,
        help="Path to the JSON file containing the Solr query parameters.",
    )
    parser.add_argument(
        "--uri",
        type=str,
        default="http://localhost:8983/solr",
        help="The URI of the Solr instance (default: http://localhost:8983/solr).",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default="tech_videos",
        help="Name of the Solr collection to query (default: 'tech_videos').",
    )
    # Parse command-line arguments
    args = parser.parse_args()
    main(args.query, args.uri, args.collection)
