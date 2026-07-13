# DB-optimization

A small query cost optimizer. It loads a database schema with table statistics
and indexes from a JSON file, parses simple SQL-like queries, and builds a
physical execution plan with an estimated cost measured in block transfers.

## Requirements

- Python 3

## Setup

```bash
./setup_env.sh          # create venv and install dependencies
source venv/bin/activate
```

Other commands:

```bash
./setup_env.sh --clean  # remove the virtual environment
./setup_env.sh --help   # show usage
```

## Usage

```bash
python main.py <path-to-schema.json>
```

Example:

```bash
python main.py DB/example.json
```

The schema loads, then you enter queries at the `>` prompt. Type `exit` to quit.
For each query the optimizer prints the chosen plan tree and its total estimated
cost in block transfers.

## Query syntax

A subset of SQL:

```sql
SELECT <attrs> FROM <tables> [WHERE <conditions>] [ORDER BY <attr> [ASC|DESC]]
```

- `SELECT` and `FROM` are required; `WHERE` and `ORDER BY` are optional.
- Comparison operators: `=`, `!=`, `<`, `>`, `<=`, `>=`.
- `WHERE` conditions are combined with `AND` only (max 6 conditions).
- Up to 4 tables in `FROM`.
- `ORDER BY` supports a single attribute.

## Schema file

A JSON document describing the buffer size and per-table statistics (row/block
counts, attributes with distinct-value counts, and indexes). See
[`DB/example.json`](DB/example.json) for the expected format.

## Project layout

```
main.py            CLI entry point and query REPL
utils/parser.py    parses SQL-like queries into a ParsedQuery
utils/schema.py    loads and validates schema statistics
utils/optimizer.py builds the physical plan and estimates cost
utils/plan.py      plan tree nodes
DB/example.json    sample schema
tests/             pytest suite
```

## Tests

```bash
pytest   # This will run full test suite
```
