"""Fixtures del servicio de inventario: carga app.py con una base SQLite temporal."""
import importlib.util
import sys
import os
import pathlib

import pytest

APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture(scope="session")
def modulo(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "inventario.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db}"
    spec = importlib.util.spec_from_file_location("inventory_app", APP_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def inv(modulo):
    """Base de datos limpia en cada prueba."""
    modulo.Base.metadata.drop_all(modulo.engine)
    modulo.init_db()
    return modulo


@pytest.fixture
def client(inv):
    inv.app.config["TESTING"] = True
    return inv.app.test_client()


@pytest.fixture
def con_datos(inv):
    inv.sembrar_datos_ejemplo()
    return inv
