"""RF-01 a RF-04 / HU-01 a HU-03: login único, protección del legacy y propagación de identidad."""
from unittest.mock import MagicMock, patch

from flask import redirect


def test_sin_sesion_redirige_al_login(client):
    r = client.get("/facturas")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")


def test_login_redirige_a_keycloak_con_callback(proxy, client):
    with patch.object(proxy.oauth.keycloak, "authorize_redirect",
                      return_value=redirect("http://keycloak.test/auth")) as m:
        r = client.get("/login")
    assert r.status_code == 302 and r.headers["Location"] == "http://keycloak.test/auth"
    assert m.call_args.args[0].endswith("/auth/callback")


def test_callback_crea_sesion_con_datos_de_keycloak(proxy, client):
    token = {"userinfo": {"email": "ana.torres@empresa.com", "name": "Ana Torres"}}
    with patch.object(proxy.oauth.keycloak, "authorize_access_token", return_value=token):
        r = client.get("/auth/callback?code=abc&state=xyz")
    assert r.status_code == 302 and r.headers["Location"] == "/"
    with client.session_transaction() as s:
        assert s["usuario"] == {"email": "ana.torres@empresa.com", "nombre": "Ana Torres"}


def test_callback_sin_userinfo_usa_valores_por_defecto(proxy, client):
    with patch.object(proxy.oauth.keycloak, "authorize_access_token", return_value={}):
        client.get("/auth/callback")
    with client.session_transaction() as s:
        assert s["usuario"] == {"email": "desconocido", "nombre": "desconocido"}


def test_callback_usa_preferred_username_si_no_hay_nombre(proxy, client):
    token = {"userinfo": {"email": "a@b.co", "preferred_username": "ana.torres"}}
    with patch.object(proxy.oauth.keycloak, "authorize_access_token", return_value=token):
        client.get("/auth/callback")
    with client.session_transaction() as s:
        assert s["usuario"]["nombre"] == "ana.torres"


def test_logout_cierra_sesion(sesion_iniciada):
    r = sesion_iniciada.get("/logout")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    assert sesion_iniciada.get("/facturas").status_code == 302  # ya no pasa al backend


def _respuesta_backend(status=200, body=b'{"ok": true}', headers=None):
    resp = MagicMock()
    resp.status_code, resp.content = status, body
    resp.raw.headers = headers or {"Content-Type": "application/json", "Content-Length": "999", "X-Legacy": "1"}
    return resp


def test_con_sesion_reenvia_con_identidad_y_cuenta_de_servicio(proxy, sesion_iniciada):
    with patch.object(proxy.requests, "request", return_value=_respuesta_backend()) as m:
        r = sesion_iniciada.get("/facturas?anio=2026", headers={"Cookie": "x=1", "X-Traza": "t1"})
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    kw = m.call_args.kwargs
    assert kw["url"] == "http://legacy.test:6000/facturas"
    assert kw["method"] == "GET" and kw["params"]["anio"] == "2026"
    assert kw["auth"] == ("svc-pruebas", "pass-pruebas")
    assert kw["headers"]["X-Forwarded-User"] == "ana.torres@empresa.com"
    assert kw["headers"]["X-Traza"] == "t1"
    # Nunca se reenvían la cookie de sesión del proxy ni el Host original.
    assert "Cookie" not in kw["headers"] and "Host" not in kw["headers"]
    assert kw["timeout"] == 10 and kw["allow_redirects"] is False


def test_no_devuelve_headers_de_transporte(proxy, sesion_iniciada):
    with patch.object(proxy.requests, "request", return_value=_respuesta_backend()):
        r = sesion_iniciada.get("/")
    assert r.headers["X-Legacy"] == "1"
    assert r.headers["Content-Length"] == str(len(r.data))  # lo recalcula Flask; no copia el "999" del backend


def test_reenvia_metodo_y_cuerpo(proxy, sesion_iniciada):
    with patch.object(proxy.requests, "request", return_value=_respuesta_backend(201)) as m:
        r = sesion_iniciada.post("/facturas", data=b"monto=100")
    assert r.status_code == 201
    assert m.call_args.kwargs["method"] == "POST" and m.call_args.kwargs["data"] == b"monto=100"


def test_propaga_errores_del_backend(proxy, sesion_iniciada):
    with patch.object(proxy.requests, "request", return_value=_respuesta_backend(503, b"caido")):
        r = sesion_iniciada.get("/")
    assert r.status_code == 503 and r.data == b"caido"
