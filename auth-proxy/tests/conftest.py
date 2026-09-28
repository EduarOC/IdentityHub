"""Fixtures del auth-proxy. Keycloak y el aplicativo legacy se simulan (no se usa red)."""
import importlib.util
import sys
import os
import pathlib

import pytest

APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture(scope="session")
def proxy():
    os.environ.update({
        "PROXY_SECRET_KEY": "clave-de-pruebas",
        "BACKEND_URL": "http://legacy.test:6000",
        "BACKEND_SERVICE_USER": "svc-pruebas",
        "BACKEND_SERVICE_PASSWORD": "pass-pruebas",
    })
    spec = importlib.util.spec_from_file_location("auth_proxy_app", APP_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    mod.app.config["TESTING"] = True
    return mod


@pytest.fixture()
def client(proxy):
    return proxy.app.test_client()


@pytest.fixture()
def sesion_iniciada(client):
    with client.session_transaction() as s:
        s["usuario"] = {"email": "ana.torres@empresa.com", "nombre": "Ana Torres"}
    return client
