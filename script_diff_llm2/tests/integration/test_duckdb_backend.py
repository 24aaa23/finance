import json
import tempfile
from pathlib import Path
import pytest

duckdb = pytest.importorskip('duckdb')
from script_diff_llm.backends.sql_schema import load_source_schema
from script_diff_llm.backends.sql import pre_programmed_scan_sql, semantic_pre_scan_validate_sql


def test_native_schema_dates_aggregation_and_readonly():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'source.duckdb'
        connection = duckdb.connect(str(path))
        connection.execute("CREATE TABLE accounts(id INTEGER PRIMARY KEY, segment VARCHAR, day DATE, value DECIMAL(10,2))")
        connection.execute("INSERT INTO accounts VALUES (1,'A','2026-01-01',1.25),(2,'A','2026-01-02',2.50)")
        connection.close()
        schema = load_source_schema(str(path))
        assert schema['accounts']['primary_keys'] == ['id']
        assert schema['accounts']['columns'][1]['allowed_values'] == ['A']
        result = pre_programmed_scan_sql({'sql': "SELECT DATE_TRUNC('month',day)::DATE AS month,SUM(value) AS total FROM accounts GROUP BY 1"}, str(path))
        assert result['data'] == [{'month':'2026-01-01','total':3.75}]
        json.dumps(result)
        assert pre_programmed_scan_sql({'sql':'DELETE FROM accounts'}, str(path))['status'] == 'error'
        assert pre_programmed_scan_sql({'sql':'SELECT COUNT(*) AS n FROM accounts'}, str(path))['data'] == [{'n':2}]
        # Invalid physical columns fail before making any model request.
        validation = semantic_pre_scan_validate_sql({'sql':'SELECT absent FROM accounts','db_path':str(path)}, None, 'unused')
        assert validation['pre_scan_validation']['is_valid'] is False
        assert 'DuckDB query preparation failed' in validation['pre_scan_validation']['reason']
