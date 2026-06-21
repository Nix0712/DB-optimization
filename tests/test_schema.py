"""Schema loading tests — JSON parsing, lookups, error handling.

Run:
    ./venv/bin/pytest tests/test_schema.py -v
"""

from pathlib import Path

import pytest

from utils.schema import DBStatistics, IndexType, DataType

SCHEMA = Path(__file__).parent / "inputs" / "example.json"


@pytest.fixture(scope="module")
def db():
    return DBStatistics(SCHEMA)


# --- Loading -----------------------------------------------------------------

def test_loads_buffer_and_tables(db):
    assert db.bufferBlocks == 10
    assert [t.name for t in db.tables] == ["Student", "Ispit", "Predmet", "Stipendija"]


def test_table_fields(db):
    student = db.get_table("Student")
    assert student.rowCount == 1000
    assert student.blockCount == 100
    assert student.rowsPerBlock == 10
    assert len(student.attributes) == 5
    assert len(student.indexes) == 3


def test_attribute_fields(db):
    indeks = db.get_table("Student").get_attribute("indeks")
    assert indeks.type == DataType.STRING
    assert indeks.unique is True
    assert indeks.distinctValues == 1000


def test_index_fields(db):
    indexes = {i.name: i for i in db.get_table("Student").indexes}
    clustered = indexes["idx_student_indeks_clustered"]
    assert clustered.type == IndexType.B_PLUS_TREE
    assert clustered.clustered is True
    assert clustered.treeHeight == 3

    hash_idx = indexes["idx_student_ime_hash"]
    assert hash_idx.type == IndexType.HASH
    assert hash_idx.treeHeight is None


def test_str_renders(db):
    # __str__ should produce a non-empty table for each section
    out = str(db)
    assert "Student" in out
    assert "Buffer" in out


# --- Lookups -----------------------------------------------------------------

def test_get_table_missing(db):
    with pytest.raises(ValueError):
        db.get_table("Nonexistent")


def test_get_attribute_missing(db):
    with pytest.raises(ValueError):
        db.get_table("Student").get_attribute("nonexistent")


# --- File error handling -----------------------------------------------------

def test_missing_file():
    with pytest.raises(FileNotFoundError):
        DBStatistics("does/not/exist.json")


def test_not_json_extension(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("{}")
    with pytest.raises(ValueError):
        DBStatistics(f)


def test_invalid_json(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("{ not valid json ]")
    with pytest.raises(ValueError):
        DBStatistics(f)


def test_directory_not_file(tmp_path):
    with pytest.raises(ValueError):
        DBStatistics(tmp_path)


# --- Index validation (DataIndex.__post_init__) ------------------------------

def _schema_with_index(index_obj):
    return {
        "bufferBlocks": 10,
        "schema": {"tables": [{
            "name": "T", "rowCount": 100, "blockCount": 10, "rowsPerBlock": 10,
            "attributes": [{"name": "k", "type": "INT", "unique": False, "distinctValues": 10}],
            "indexes": [index_obj],
        }]},
    }


def test_bplus_missing_tree_height(tmp_path):
    import json
    bad = _schema_with_index(
        {"name": "i", "attributes": ["k"], "type": "B_PLUS_TREE", "clustered": False}
    )
    f = tmp_path / "s.json"
    f.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        DBStatistics(f)


def test_bplus_negative_tree_height(tmp_path):
    import json
    bad = _schema_with_index(
        {"name": "i", "attributes": ["k"], "type": "B_PLUS_TREE", "clustered": False, "treeHeight": -1}
    )
    f = tmp_path / "s.json"
    f.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        DBStatistics(f)
