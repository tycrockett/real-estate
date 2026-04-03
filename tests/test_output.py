import csv
import json
from io import StringIO
from pathlib import Path

from realestate.analyzers import score_properties
from realestate.output import available, get_formatter
from realestate.output.json_out import JsonFormatter
from realestate.output.csv_out import CsvFormatter
from realestate.output.table import TableFormatter


def test_formatter_registry():
    assert "table" in available()
    assert "json" in available()
    assert "csv" in available()


def test_json_output(sample_properties, tmp_path: Path):
    scored = score_properties(sample_properties[:5])
    dest = tmp_path / "output.json"

    formatter = JsonFormatter()
    formatter.format(scored, dest=str(dest))

    data = json.loads(dest.read_text())
    assert len(data) == 5
    assert "property" in data[0]
    assert "total_score" in data[0]


def test_csv_output(sample_properties, tmp_path: Path):
    scored = score_properties(sample_properties[:5])
    dest = tmp_path / "output.csv"

    formatter = CsvFormatter()
    formatter.format(scored, dest=str(dest))

    with open(dest) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 5
    assert "address" in rows[0]
    assert "total_score" in rows[0]


def test_table_output(sample_properties, tmp_path: Path):
    scored = score_properties(sample_properties[:3])
    dest = tmp_path / "output.txt"

    formatter = TableFormatter()
    formatter.format(scored, dest=str(dest))

    content = dest.read_text()
    assert "Top Real Estate Deals" in content


def test_empty_results(tmp_path: Path):
    dest = tmp_path / "empty.json"
    formatter = JsonFormatter()
    formatter.format([], dest=str(dest))
    data = json.loads(dest.read_text())
    assert data == []


def test_get_formatter():
    f = get_formatter("json")
    assert isinstance(f, JsonFormatter)
