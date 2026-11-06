"""Cabeceras de seguridad del inventario y arranque con Gunicorn."""
import pathlib
import runpy
import sys

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]


def test_panel_con_csp_a_la_medida(client):
    r = client.get("/")
    csp = r.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "https://fonts.googleapis.com" in csp
    assert "https://fonts.gstatic.com" in csp
    assert "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp
    assert r.headers["X-Frame-Options"] == "DENY"


def test_api_con_cabeceras_de_seguridad(client):
    r = client.get("/api/usuarios")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_las_respuestas_401_tambien_llevan_cabeceras(client, monkeypatch):
    monkeypatch.setenv("BACKEND_SERVICE_PASSWORD", "clave")
    r = client.get("/api/usuarios")
    assert r.status_code == 401
    assert r.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("servicio, puerto", [("auth-proxy", "9000"), ("inventory-service", "5000"),
                                              ("legacy-app-demo", "6000")])
def test_configuracion_de_gunicorn(monkeypatch, servicio, puerto):
    archivo = str(RAIZ / servicio / "gunicorn.conf.py")
    monkeypatch.delenv("PORT", raising=False)
    conf = runpy.run_path(archivo)
    assert conf["bind"] == f"0.0.0.0:{puerto}"
    assert conf["workers"] == 1
    assert conf["accesslog"] == "-"
    monkeypatch.setenv("PORT", "10000")
    assert runpy.run_path(archivo)["bind"] == "0.0.0.0:10000"


def test_wsgi_prepara_la_base_antes_de_atender(inv, monkeypatch):
    llamadas = []
    monkeypatch.setitem(sys.modules, "app", inv)
    monkeypatch.setattr(inv, "preparar_base", lambda: llamadas.append(True))
    modulo = runpy.run_path(str(RAIZ / "inventory-service" / "wsgi.py"))
    assert llamadas == [True]
    assert modulo["app"] is inv.app
