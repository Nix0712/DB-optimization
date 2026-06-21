# Parsing Query

from dataclasses import dataclass
from enum import Enum
from typing import Optional

_MAXIMUM_NUM_OF_CONDITIONS=6
_MAXIMUM_NUM_OF_TABLES=4

class CmpOperators(str, Enum):
    EQ = "=" # Equal
    NEQ = "!=" # Not Equal
    LT = "<" # Less than
    GT = ">" # Greater than
    LE = "<=" # Less or Equal
    GE = ">=" # Greater or Equal

class ClauseLexTokens(str, Enum):
    SELECT = "SELECT"
    FROM = "FROM"
    WHERE = "WHERE"
    ORDER_BY = "ORDER BY"

class OrderDirection(str, Enum):
    ASC = "ASC"
    DESC = "DESC"

@dataclass
class OrderBy:
    attribute: str
    direction: OrderDirection = OrderDirection.ASC

# Note for Condition -> We only support AND operation
@dataclass
class Condition:
    left_side: str
    operator: CmpOperators
    right_side: str

    @staticmethod
    def from_string(raw: str) -> "Condition":
        raw = raw.strip()

        # Check longer operators first so "<=" is not mistaken for "<"
        for op in sorted(CmpOperators, key=lambda o: -len(o.value)):
            idx = raw.find(op.value)
            if idx == -1:
                continue

            left = raw[:idx].strip()
            right = raw[idx + len(op.value):].strip()
            if not left or not right:
                raise ValueError(f"Invalid condition (empty side): '{raw}'")
            return Condition(left, op, right)

        raise ValueError(f"No valid comparison operator in condition: '{raw}'")

@dataclass
class ParsedQuery:
    attributes: list[str]
    tables: list[str]
    conditions: list[Condition]
    order_by: Optional[OrderBy] = None

    @staticmethod
    def _split_optional(text: str, token: ClauseLexTokens):
        '''Split off an optional trailing clause.

        Returns (before, after) where `after` is the stripped clause body, or
        None if the token is absent.
        '''
        parts = text.split(token)
        after = parts[1].strip() if len(parts) > 1 else None
        return parts[0], after

    def __init__(self, raw_string):
        self.tables = []
        self.conditions = []

        raw_string = raw_string.strip()

        # Ensure SELECT clause is in the right place
        parse_token = raw_string.split(ClauseLexTokens.SELECT)
        if len(parse_token) == 1:
            raise ValueError("Invalid query: missing SELECT clause")
        elif len(parse_token) > 2:
            raise ValueError("Invalid query: too many SELECT clauses")
        elif len(parse_token[0].strip()) != 0:
            raise ValueError("Invalid query: SELECT clauses has to be first in Query")

        # Parsing SELECT Clause -- Required
        # It's safe to take second element, up there we made sure that we have 2 elements
        parse_token = parse_token[1].split(ClauseLexTokens.FROM)

        # Now at this point parse_token has as it's first element SELECTs
        raw_attributes = [a.strip() for a in parse_token[0].split(',')]
        if any(a == "" for a in raw_attributes):
            raise ValueError("SELECT has an empty attribute")

        self.attributes = raw_attributes


        # Parsing FROM Clause -- Required
        if len(parse_token) == 1:
            raise ValueError("Invalid query: missing FROM clause")
        elif len(parse_token) > 2:
            raise ValueError("Invalid query: too many FROM clauses")

        after_from = parse_token[1]

        # The FROM segment ends where WHERE or ORDER BY begins.
        # Peel off ORDER BY first, then WHERE, so what's left is just the tables.
        after_from, order_by_raw = self._split_optional(after_from, ClauseLexTokens.ORDER_BY)
        from_raw,   where_raw    = self._split_optional(after_from, ClauseLexTokens.WHERE)

        raw_tables = [t.strip() for t in from_raw.split(',')]
        if any(t == "" for t in raw_tables):
            raise ValueError("FROM has an empty table name")
        if len(raw_tables) > _MAXIMUM_NUM_OF_TABLES:
            raise ValueError(
                f"Query can be over at most {_MAXIMUM_NUM_OF_TABLES} tables"
            )

        self.tables = raw_tables

        # Parsing WHERE Clause -- Optional
        if where_raw is not None:
            raw_conditions = [c.strip() for c in where_raw.split("AND")]
            if any(c == "" for c in raw_conditions):
                raise ValueError("WHERE has an empty condition")
            if len(raw_conditions) > _MAXIMUM_NUM_OF_CONDITIONS:
                raise ValueError(
                    f"WHERE can have at most {_MAXIMUM_NUM_OF_CONDITIONS} conditions"
                )
            self.conditions = [Condition.from_string(c) for c in raw_conditions]


        # Parsing ORDER BY Clause -- Optional
        if order_by_raw is not None:
            if "," in order_by_raw:
                raise ValueError("ORDER BY supports at most one attribute")

            parts = order_by_raw.split()
            if len(parts) == 0:
                raise ValueError("ORDER BY has no attribute")
            elif len(parts) == 1:
                self.order_by = OrderBy(parts[0])
            elif len(parts) == 2:
                try:
                    direction = OrderDirection(parts[1])
                except ValueError:
                    raise ValueError(f"Invalid ORDER BY direction: '{parts[1]}'")
                self.order_by = OrderBy(parts[0], direction)
            else:
                raise ValueError(f"Invalid ORDER BY clause: '{order_by_raw}'")