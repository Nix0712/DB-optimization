"""Data model for the input JSON. 

Schema defined for handling JSON input
"""
from dataclasses import dataclass
from enum import Enum
import json
import textwrap
from pathlib import Path
from typing import Optional


def _render_table(headers, rows) -> str:
    """Render rows (list of tuples) as an aligned, fixed-width text table."""
    cells = [headers] + [[str(c) for c in r] for r in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(headers))]
    fmt = lambda row: "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row))
    sep = "  ".join("-" * w for w in widths)
    return "\n".join([fmt(headers), sep] + [fmt(r) for r in rows])

class DataType(Enum):
    INT = "INT"
    DOUBLE = "DOUBLE"
    STRING = "STRING"
    DATE = "DATE"

class IndexType(Enum):
    B_PLUS_TREE = "B_PLUS_TREE"
    HASH = "HASH"

@dataclass
class Attribute:
    name: str
    type: DataType
    unique: bool
    distinctValues: int

    @staticmethod
    def from_dict(d: dict) -> "Attribute":
        return Attribute(
            name=d["name"],
            type=DataType(d["type"]),
            unique=d["unique"],
            distinctValues=d["distinctValues"],
        )

@dataclass
class DataIndex:
    name: str
    attributes: list[str]
    type: IndexType
    clustered: bool 
    treeHeight: Optional[int] = None

    def __post_init__(self):
        if self.type == IndexType.B_PLUS_TREE:
            if self.treeHeight is None:
                raise ValueError("Fot B+ tree you need to define tree height argument")
            if self.treeHeight < 0:
                raise ValueError("Tree height can't be negative")

    @staticmethod
    def from_dict(d: dict) -> "DataIndex":
        return DataIndex(
            name=d["name"],
            attributes=list(d["attributes"]),
            type=IndexType(d["type"]),
            clustered=d.get("clustered", False),
            treeHeight=d.get("treeHeight"),
        )
        
@dataclass
class TableMetadata:
    "Tabel Attributes"
    name: str
    rowCount: int
    blockCount: int
    rowsPerBlock: int
    attributes: list[Attribute]
    indexes: list[DataIndex]

    @staticmethod
    def from_dict(d: dict) -> "TableMetadata":
        return TableMetadata(
            name=d["name"],
            rowCount=d["rowCount"],
            blockCount=d["blockCount"],
            rowsPerBlock=d["rowsPerBlock"],
            attributes=[Attribute.from_dict(a) for a in d["attributes"]],
            indexes=[DataIndex.from_dict(i) for i in d["indexes"]],
        )

    def __str__(self) -> str:
        attr_rows = [
            (a.name, a.type.value, "yes" if a.unique else "no", a.distinctValues)
            for a in self.attributes
        ]
        idx_rows = [
            (
                i.name,
                ",".join(i.attributes),
                i.type.value,
                "yes" if i.clustered else "no",
                i.treeHeight if i.treeHeight is not None else "-",
            )
            for i in self.indexes
        ]
        attr_tbl = _render_table(["name", "type", "unique", "distinct"], attr_rows)
        idx_tbl = _render_table(
            ["name", "attributes", "type", "clustered", "height"], idx_rows
        )
        return (
            f"Table: {self.name}  "
            f"(rows={self.rowCount}, blocks={self.blockCount}, rows/block={self.rowsPerBlock})\n"
            f"  Attributes:\n{textwrap.indent(attr_tbl, '    ')}\n"
            f"  Indexes:\n{textwrap.indent(idx_tbl, '    ')}"
        )


@dataclass
class Database:
    "Top-level input: buffer size + all tables"
    bufferBlocks: int
    tables: list[TableMetadata]

    def __init__(self, json_path):
        json_db_stats = self.__load_json(Path(json_path))

        # Fill Attributes from table
        self.__fill_tables(json_db_stats)        

    def __fill_tables(self, json_stats):
        self.bufferBlocks = json_stats["bufferBlocks"]
        self.tables = [
            TableMetadata.from_dict(t) for t in json_stats["schema"]["tables"]
        ]

    # Fancy way to print info
    def __str__(self) -> str:
        parts = [f"Buffer: {self.bufferBlocks} blocks", ""]
        for t in self.tables:
            parts.append(str(t))
            parts.append("")
        return "\n".join(parts)

    def __load_json(self, json_path: Path):
        # Handle edge cases for safe oppening
        if not json_path.exists():
            raise FileNotFoundError(f"Path does not exist: {json_path}")
        if not json_path.is_file():
            raise ValueError(f"Path is not a file: {json_path}")
        if json_path.suffix.lower() != ".json":
            raise ValueError(f"Expected a .json file, got: {json_path.name}")

        # Try to open file
        try:
            with json_path.open("r", encoding="utf-8") as f:
                json_obj = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"File is not valid JSON: {json_path} ({e})") from e

        return json_obj