"""Parser tests — query parsing, condition splitting, error handling.

Run:
    ./venv/bin/pytest tests/test_parser.py -v
"""

import pytest

from utils.parser import (
    CmpOperators,
    Condition,
    OrderDirection,
    ParsedQuery,
)


# --- Condition.from_string ---------------------------------------------------

@pytest.mark.parametrize("raw, left, op, right", [
    ("prosek > 8.5",        "prosek",        ">",  "8.5"),
    ("smer = IN",           "smer",          "=",  "IN"),
    ("godinaUpisa <= 2020", "godinaUpisa",   "<=", "2020"),
    ("a >= b",              "a",             ">=", "b"),
    ("x != 5",              "x",             "!=", "5"),
    ("A.b = C.d",           "A.b",           "=",  "C.d"),
])
def test_condition_from_string(raw, left, op, right):
    c = Condition.from_string(raw)
    assert c.left_side == left
    assert c.operator.value == op
    assert c.right_side == right


@pytest.mark.parametrize("bad", [
    "prosek 8.5",   # no operator
    "> 5",          # empty left
    "x = ",         # empty right
])
def test_condition_from_string_invalid(bad):
    with pytest.raises(ValueError):
        Condition.from_string(bad)


def test_multichar_operator_precedence():
    # "<=" must not be parsed as "<"
    c = Condition.from_string("a <= 5")
    assert c.operator == CmpOperators.LE


# --- Full query parsing ------------------------------------------------------

def test_full_query():
    q = ParsedQuery("SELECT A.x, A.y FROM A, B WHERE A.id = B.aid AND A.x > 5 ORDER BY A.x")
    assert q.attributes == ["A.x", "A.y"]
    assert q.tables == ["A", "B"]
    assert len(q.conditions) == 2
    assert q.order_by.attribute == "A.x"
    assert q.order_by.direction == OrderDirection.ASC


def test_order_by_desc():
    q = ParsedQuery("SELECT A.x FROM A ORDER BY A.x DESC")
    assert q.order_by.direction == OrderDirection.DESC


def test_no_where_no_order():
    q = ParsedQuery("SELECT A.x FROM A")
    assert q.conditions == []
    assert q.order_by is None


def test_whitespace_tolerant():
    q = ParsedQuery("   SELECT A.x  FROM   A   ")
    assert q.attributes == ["A.x"]
    assert q.tables == ["A"]


# --- Error handling ----------------------------------------------------------

@pytest.mark.parametrize("bad_query", [
    "FROM A",                                   # missing SELECT
    "garbage SELECT A.x FROM A",                # SELECT not first
    "SELECT A.x FROM A SELECT B.y FROM B",      # too many SELECT clauses
    "SELECT A.x",                               # missing FROM
    "SELECT A.x FROM A FROM B",                 # too many FROM clauses
    "SELECT  FROM A",                           # empty attribute
    "SELECT A.x FROM A,,B",                     # empty table name
    "SELECT A.x FROM A, B, C, D, E",            # too many tables (>4)
    "SELECT A.x FROM A WHERE A.x = 1 AND AND A.y = 2",  # empty condition
    "SELECT A.x FROM A ORDER BY",               # ORDER BY with no attribute
    "SELECT A.x FROM A ORDER BY A.x, A.y",      # ORDER BY > 1 attribute
    "SELECT A.x FROM A ORDER BY A.x B C",       # ORDER BY too many parts
    "SELECT A.x FROM A ORDER BY A.x WRONGDIR",  # invalid direction
])
def test_invalid_queries(bad_query):
    with pytest.raises(ValueError):
        ParsedQuery(bad_query)


def test_too_many_conditions():
    conds = " AND ".join(f"A.c{i} = {i}" for i in range(7))   # 7 > max 6
    with pytest.raises(ValueError):
        ParsedQuery(f"SELECT A.x FROM A WHERE {conds}")
