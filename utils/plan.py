# Physical execution plan tree
#
# Each node is one physical operation (a RA operator with a
# concrete algorithm with estimated cost). Children are the inputs the
# operation consumes, so a query becomes a tree of these nodes.
#
# This is only data structure module, mostly used by optimzer

from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, Optional


class Operation(str, Enum):
    SCAN = "Scan"
    SELECTION = "Selection"
    JOIN = "Join"
    PROJECTION = "Projection"
    SORT = "Sort"


class Algorithm(str, Enum):
    # Access paths / selection
    FULL_SCAN = "Full Scan"
    BPLUS_INDEX = "B+ Tree Index"
    HASH_INDEX = "Hash Index"
    # Joins
    NESTED_LOOP = "Nested Loop Join"
    BLOCK_NESTED_LOOP = "Block Nested Loop Join"
    INDEX_NESTED_LOOP = "Index Nested Loop Join"
    MERGE_JOIN = "Merge Join"
    HASH_JOIN = "Hash Join"
    # Other
    EXTERNAL_MERGE_SORT = "External Merge Sort"
    PROJECTION = "Projection"


@dataclass
class PlanNode:
    """Base node in the physical plan tree."""

    algorithm: Optional[Algorithm] = None
    operation: Optional[Operation] = None
    cost: int = 0                  # Cost is represented in block transfers
    out_rows: int = 0              # estimated rows produced by this node
    out_blocks: int = 0           # estimated blocks produced (materialized output)
    children: list["PlanNode"] = field(default_factory=list)
    # V(A, node) for each attribute — used by subsequent join size estimation
    v_values: dict = field(default_factory=dict)

    # Per-subclass identity; the base has none.
    DEFAULT_OPERATION: ClassVar[Optional[Operation]] = None
    DEFAULT_ALGORITHM: ClassVar[Optional[Algorithm]] = None

    def __post_init__(self):
        if self.operation is None:
            self.operation = self.DEFAULT_OPERATION
        if self.algorithm is None:
            self.algorithm = self.DEFAULT_ALGORITHM

    @property
    def total_cost(self) -> int:
        """Cost of this node plus the entire subtree below it."""
        return self.cost + sum(child.total_cost for child in self.children)

    def wrap(self, parent: "PlanNode", *extra_children: "PlanNode") -> "PlanNode":
        """Place `parent` on top of this node and return it.

        `self` becomes the (first) child; pass `extra_children` for operators
        that take more than one input (e.g. the right side of a join):

            plan = left.wrap(JoinNode(predicate=p, algorithm=a), right)
            plan = plan.wrap(ProjectionNode(attributes=[...]))
            plan = plan.wrap(SortNode(attribute="..."))
        """
        parent.children = [self, *extra_children]
        return parent

    def __str__(self) -> str:
        return self._render(prefix="", is_root=True, is_last=True)

    def _label(self) -> str:
        """The node's own description (operation, algorithm, detail)."""
        detail = self._describe()
        detail = f" {detail}" if detail else ""
        return f"{self.operation.value} [{self.algorithm.value}]{detail}"

    def _metrics(self) -> str:
        return f"cost={self.cost}, rows={self.out_rows}, blocks={self.out_blocks}"

    def _render(self, prefix: str, is_root: bool, is_last: bool) -> str:
        # Draw this node with tree connectors, then recurse into children.
        if is_root:
            connector = ""
            child_prefix = prefix
        else:
            connector = "└── " if is_last else "├── "
            child_prefix = prefix + ("    " if is_last else "│   ")

        line = f"{prefix}{connector}{self._label()}  ({self._metrics()})"

        child_lines = []
        for i, child in enumerate(self.children):
            last = i == len(self.children) - 1
            child_lines.append(child._render(child_prefix, is_root=False, is_last=last))

        return "\n".join([line] + child_lines)

    def _describe(self) -> str:
        """Hook: subclass-specific detail for one line. Override per node."""
        return ""


@dataclass
class ScanNode(PlanNode):
    """Access to a base table (full scan or via an index), with selections."""

    table: str = ""
    access_path: Optional[str] = None   # index name used, or None for full scan

    DEFAULT_OPERATION = Operation.SCAN

    def _describe(self) -> str:
        if self.access_path:
            return f"on {self.table} via {self.access_path}"
        return f"on {self.table}"


@dataclass
class JoinNode(PlanNode):
    """Join of its two children on a predicate."""

    predicate: str = ""                 # e.g. "Student.indeks = Ispit.studentIndeks"

    DEFAULT_OPERATION = Operation.JOIN

    def _describe(self) -> str:
        return f"on ({self.predicate})"


@dataclass
class ProjectionNode(PlanNode):
    """Projection onto a subset of attributes."""

    attributes: list[str] = field(default_factory=list)

    DEFAULT_OPERATION = Operation.PROJECTION
    DEFAULT_ALGORITHM = Algorithm.PROJECTION

    def _describe(self) -> str:
        return f"[{', '.join(self.attributes)}]"


@dataclass
class SortNode(PlanNode):
    """Ordering of its single child on one attribute."""

    attribute: str = ""

    DEFAULT_OPERATION = Operation.SORT
    DEFAULT_ALGORITHM = Algorithm.EXTERNAL_MERGE_SORT

    def _describe(self) -> str:
        return f"by {self.attribute}"
