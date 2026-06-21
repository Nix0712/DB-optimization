from pathlib import Path
from sys import argv

from utils.optimizer import Optimizer
from utils.parser import ParsedQuery
from utils.schema import DBStatistics


def main(*sysargv):
    first_element = sysargv[0]

    try:
        dbs = DBStatistics(first_element)
    except FileNotFoundError as e:
        print(f"Error loading schema: {e}")
        return
    except ValueError as e:
        print(f"Invalid schema file: {e}")
        return

    print(f"Schema loaded. Buffer: {dbs.bufferBlocks} blocks, "
          f"Tables: {[t.name for t in dbs.tables]}")
    print("Enter a query (or 'exit' to quit):\n")

    '''
    Skipping RA translation layer — no subqueries or nested expressions,
    so the canonical RA shape is always the same and the optimizer builds
    the physical plan directly from the parsed query.
    '''

    while True:
        try:
            query = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not query:
            continue

        if query.lower() == "exit":
            print("Exiting.")
            break

        try:
            parsed_query = ParsedQuery(query)
            plan_tree    = Optimizer(dbs, parsed_query).optimize()
            print()
            print(plan_tree)
            print(f"\nTotal estimated cost: {plan_tree.total_cost} block transfers\n")
        except ValueError as e:
            print(f"Query error: {e}\n")
        except Exception as e:
            print(f"Unexpected error: {e}\n")


if __name__ == "__main__":
    if len(argv) < 2:
        print("Usage: python main.py <path-to-schema.json>")
    else:
        main(*argv[1:])
