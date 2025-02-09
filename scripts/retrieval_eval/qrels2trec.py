#!/usr/bin/env python3
import sys


def qrels_to_trec(qrels: list) -> None:
    """
    Converts qrels (query relevance judgments) to TREC evaluation format.

    Input Format:
    query_id doc_id

    Output Format:
    query_id 0 doc_id 1

    Arguments:
    - qrels: A list of qrel lines (query_id and doc_id) from standard input.
    """
    for line in qrels:
        try:
            query_id, doc_id = line.strip().split(maxsplit=1)
            print(f"{query_id} 0 {doc_id} 1")
        except ValueError:
            print(f"Error: Invalid qrels format: {line.strip()}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    """
    Read qrels from stdin and output them in TREC format.
    """
    qrels = sys.stdin.readlines()
    qrels_to_trec(qrels)
