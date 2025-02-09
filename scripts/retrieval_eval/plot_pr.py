#!/usr/bin/env python3
import argparse
import sys

import matplotlib
matplotlib.use('Agg')  # Use a non-interactive backend for plotting

import matplotlib.pyplot as plt
import numpy as np

def main(qrels_file: str, output_file: str):
    """
    Read predicted document IDs from stdin in TREC format and qrels (ground truth IDs) from a file,
    Plot average precision-recall curve over multiple queries and save it to a .PNG file.

    Arguments:
        qrels_file -- Path to the qrels file containing ground truth document IDs in TREC format.
        output_file -- Name of the output PNG file where the precision-recall curve will be saved.
    """

    # Read qrels (ground truth) and group by query ID
    qrels = {}
    with open(qrels_file, "r") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 4:
                continue
            query_id = parts[0]
            doc_id = parts[2]
            if query_id not in qrels:
                qrels[query_id] = set()
            qrels[query_id].add(doc_id)

    # Read predicted document IDs from stdin and group by query ID
    predictions = {}
    for line in sys.stdin:
        parts = line.strip().split()
        if len(parts) < 6:
            continue
        query_id = parts[0]
        doc_id = parts[2]
        if query_id not in predictions:
            predictions[query_id] = []
        predictions[query_id].append(doc_id)

    # Check for empty inputs
    if not predictions or not qrels:
        print("Error: No predictions or qrels found. Please provide valid input.")
        sys.exit(1)

    per_query_precisions = {}
    per_query_recalls = {}
    average_precisions = []

    for query_id in qrels:
        y_true = qrels[query_id]
        y_pred = predictions.get(query_id, [])
        
        # Skip queries with no predictions
        if not y_pred:
            continue
        
        precision = []
        recall = []
        relevant_ranks = []
        relevant_count = 0
        
        for i, doc_id in enumerate(y_pred, 1):
            if doc_id in y_true:
                relevant_count += 1
                relevant_ranks.append(relevant_count / i)
            precision.append(relevant_count / i)
            recall.append(relevant_count / len(y_true))
        
        # Store per-query precision and recall
        per_query_precisions[query_id] = (recall, precision)
        
        # Compute Average Precision for the query
        ap = np.sum(relevant_ranks) / len(y_true) if relevant_ranks else 0
        average_precisions.append(ap)

    # Compute Mean Average Precision (MAP)
    map_score = np.mean(average_precisions) if average_precisions else 0

    # Interpolate and average precision-recall curves over all queries
    recall_levels = np.linspace(0.0, 1.0, 11)
    interpolated_precisions = []

    for r_level in recall_levels:
        precisions_at_r = []
        for query_id in per_query_precisions:
            recall, precision = per_query_precisions[query_id]
            # Find maximum precision for recall >= r_level
            interpolated_precision = max(
                [p for p, r in zip(precision, recall) if r >= r_level],
                default=0
            )
            precisions_at_r.append(interpolated_precision)
        # Average precision at this recall level over all queries
        interpolated_precisions.append(np.mean(precisions_at_r))

    # Compute AUC
    auc_score = np.trapezoid(interpolated_precisions, recall_levels)

    # Plot the averaged interpolated precision-recall curve
    plt.plot(
        recall_levels,
        interpolated_precisions,
        drawstyle="steps-post",
        label=f"MAP: {map_score:.4f}, AUC: {auc_score:.4f}",
        linewidth=1,
    )

    # Customize plot appearance
    plt.xlabel("Recall")
    plt.ylabel("Precision")
    plt.xlim(0, 1)
    plt.ylim(0, 1)
    plt.legend(loc="lower left", prop={"size": 10})
    plt.title("Precision-Recall Curve (Averaged over Queries)")

    # Save the plot to the specified output PNG file
    plt.savefig(output_file, format="png", dpi=300)
    print(f"Precision-Recall plot saved to {output_file}")


if __name__ == "__main__":
    # Argument parser to handle the qrels file and output file as command-line arguments
    parser = argparse.ArgumentParser(
        description="Generate a Precision-Recall curve from Solr results (in TREC format) and qrels, averaged over multiple queries."
    )
    parser.add_argument(
        "--qrels",
        type=str,
        required=True,
        help="Path to the qrels file (ground truth document IDs in TREC format)",
    )
    parser.add_argument("--output", type=str, required=True, help="Path to the output PNG file")
    args = parser.parse_args()

    # Run the main function with the provided qrels file and output file
    main(args.qrels, args.output)
