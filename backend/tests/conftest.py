"""Shared fixtures: one warehouse built from the data pack, reused by the Phase 3+ tests."""
import pytest

from app.data_gen.generate import generate
from app.ingest.run import build_warehouse
from app.stores import db
from app.stores.doc_index import DocIndex


@pytest.fixture(scope="session")
def warehouse_path(tmp_path_factory):
    generate()
    path = tmp_path_factory.mktemp("shared") / "warehouse.db"
    build_warehouse(db_path=path)
    return path


@pytest.fixture(scope="session")
def warehouse(warehouse_path):
    conn = db.connect(warehouse_path, readonly=True)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def index(warehouse):
    return DocIndex.load(warehouse)
