# Query optimizer
#
# Turns a ParsedQuery + Database schema into the cheapest physical plan tree
# (defined in plan.py): classify conditions, choose access paths and join
# algorithms by cost, enumerate join orders, and build the tree.

import math
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import permutations
from typing import Optional

from utils.parser import CmpOperators, Condition, ParsedQuery
from utils.plan import (
    Algorithm,
    JoinNode,
    Operation,
    PlanNode,
    ProjectionNode,
    ScanNode,
    SortNode,
)
from utils.schema import DBStatistics, IndexType


@dataclass
class Optimizer:
    dbs: DBStatistics
    query: ParsedQuery

    # per-table filter conditions -> Used for selectivity
    selections: dict = field(default_factory=lambda: defaultdict(list))
    # conditions linking two tables -> used for join ordering + algorithm cost
    join_conditions: list = field(default_factory=list)

    def __post_init__(self):
        for cond in self.query.conditions:
            left_is_attr  = self._is_attribute(cond.left_side)
            right_is_attr = self._is_attribute(cond.right_side)

            if not left_is_attr and not right_is_attr:
                continue  # literal-literal condition, skip

            if left_is_attr and right_is_attr:
                left_table  = cond.left_side.split(".")[0]
                right_table = cond.right_side.split(".")[0]

                if left_table == right_table:
                    self.selections[left_table].append(cond)
                else:
                    self.join_conditions.append(cond)
            else:
                attr_side = cond.left_side if left_is_attr else cond.right_side
                table = attr_side.split(".")[0]
                self.selections[table].append(cond)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _is_attribute(value: str) -> bool:
        # A qualified attribute looks like "Table.column".
        # Exclude numeric literals like "8.5"
        if "." not in value:
            return False
        return not value.split(".")[0].lstrip("-").isdigit()

    def _selectivity(self, cond: Condition, table_name: str) -> float:
        '''Returns fraction of rows surviving one condition (0.0 to 1.0).'''
        table = self.dbs.get_table(table_name)
        attr_side = cond.left_side if self._is_attribute(cond.left_side) else cond.right_side
        attr_name = attr_side.split(".")[1]
        attr = table.get_attribute(attr_name)

        if cond.operator == CmpOperators.EQ:
            if attr.unique:
                return 1.0 / table.rowCount
            return 1.0 / attr.distinctValues
        else:
            # range — no min/max in schema, use n/2 heuristic
            return 0.5

    def _out_rows_after_selections(self, table_name: str) -> int:
        '''Estimated rows remaining after applying all selections on a table.'''
        table = self.dbs.get_table(table_name)
        conds = self.selections.get(table_name, [])
        if not conds:
            return table.rowCount

        combined = 1.0
        for cond in conds:
            combined *= self._selectivity(cond, table_name)
        return max(1, round(table.rowCount * combined))

    # -------------------------------------------------------------------------
    # Access path selection
    # -------------------------------------------------------------------------

    def _best_scan(self, table_name: str) -> ScanNode:
        '''Picks cheapest access path for a table and returns a costed ScanNode.'''
        table = self.dbs.get_table(table_name)
        conds = self.selections.get(table_name, [])
        out_rows   = self._out_rows_after_selections(table_name)
        out_blocks = max(1, out_rows // table.rowsPerBlock)

        best_cost  = table.blockCount   # full scan baseline
        best_algo  = Algorithm.FULL_SCAN
        best_index = None

        is_equality = lambda c: c.operator == CmpOperators.EQ

        for cond in conds:
            if not self._is_attribute(cond.left_side):
                continue
            attr_name = cond.left_side.split(".")[1]
            attr      = table.get_attribute(attr_name)

            for index in table.indexes:
                if index.attributes[0] != attr_name:
                    continue

                if index.type == IndexType.HASH:
                    if not is_equality(cond):
                        continue
                    cost = 2  # hash bucket + one read
                elif index.type == IndexType.B_PLUS_TREE:
                    h = index.treeHeight
                    if index.clustered:
                        if is_equality(cond):
                            cost = h + 1 if attr.unique else h + out_blocks   # A2 / A3
                        else:
                            cost = h + out_blocks                               # A5
                    else:
                        if is_equality(cond):
                            cost = h + 1 if attr.unique else h + out_rows      # A4-key / A4-nonkey
                        else:
                            cost = h + out_rows                                 # A6
                else:
                    continue

                if cost < best_cost:
                    best_cost  = cost
                    best_algo  = Algorithm.HASH_INDEX if index.type == IndexType.HASH else Algorithm.BPLUS_INDEX
                    best_index = index.name

        # V values from schema, capped at surviving rows after selections
        v_values = {
            f"{table_name}.{a.name}": min(a.distinctValues, out_rows)
            for a in table.attributes
        }
        return ScanNode(
            table=table_name,
            operation=Operation.SELECTION if conds else Operation.SCAN,
            algorithm=best_algo,
            access_path=best_index,
            cost=best_cost,
            out_rows=out_rows,
            out_blocks=out_blocks,
            v_values=v_values,
        )

    # -------------------------------------------------------------------------
    # Join size estimation
    # -------------------------------------------------------------------------

    def _join_out_size(self, left: PlanNode, right: PlanNode,
                       cond: Optional[Condition]) -> tuple:
        '''Estimates (out_rows, out_blocks) for a join of left and right.'''
        if cond is None:
            out_rows = left.out_rows * right.out_rows  # Cartesian product
        else:
            # Use V values from nodes — these are propagated through intermediate
            # join results, so they reflect actual estimated distinct values, not
            # just original schema values (V propagation from slides).
            v_l = left.v_values.get(cond.left_side) or right.v_values.get(cond.left_side, 1)
            v_r = left.v_values.get(cond.right_side) or right.v_values.get(cond.right_side, 1)
            n_l, n_r = left.out_rows, right.out_rows
            # min(n_l*n_r / V(A,l), n_l*n_r / V(A,r))
            out_rows = max(1, min(n_l * n_r // max(v_l, 1),
                                   n_l * n_r // max(v_r, 1)))

        l_rpb    = max(1, left.out_rows  // max(1, left.out_blocks))
        r_rpb    = max(1, right.out_rows // max(1, right.out_blocks))
        rpb      = max(1, (l_rpb + r_rpb) // 2)
        out_blocks = max(1, math.ceil(out_rows / rpb))
        return out_rows, out_blocks

    # -------------------------------------------------------------------------
    # Join algorithm costs
    # -------------------------------------------------------------------------

    def _sort_cost(self, b: int) -> int:
        '''External merge sort cost in block transfers.'''
        M = self.dbs.bufferBlocks
        if b <= M:
            return b  # fits in memory
        passes = math.ceil(math.log(math.ceil(b / M)) / math.log(max(2, M - 1)))
        return b * (2 * passes + 1)

    def _cost_nested_loop(self, outer: PlanNode, inner: PlanNode) -> int:
        return outer.out_rows * inner.out_blocks + outer.out_blocks

    def _cost_block_nested_loop(self, outer: PlanNode, inner: PlanNode) -> int:
        M = self.dbs.bufferBlocks
        return math.ceil(outer.out_blocks / max(1, M - 2)) * inner.out_blocks + outer.out_blocks

    def _cost_index_nested_loop(self, outer: PlanNode, inner: PlanNode,
                                 cond: Optional[Condition]) -> int:
        '''Index NL only viable when inner is a base table with an index on the join attr.'''
        if cond is None or not isinstance(inner, ScanNode):
            return float('inf')

        l_tbl = cond.left_side.split(".")[0]
        r_tbl = cond.right_side.split(".")[0]

        if l_tbl == inner.table:
            inner_attr = cond.left_side.split(".")[1]
        elif r_tbl == inner.table:
            inner_attr = cond.right_side.split(".")[1]
        else:
            return float('inf')

        inner_table = self.dbs.get_table(inner.table)
        best_c = float('inf')

        for index in inner_table.indexes:
            if index.attributes[0] != inner_attr:
                continue
            attr = inner_table.get_attribute(inner_attr)
            if index.type == IndexType.HASH:
                c = 2
            elif index.type == IndexType.B_PLUS_TREE:
                if attr.unique:
                    c = index.treeHeight + 1
                elif index.clustered:
                    c = index.treeHeight + max(1, inner.out_rows // inner_table.rowsPerBlock)
                else:
                    c = index.treeHeight + inner.out_rows
            best_c = min(best_c, c)

        if best_c == float('inf'):
            return float('inf')
        return outer.out_blocks + outer.out_rows * best_c

    def _cost_merge_join(self, left: PlanNode, right: PlanNode) -> int:
        return (self._sort_cost(left.out_blocks) +
                self._sort_cost(right.out_blocks) +
                left.out_blocks + right.out_blocks)

    def _cost_hash_join(self, left: PlanNode, right: PlanNode) -> int:
        M = self.dbs.bufferBlocks
        b_build = min(left.out_blocks, right.out_blocks)
        if M * M >= b_build:  # no recursive partitioning needed
            return 3 * (left.out_blocks + right.out_blocks)
        passes = math.ceil(math.log(b_build / M) / math.log(max(2, M - 1)))
        return 2 * (left.out_blocks + right.out_blocks) * passes + (left.out_blocks + right.out_blocks)

    def _best_join(self, left: PlanNode, right: PlanNode,
                   cond: Optional[Condition]) -> JoinNode:
        '''Tries all join algorithms (both outer/inner orderings) and picks cheapest.'''
        out_rows, out_blocks = self._join_out_size(left, right, cond)
        predicate = (f"{cond.left_side} {cond.operator.value} {cond.right_side}"
                     if cond else "CROSS JOIN")

        candidates = []
        for outer, inner in [(left, right), (right, left)]:
            candidates += [
                (Algorithm.NESTED_LOOP,       self._cost_nested_loop(outer, inner)),
                (Algorithm.BLOCK_NESTED_LOOP, self._cost_block_nested_loop(outer, inner)),
                (Algorithm.INDEX_NESTED_LOOP, self._cost_index_nested_loop(outer, inner, cond)),
            ]
        candidates += [
            (Algorithm.MERGE_JOIN, self._cost_merge_join(left, right)),
            (Algorithm.HASH_JOIN,  self._cost_hash_join(left, right)),
        ]

        best_algo, best_cost = min(
            ((a, c) for a, c in candidates if c != float('inf')),
            key=lambda x: x[1],
        )

        # V(A, r |x| s) = min(V(A, input), out_rows) for each attribute — slide formula
        v_values = {
            attr: min(v, out_rows)
            for attr, v in {**left.v_values, **right.v_values}.items()
        }
        return JoinNode(
            algorithm=best_algo,
            predicate=predicate,
            cost=best_cost,
            out_rows=out_rows,
            out_blocks=out_blocks,
            v_values=v_values,
        )

    # -------------------------------------------------------------------------
    # Join ordering
    # -------------------------------------------------------------------------

    def _find_join_cond(self, left_tables: set,
                        right_table: str) -> Optional[Condition]:
        '''Find the join condition linking the right table to the left subtree.'''
        for cond in self.join_conditions:
            l = cond.left_side.split(".")[0]
            r = cond.right_side.split(".")[0]
            if (l in left_tables and r == right_table) or \
               (r in left_tables and l == right_table):
                return cond
        return None

    # -------------------------------------------------------------------------
    # Main entry point
    # -------------------------------------------------------------------------

    def optimize(self) -> PlanNode:
        '''Runs the full optimization pass.

        Returns the root of the plan tree representing the
        cheapest execution plan found for the query.
        '''
        # Step 1: best access path per table (selections pushed down)
        scans = {table: self._best_scan(table) for table in self.query.tables}

        # Step 2: join ordering — enumerate all left-deep permutations, pick cheapest
        if len(self.query.tables) == 1:
            plan = scans[self.query.tables[0]]
        else:
            best_plan = None
            best_cost = float('inf')

            for order in permutations(self.query.tables):
                node = scans[order[0]]
                left_tables = {order[0]}

                for i in range(1, len(order)):
                    right_table = order[i]
                    right  = scans[right_table]
                    cond   = self._find_join_cond(left_tables, right_table)
                    join   = self._best_join(node, right, cond)
                    join.children = [node, right]
                    node   = join
                    left_tables.add(right_table)

                if node.total_cost < best_cost:
                    best_cost = node.total_cost
                    best_plan = node

            plan = best_plan

        # Step 3: expand SELECT * if needed
        attrs = self.query.attributes
        if attrs == ["*"]:
            attrs = [
                f"{t}.{a.name}"
                for t in self.query.tables
                for a in self.dbs.get_table(t).attributes
            ]

        # Step 4: projection
        plan = plan.wrap(ProjectionNode(
            attributes=attrs,
            cost=plan.out_blocks,
            out_rows=plan.out_rows,
            out_blocks=plan.out_blocks,
        ))

        # Step 5: sort (ORDER BY)
        if self.query.order_by:
            plan = plan.wrap(SortNode(
                attribute=self.query.order_by.attribute,
                cost=self._sort_cost(plan.out_blocks),
                out_rows=plan.out_rows,
                out_blocks=plan.out_blocks,
            ))

        return plan