#!/bin/bash

# Exit on error
set -e

# Directories
QUERY_DIR="retrieval_config/queries"
QRELS_FILE="retrieval_config/qrels.txt"
QRELS_TREC_FILE="retrieval_config/qrels_trec.txt"
RESULTS_FILE="retrieval_config/results/results_sys2_trec_hybrid.txt"
TREC_EVAL_RESULTS="retrieval_config/results/trec_eval_results_sys2_hybrid.txt"
IMAGES_DIR="retrieval_config/results/images"

# Ensure output directories exist
mkdir -p "$(dirname "$QRELS_TREC_FILE")" "$IMAGES_DIR"

# Check if required directories exist
if [[ ! -d "$QUERY_DIR" ]]; then
    echo "Error: Query directory $QUERY_DIR does not exist"
    exit 1
fi

if [[ ! -f "$QRELS_FILE" ]]; then
    echo "Error: Qrels file $QRELS_FILE does not exist"
    exit 1
fi

# Initialize empty files
: > "$RESULTS_FILE"
: > "$TREC_EVAL_RESULTS"

# Convert qrels to TREC format (single file for all queries)
echo "Converting qrels to TREC format..."
if ! cat "$QRELS_FILE" | ./scripts/retrieval_eval/qrels2trec.py > "$QRELS_TREC_FILE"; then
    echo "Error: Failed to convert qrels to TREC format."
    exit 1
fi

# Process each sys2 query file
for query_file in "$QUERY_DIR"/*sys2.json; do
    # Check if any matching files were found
    if [[ ! -e "$query_file" ]]; then
        echo "Error: No sys2 query files found in $QUERY_DIR"
        exit 1
    fi

    # Extract the query identifier (e.g., "1" from "query1_sys2.json")
    base_name=$(basename "$query_file" "_sys2.json")
    query_id="${base_name//query/}"

    echo "Processing query file: $query_file"

    # Query Solr and append results in TREC format to the results file
    if ! ./scripts/semantic_search/query_embedding.py --query "$query_file" --uri http://localhost:8983/solr --collection tech_videos | \
        ./scripts/retrieval_eval/solr2trec.py "$query_id" --run-id "sys2" >> "$RESULTS_FILE"; then
        echo "Error: Failed to query Solr or convert results for $query_file"
        continue
    fi
done

# Run TREC evaluation
echo "Running TREC evaluation..."
if ! ./src/trec_eval/trec_eval -q "$QRELS_TREC_FILE" "$RESULTS_FILE" > "$TREC_EVAL_RESULTS"; then
    echo "Error: TREC evaluation failed."
    exit 1
fi

# Generate Precision-Recall plots
echo "Generating Precision-Recall plots..."
if ! cat "$RESULTS_FILE" | ./scripts/retrieval_eval/plot_pr.py --qrels "$QRELS_TREC_FILE" --output "$IMAGES_DIR/prec_rec_sys2_hybrid.png"; then
    echo "Error: Failed to generate precision-recall plot."
    exit 1
fi

echo "Processing completed successfully:"
echo "  - Results: $RESULTS_FILE"
echo "  - TREC Evaluation Results: $TREC_EVAL_RESULTS"
echo "  - Plot: $IMAGES_DIR/prec_rec_sys2.png"