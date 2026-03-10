"""Tests for the plugin ecosystem.

Covers:
- aptdata.plugins.base (BaseReader / BaseWriter interfaces)
- aptdata.plugins.manager (PluginManager, PluginDependencyError)
- aptdata.plugins.dataset (InMemoryDataset)
- aptdata.plugins.local_fs (CSV / JSON readers and writers)
- aptdata.plugins.rest (APIReader — with httpx mock)
- aptdata.plugins.postgres (friendly dependency error)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from aptdata.plugins.base import BaseReader, BaseWriter
from aptdata.plugins.dataset import InMemoryDataset
from aptdata.plugins.local_fs import (
    CSVReader,
    CSVWriter,
    JSONReader,
    JSONWriter,
    ParquetReader,
    ParquetWriter,
)
from aptdata.plugins.manager import PluginDependencyError, PluginManager, plugin_manager
from aptdata.plugins.rest import APIReader

# ---------------------------------------------------------------------------
# Concrete stubs for abstract base classes
# ---------------------------------------------------------------------------


class _StubReader(BaseReader):
    def __init__(self, endpoint: str, token: str = "x") -> None:
        self.endpoint = endpoint
        self.token = token

    def read(self, **kwargs: Any) -> InMemoryDataset:
        ds = InMemoryDataset(uri="stub://reader")
        ds.write(
            [
                {"col": "val"},
                {"col": "val2"},
                {"col": "val3"},
                {"col": "val4"},
                {"col": "val5"},
                {"col": "val6"},
            ]
        )
        return ds


class _StubWriter(BaseWriter):
    def __init__(self) -> None:
        self.last_dataset: Any = None

    def write(self, dataset: Any, **kwargs: Any) -> None:
        self.last_dataset = dataset


# ===================================================================
# BaseReader / BaseWriter
# ===================================================================


class TestBaseReader:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseReader()  # type: ignore[abstract]

    def test_concrete_read(self):
        reader = _StubReader(endpoint="https://example.com")
        ds = reader.read()
        assert ds.read()[0] == {"col": "val"}


class TestBaseWriter:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseWriter()  # type: ignore[abstract]

    def test_concrete_write(self):
        writer = _StubWriter()
        ds = InMemoryDataset(uri="test://w")
        ds.write([{"a": 1}])
        writer.write(ds)
        assert writer.last_dataset is ds


# ===================================================================
# InMemoryDataset
# ===================================================================


class TestInMemoryDataset:
    def test_empty_by_default(self):
        ds = InMemoryDataset(uri="mem://empty")
        assert ds.read() == []
        assert len(ds) == 0

    def test_write_and_read(self):
        ds = InMemoryDataset(uri="mem://data")
        records = [{"x": 1}, {"x": 2}]
        ds.write(records)
        assert ds.read() == records
        assert len(ds) == 2

    def test_records_property(self):
        ds = InMemoryDataset(uri="mem://rec")
        ds.write([{"k": "v"}])
        assert ds.records == [{"k": "v"}]

    def test_write_rejects_non_list(self):
        ds = InMemoryDataset(uri="mem://bad")
        with pytest.raises(TypeError, match="list of dicts"):
            ds.write("not a list")  # type: ignore[arg-type]

    def test_uri_required(self):
        with pytest.raises(Exception):
            InMemoryDataset()  # type: ignore[call-arg]


# ===================================================================
# PluginManager
# ===================================================================


class TestPluginManager:
    def test_register_and_get_reader(self):
        pm = PluginManager()
        pm.register_reader("stub", _StubReader)
        assert pm.get_reader("stub") is _StubReader

    def test_register_and_get_writer(self):
        pm = PluginManager()
        pm.register_writer("stub", _StubWriter)
        assert pm.get_writer("stub") is _StubWriter

    def test_get_unknown_returns_none(self):
        pm = PluginManager()
        assert pm.get_reader("nonexistent") is None
        assert pm.get_writer("nonexistent") is None

    def test_list_readers(self):
        pm = PluginManager()
        pm.register_reader("b_reader", _StubReader)
        pm.register_reader("a_reader", _StubReader)
        assert pm.list_readers() == ["a_reader", "b_reader"]

    def test_list_writers(self):
        pm = PluginManager()
        pm.register_writer("z_writer", _StubWriter)
        pm.register_writer("a_writer", _StubWriter)
        assert pm.list_writers() == ["a_writer", "z_writer"]

    def test_list_plugins(self):
        pm = PluginManager()
        pm.register_reader("r1", _StubReader)
        pm.register_writer("w1", _StubWriter)
        result = pm.list_plugins()
        assert result == {"readers": ["r1"], "writers": ["w1"]}

    def test_get_plugin_schema(self):
        pm = PluginManager()
        pm.register_reader("stub", _StubReader)
        schema = pm.get_plugin_schema("stub")
        assert schema["name"] == "stub"
        assert schema["type"] == "reader"
        assert any(
            arg["name"] == "endpoint" and arg["required"] for arg in schema["arguments"]
        )
        token_argument = next(
            arg for arg in schema["arguments"] if arg["name"] == "token"
        )
        assert token_argument["default"] == "x"

    def test_preview_dataset_returns_five_rows(self):
        pm = PluginManager()
        pm.register_reader("stub", _StubReader)
        rows = pm.preview_dataset("stub", endpoint="https://example.com")
        assert len(rows) == 5

    def test_load_module_success(self):
        pm = PluginManager()
        mod = pm.load_module("aptdata.plugins.base")
        assert hasattr(mod, "BaseReader")

    def test_load_module_failure(self):
        pm = PluginManager()
        with pytest.raises(ModuleNotFoundError):
            pm.load_module("nonexistent.module.xyz")

    def test_load_module_with_mock(self):
        pm = PluginManager()
        with patch("importlib.import_module") as mock_import:
            mock_import.return_value = "mock_module"
            result = pm.load_module("some.module")
            mock_import.assert_called_once_with("some.module")
            assert result == "mock_module"

    def test_load_module_empty_string(self):
        pm = PluginManager()
        with pytest.raises(ValueError, match="Empty module name"):
            pm.load_module("")

    def test_load_module_invalid_type(self):
        pm = PluginManager()
        with pytest.raises((TypeError, AttributeError)):
            pm.load_module(123)  # type: ignore[arg-type]

    def test_load_module_builtin(self):
        pm = PluginManager()
        mod = pm.load_module("os")
        assert mod is os

    def test_global_singleton_exists(self):
        assert isinstance(plugin_manager, PluginManager)


class TestPluginDependencyError:
    def test_attributes(self):
        err = PluginDependencyError("MyPlugin", "some-lib")
        assert err.plugin_name == "MyPlugin"
        assert err.package == "some-lib"

    def test_message_contains_install_hint(self):
        err = PluginDependencyError("PG", "psycopg2")
        assert "pip install psycopg2" in str(err)

    def test_is_import_error(self):
        err = PluginDependencyError("X", "y")
        assert isinstance(err, ImportError)


# ===================================================================
# CSVReader / CSVWriter
# ===================================================================


class TestCSVReadWrite:
    def test_roundtrip(self, tmp_path: Path):
        csv_path = tmp_path / "data.csv"
        csv_path.write_text("name,age\nAlice,30\nBob,25\n")

        reader = CSVReader(str(csv_path))
        ds = reader.read()
        assert len(ds) == 2
        assert ds.read()[0] == {"name": "Alice", "age": "30"}

        out_path = tmp_path / "out.csv"
        writer = CSVWriter(str(out_path))
        writer.write(ds)
        lines = out_path.read_text().strip().splitlines()
        assert lines[0] == "name,age"
        assert len(lines) == 3

    def test_custom_delimiter(self, tmp_path: Path):
        csv_path = tmp_path / "semi.csv"
        csv_path.write_text("a;b\n1;2\n")

        reader = CSVReader(str(csv_path), delimiter=";")
        ds = reader.read()
        assert ds.read() == [{"a": "1", "b": "2"}]

    def test_write_creates_parent_dirs(self, tmp_path: Path):
        out_path = tmp_path / "sub" / "dir" / "file.csv"
        ds = InMemoryDataset(uri="test://csv")
        ds.write([{"x": "1"}])
        writer = CSVWriter(str(out_path))
        writer.write(ds)
        assert out_path.exists()

    def test_write_empty_dataset(self, tmp_path: Path):
        out_path = tmp_path / "empty.csv"
        ds = InMemoryDataset(uri="test://csv")
        ds.write([])
        writer = CSVWriter(str(out_path))
        writer.write(ds)
        assert out_path.exists()


# ===================================================================
# JSONReader / JSONWriter
# ===================================================================


class TestJSONReadWrite:
    def test_roundtrip(self, tmp_path: Path):
        json_path = tmp_path / "data.json"
        records = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        json_path.write_text(json.dumps(records))

        reader = JSONReader(str(json_path))
        ds = reader.read()
        assert len(ds) == 2
        assert ds.read()[0]["name"] == "Alice"

        out_path = tmp_path / "out.json"
        writer = JSONWriter(str(out_path))
        writer.write(ds)
        loaded = json.loads(out_path.read_text())
        assert loaded == records

    def test_rejects_non_array(self, tmp_path: Path):
        json_path = tmp_path / "bad.json"
        json_path.write_text('{"key": "value"}')
        reader = JSONReader(str(json_path))
        with pytest.raises(ValueError, match="array of objects"):
            reader.read()

    def test_write_creates_parent_dirs(self, tmp_path: Path):
        out_path = tmp_path / "nested" / "out.json"
        ds = InMemoryDataset(uri="test://json")
        ds.write([{"a": 1}])
        writer = JSONWriter(str(out_path))
        writer.write(ds)
        assert out_path.exists()


# ===================================================================
# Parquet (optional dep — test error path only when pyarrow absent)
# ===================================================================


class TestParquetDependencyError:
    def test_reader_raises_without_pyarrow(self):
        with patch.dict("sys.modules", {"pyarrow": None, "pyarrow.parquet": None}):
            reader = ParquetReader("/fake/path.parquet")
            with pytest.raises(PluginDependencyError, match="pyarrow"):
                reader.read()

    def test_writer_raises_without_pyarrow(self):
        with patch.dict("sys.modules", {"pyarrow": None, "pyarrow.parquet": None}):
            ds = InMemoryDataset(uri="test://parquet")
            ds.write([{"x": 1}])
            writer = ParquetWriter("/fake/path.parquet")
            with pytest.raises(PluginDependencyError, match="pyarrow"):
                writer.write(ds)


# ===================================================================
# APIReader (mock httpx)
# ===================================================================


class TestAPIReader:
    def test_simple_get(self):
        """Single GET returning a JSON array."""
        mock_response = MagicMock()
        mock_response.json.return_value = [{"id": 1}, {"id": 2}]
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch("aptdata.plugins.rest._require_httpx") as mock_httpx_fn:
            mock_httpx_mod = MagicMock()
            mock_httpx_mod.Client.return_value = mock_client
            mock_httpx_fn.return_value = mock_httpx_mod

            reader = APIReader(endpoint="https://api.example.com/data")
            ds = reader.read()

        assert len(ds) == 2
        assert ds.read()[0] == {"id": 1}

    def test_get_with_headers(self):
        """GET with custom auth headers."""
        mock_response = MagicMock()
        mock_response.json.return_value = [{"ok": True}]
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch("aptdata.plugins.rest._require_httpx") as mock_httpx_fn:
            mock_httpx_mod = MagicMock()
            mock_httpx_mod.Client.return_value = mock_client
            mock_httpx_fn.return_value = mock_httpx_mod

            headers = {"Authorization": "Bearer token123"}
            reader = APIReader(
                endpoint="https://api.example.com/secure",
                headers=headers,
            )
            reader.read()

        mock_client.get.assert_called_once()
        call_kwargs = mock_client.get.call_args
        assert call_kwargs.kwargs["headers"] == headers

    def test_pagination(self):
        """Paginated GET stops when empty page is returned."""
        page1_response = MagicMock()
        page1_response.json.return_value = [{"p": 1}]
        page1_response.raise_for_status = MagicMock()

        page2_response = MagicMock()
        page2_response.json.return_value = []
        page2_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = [page1_response, page2_response]

        with patch("aptdata.plugins.rest._require_httpx") as mock_httpx_fn:
            mock_httpx_mod = MagicMock()
            mock_httpx_mod.Client.return_value = mock_client
            mock_httpx_fn.return_value = mock_httpx_mod

            reader = APIReader(
                endpoint="https://api.example.com/paginated",
                pagination_key="page",
            )
            ds = reader.read()

        assert len(ds) == 1
        assert mock_client.get.call_count == 2

    def test_records_path(self):
        """Nested JSON response with records_path."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"items": [{"id": 99}]}}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch("aptdata.plugins.rest._require_httpx") as mock_httpx_fn:
            mock_httpx_mod = MagicMock()
            mock_httpx_mod.Client.return_value = mock_client
            mock_httpx_fn.return_value = mock_httpx_mod

            reader = APIReader(
                endpoint="https://api.example.com/nested",
                records_path="data.items",
            )
            ds = reader.read()

        assert ds.read() == [{"id": 99}]

    def test_missing_httpx_raises(self):
        """Friendly error when httpx is not installed."""
        with patch.dict("sys.modules", {"httpx": None}):
            reader = APIReader(endpoint="https://example.com")
            with pytest.raises(PluginDependencyError, match="httpx"):
                reader.read()


# ===================================================================
# PostgreSQL (dependency error path)
# ===================================================================


class TestPostgresPlugin:
    def test_reader_raises_without_sqlalchemy(self):
        with patch.dict("sys.modules", {"sqlalchemy": None}):
            from aptdata.plugins.postgres import PostgresReader

            reader = PostgresReader("postgresql://x", "SELECT 1")
            with pytest.raises(PluginDependencyError, match="sqlalchemy"):
                reader.read()

    def test_writer_raises_without_sqlalchemy(self):
        with patch.dict("sys.modules", {"sqlalchemy": None}):
            from aptdata.plugins.postgres import PostgresWriter

            ds = InMemoryDataset(uri="pg://test")
            ds.write([{"a": "1"}])
            writer = PostgresWriter("postgresql://x", "my_table")
            with pytest.raises(PluginDependencyError, match="sqlalchemy"):
                writer.write(ds)


# ===================================================================
# Integration: plugins/__init__.py re-exports
# ===================================================================


class TestPluginInitReExports:
    def test_base_classes_accessible(self):
        from aptdata.plugins import BaseReader, BaseWriter

        assert BaseReader is not None
        assert BaseWriter is not None

    def test_manager_accessible(self):
        from aptdata.plugins import PluginDependencyError, PluginManager, plugin_manager

        assert isinstance(plugin_manager, PluginManager)
        assert issubclass(PluginDependencyError, ImportError)

    def test_registry_still_works(self):
        from aptdata.plugins import registry

        assert hasattr(registry, "register")
        assert hasattr(registry, "list_systems")
