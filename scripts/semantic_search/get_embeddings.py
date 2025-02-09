#!/usr/bin/env python3
import json
import os
from sentence_transformers import SentenceTransformer

# Load the SentenceTransformer model
model = SentenceTransformer('all-MiniLM-L6-v2')

def get_embedding(text):
    # The model.encode() method already returns a list of floats
    return model.encode(text, convert_to_tensor=False).tolist()

def load_json(document):
    # Extract fields if they exist, otherwise default to empty strings
    title = document.get("title", "")
    channel = document.get("channel", "")
    upload_date = document.get("upload_date", "")
    description = document.get("description", "")
    transcript = document.get("transcript", "")
    category = document.get("category", "")
    tags = document.get("tags", "")

    combined_text = title + " " + channel + " " + category + " " + description + " " + transcript + " " + upload_date + " " + " ".join(tags)

    document["vector"] = get_embedding(combined_text)

    return document

if __name__ == "__main__":
    # Get the absolute path of the script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Define the input and output directories relative to the script directory
    file_path = '../../docker/data/video_collection'
    new_file_path = '../../docker/data/video_collection_semantic'

    # Print current working directory for debugging
    print("Current working directory:", os.getcwd())
    print("Input directory:", file_path)
    print("Output directory:", new_file_path)

    # Ensure the output directory exists
    os.makedirs(new_file_path, exist_ok=True)

    # Load multiple JSON files from the folder
    for filename in os.listdir(file_path):
        if filename.endswith('.json'):
            input_file = os.path.join(file_path, filename)
            output_file = os.path.join(new_file_path, filename)
            
            # Print file paths for debugging
            print("Processing file:", input_file)
            print("Output file:", output_file)

            with open(input_file, 'r', encoding='utf-8') as infile:
                document = json.load(infile)
                modified_document = load_json(document)

            with open(output_file, 'w', encoding='utf-8') as outfile:
                json.dump(modified_document, outfile, indent=4, ensure_ascii=False)
        
print("Processing complete.")
