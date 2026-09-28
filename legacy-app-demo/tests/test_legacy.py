"""Aplicativo legacy de demostración: solo acepta HTTP Basic con la cuenta de servicio."""
import base64
import importlib.util
import os
import pathlib

import pytest

APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture(scope="module")
def client():
    os.environ.update({"BACKEND_SERVICE_USER": "svc-pruebas", "BACKEND_SERVICE_PASSWORD": "pass-pruebas"})
    spec = importlib.util.spec_from_file_location("legacy_app", APP_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.app.config["TESTING"] = True
    return mod.app.test_client()


def _basic(usuario, clave):
    return {"Authorization": "Basic " + base64.b64encode(f"{usuario}:{clave}".encode()).decode()}


def test_sin_credenciales_responde_401(client):
    r = client.get("/")
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"].startswith("Basic")


def test_credenciales_incorrectas_responde_401(client):
    assert client.get("/", headers=_basic("svc-pruebas", "otra")).status_code == 401
    assert client.get("/", headers=_basic("otro", "pass-pruebas")).status_code == 401


def test_home_muestra_usuario_real_del_proxy(client):
    headers = {**_basic("svc-pruebas", "pass-pruebas"), "X-Forwarded-User": "ana@empresa.com"}
    r = client.get("/", headers=headers)
    assert r.status_code == 200
    assert r.get_json()["autenticado_via_proxy_como"] == "ana@empresa.com"


def test_facturas_sin_header_de_proxy(client):
    body = client.get("/facturas", headers=_basic("svc-pruebas", "pass-pruebas")).get_json()
    assert body["usuario"] == "desconocido"
    assert len(body["facturas"]) == 2
