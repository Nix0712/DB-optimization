"""Optimizer tests — driven by tests/cases.json.

Run:
    ./venv/bin/pytest tests/test_optimizer.py -v
"""

import json
from pathlib import Path

import pytest

from utils.optimizer import Optimizer
from utils.parser import ParsedQuery
from utils.plan import JoinNode, ProjectionNode, ScanNode, SortNode
from utils.schema import DBStatistics

TEST_DIR = Path(__file__).parent
SCHEMA   = TEST_DIR / "inputs" / "example.json"
CASES    = TEST_DIR / "cases.json"


@pytest.fixture(scope="module")
def db():
    return DBStatistics(SCHEMA)


def load_cases():
    with open(CASES) as f:
        return json.load(f)


def collect_nodes(root, node_type):
    """Recursively collect all nodes of a given type from the plan tree."""
    result = []
    if isinstance(root, node_type):
        result.append(root)
    for child in root.children:
        result.extend(collect_nodes(child, node_type))
    return result


def find_scan(root, table_name):
    """Find the ScanNode for a specific table."""
    for node in collect_nodes(root, ScanNode):
        if node.table == table_name:
            return node
    return None


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["id"])
def test_optimizer_case(db, case):
    query = ParsedQuery(case["query"])
    plan  = Optimizer(dbs=db, query=query).optimize()
    exp   = case["expected"]

    print(f"\n[{case['id']}] {case['description']}")
    print(f"Query: {case['query']}")
    print(plan)
    print(f"Total cost: {plan.total_cost}")

    # root operation type
    if "root_operation" in exp:
        assert plan.operation.value == exp["root_operation"], (
            f"Expected root op '{exp['root_operation']}', got '{plan.operation.value}'"
        )

    # ORDER BY attribute
    if "root_attribute" in exp:
        assert isinstance(plan, SortNode)
        assert plan.attribute == exp["root_attribute"]

    # projection attribute count (for SELECT *)
    if "projection_attr_count" in exp:
        proj = plan if isinstance(plan, ProjectionNode) else plan.children[0]
        assert isinstance(proj, ProjectionNode)
        assert len(proj.attributes) == exp["projection_attr_count"], (
            f"Expected {exp['projection_attr_count']} projected attrs, "
            f"got {len(proj.attributes)}: {proj.attributes}"
        )

    # join count
    if "join_count" in exp:
        joins = collect_nodes(plan, JoinNode)
        assert len(joins) == exp["join_count"], (
            f"Expected {exp['join_count']} join(s), found {len(joins)}"
        )

    # total cost must be positive
    if exp.get("total_cost_positive"):
        assert plan.total_cost > 0

    # per-table scan checks
    for key, value in exp.items():
        if not key.startswith("scan_"):
            continue
        # key format: scan_<TableName>_<field>
        parts = key.split("_", 2)          # ["scan", "Student", "algorithm"]
        if len(parts) != 3:
            continue
        _, table_name, field = parts
        scan = find_scan(plan, table_name)
        assert scan is not None, f"No ScanNode found for table '{table_name}'"

        if field == "algorithm":
            assert scan.algorithm.value == value, (
                f"{table_name} algorithm: expected '{value}', got '{scan.algorithm.value}'"
            )
        elif field == "access_path":
            assert scan.access_path == value, (
                f"{table_name} access_path: expected '{value}', got '{scan.access_path}'"
            )
        elif field == "cost":
            assert scan.cost == value, (
                f"{table_name} cost: expected {value}, got {scan.cost}"
            )
        elif field == "out_rows":
            assert scan.out_rows == value, (
                f"{table_name} out_rows: expected {value}, got {scan.out_rows}"
            )
