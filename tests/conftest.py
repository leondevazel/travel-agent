import pytest

from travel_agent import db as db_module


@pytest.fixture
def db_ready(tmp_path):
    db_module.init_engine(f"sqlite:///{tmp_path / 'test.db'}")
    yield
    db_module._engine = None
    db_module._SessionLocal = None
