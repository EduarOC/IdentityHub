"""RF-01 a RF-04 / HU-01 a HU-03: login único, protección del legacy y propagación de identidad."""
from unittest.mock import MagicMock, patch

from flask import redirect


def test_sin_sesion_redirige_al_login(client):
    r = client.get("/facturas")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/login")


def test_login_redirige_a_keycloak_con_callback(proxy, client):
    with patch.object(proxy.oauth.keycloak, "authorize_redirect",
                      return_value=redirect("http://keycloak.test/auth")) as m:
        r = client.get("/login")
    assert r.status_code == 302
    assert r.headers["Location"] == "http://keycloak.test/auth"
    assert m.call_args.args[0].endswith("/auth/callback")


def test_callback_crea_sesion_con_datos_de_keycloak(proxy, client):
    token = {"userinfo": {"email": "ana.torres@empresa.com", "name": "Ana Torres"}}
    with patch.object(proxy.oauth.keycloak, "authorize_access_token", return_value=token):
        r = client.get("/auth/callback?code=abc&state=xyz")
    assert r.status_code == 302
    assert r.headers["Location"] == "/"
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
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/login")
    assert sesion_iniciada.get("/facturas").status_code == 302  # ya no pasa al backend


def _respuesta_backend(status=200, body=b'{"ok": true}', headers=None):
    resp = MagicMock()
    resp.status_code, resp.content = status, body
    resp.raw.headers = headers or {"Content-Type": "application/json", "Content-Length": "999", "X-Legacy": "1"}
    return resp


def test_con_sesion_reenvia_con_identidad_y_cuenta_de_servicio(proxy, sesion_iniciada):
    with patch.object(proxy.requests, "request", return_value=_respuesta_backend()) as m:
        r = sesion_iniciada.get("/facturas?anio=2026", headers={"Cookie": "x=1", "X-Traza": "t1"})
    assert r.status_code == 200
    assert r.get_json() == {"ok": True}
    kw = m.call_args.kwargs
    assert kw["url"] == "http://legacy.test:6000/facturas"
    assert kw["method"] == "GET"
    assert kw["params"]["anio"] == "2026"
    assert kw["auth"] == ("svc-pruebas", "pass-pruebas")
    assert kw["headers"]["X-Forwarded-User"] == "ana.torres@empresa.com"
    assert kw["headers"]["X-Traza"] == "t1"
    # Nunca se reenvían la cookie de sesión del proxy ni el Host original.
    assert "Cookie" not in kw["headers"]
    assert "Host" not in kw["headers"]
    assert kw["timeout"] == 10
    assert kw["allow_redirects"] is False


def test_no_devuelve_headers_de_transporte(proxy, sesion_iniciada):
    with patch.object(proxy.requests, "request", return_value=_respuesta_backend()):
        r = sesion_iniciada.get("/")
    assert r.headers["X-Legacy"] == "1"
    assert r.headers["Content-Length"] == str(len(r.data))  # lo recalcula Flask; no copia el "999" del backend


def test_reenvia_metodo_y_cuerpo(proxy, sesion_iniciada):
    with patch.object(proxy.requests, "request", return_value=_respuesta_backend(201)) as m:
        r = sesion_iniciada.post("/facturas", data=b"monto=100")
    assert r.status_code == 201
    assert m.call_args.kwargs["method"] == "POST"
    assert m.call_args.kwargs["data"] == b"monto=100"


def test_propaga_errores_del_backend(proxy, sesion_iniciada):
    with patch.object(proxy.requests, "request", return_value=_respuesta_backend(503, b"caido")):
        r = sesion_iniciada.get("/")
    assert r.status_code == 503
    assert r.data == b"caido"


def test_detras_de_https_la_url_de_retorno_es_https(proxy, client):
    # En Render, HTTPS termina antes del contenedor: sin ProxyFix la URL de retorno saldría
    # con http:// y Keycloak la rechazaría por no coincidir con la registrada.
    with patch.object(proxy.oauth.keycloak, "authorize_redirect",
                      return_value=redirect("http://keycloak.test/auth")) as m:
        client.get("/login", headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "identityhub-gateway.onrender.com"})
    assert m.call_args.args[0] == "https://identityhub-gateway.onrender.com/auth/callback"


# ---------------------------------------------------------------- rol obligatorio, CSRF y cierre de sesión
import base64
import json


def _access_token(roles=(), roles_cliente=None):
    carga = {"realm_access": {"roles": list(roles)}}
    if roles_cliente:
        carga["resource_access"] = {"auth-proxy": {"roles": list(roles_cliente)}}
    cuerpo = base64.urlsafe_b64encode(json.dumps(carga).encode()).decode().rstrip("=")
    return f"cabecera.{cuerpo}.firma"


def test_rol_requerido_rechaza_usuario_sin_el_rol(proxy, client, monkeypatch):
    monkeypatch.setattr(proxy, "ROL_REQUERIDO", "admin-ti")
    token = {"access_token": _access_token(["empleado"]), "id_token": "idt",
             "userinfo": {"email": "ana@empresa.com", "name": "Ana"}}
    with patch.object(proxy.oauth.keycloak, "authorize_access_token", return_value=token):
        r = client.get("/auth/callback")
    assert r.status_code == 403
    with client.session_transaction() as s:
        assert "usuario" not in s
        assert s["id_token"] == "idt"
    assert client.get("/facturas").status_code == 302  # sigue sin poder pasar


def test_rol_requerido_acepta_rol_de_realm_o_de_cliente(proxy, client, monkeypatch):
    monkeypatch.setattr(proxy, "ROL_REQUERIDO", "admin-ti")
    for token in ({"access_token": _access_token(["admin-ti"])},
                  {"access_token": _access_token(roles_cliente=["admin-ti"])}):
        with patch.object(proxy.oauth.keycloak, "authorize_access_token", return_value=token):
            r = client.get("/auth/callback")
        assert r.status_code == 302
        with client.session_transaction() as s:
            assert "usuario" in s


def test_rol_requerido_con_token_ilegible_rechaza(proxy, client, monkeypatch):
    monkeypatch.setattr(proxy, "ROL_REQUERIDO", "admin-ti")
    with patch.object(proxy.oauth.keycloak, "authorize_access_token", return_value={"access_token": "no-es-jwt"}):
        assert client.get("/auth/callback").status_code == 403


def test_cookie_de_sesion_es_samesite_lax(proxy):
    assert proxy.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert proxy.app.config["SESSION_COOKIE_HTTPONLY"] is True


def test_post_desde_otro_sitio_se_rechaza(proxy, sesion_iniciada):
    with patch.object(proxy.requests, "request", return_value=_respuesta_backend()) as m:
        r = sesion_iniciada.post("/api/usuarios/1/offboarding", headers={"Origin": "https://sitio-malicioso.example"})
    assert r.status_code == 403
    m.assert_not_called()


def test_post_desde_el_mismo_sitio_pasa(proxy, sesion_iniciada):
    with patch.object(proxy.requests, "request", return_value=_respuesta_backend()) as m:
        r = sesion_iniciada.post("/api/usuarios/1/offboarding", headers={"Origin": "http://localhost"})
    assert r.status_code == 200
    m.assert_called_once()


def test_post_con_referer_ajeno_y_sin_origin_se_rechaza(proxy, sesion_iniciada):
    with patch.object(proxy.requests, "request", return_value=_respuesta_backend()):
        r = sesion_iniciada.post("/api/x", headers={"Referer": "https://otro.example/pagina"})
    assert r.status_code == 403


def test_logout_cierra_tambien_la_sesion_de_keycloak(proxy, client, monkeypatch):
    monkeypatch.setattr(proxy, "FIN_SESION_URL", "https://keycloak.test/realms/identityhub/protocol/openid-connect/logout")
    with client.session_transaction() as s:
        s["usuario"] = {"email": "a@b.co", "nombre": "A"}
        s["id_token"] = "token-id"
    r = client.get("/logout")
    destino = r.headers["Location"]
    assert destino.startswith("https://keycloak.test/realms/identityhub/protocol/openid-connect/logout?")
    assert "id_token_hint=token-id" in destino
    assert "client_id=auth-proxy" in destino
    assert "post_logout_redirect_uri=http%3A%2F%2Flocalhost%2Flogin" in destino
    with client.session_transaction() as s:
        assert "usuario" not in s


def test_logout_consulta_keycloak_si_el_proxy_arranco_antes(proxy, client, monkeypatch):
    # En Render los proxies pueden arrancar antes que Keycloak: la URL se pide al cerrar sesión.
    monkeypatch.setattr(proxy, "FIN_SESION_URL", None)
    monkeypatch.setattr(proxy, "KEYCLOAK_URL", "http://keycloak:8080")
    monkeypatch.setattr(proxy, "KEYCLOAK_EXTERNAL_URL", "https://sso.test")
    metadata = {"end_session_endpoint": "http://keycloak:8080/realms/identityhub/protocol/openid-connect/logout"}
    with patch.object(proxy.oauth.keycloak, "load_server_metadata", return_value=metadata):
        r = client.get("/logout")
    assert r.headers["Location"].startswith("https://sso.test/realms/identityhub/protocol/openid-connect/logout?")


def test_logout_sin_keycloak_disponible_vuelve_al_login(proxy, client, monkeypatch):
    monkeypatch.setattr(proxy, "FIN_SESION_URL", None)
    with patch.object(proxy.oauth.keycloak, "load_server_metadata", side_effect=OSError("caído")):
        r = client.get("/logout")
    assert r.headers["Location"].endswith("/login")


def test_los_archivos_estaticos_se_piden_al_backend(proxy, sesion_iniciada):
    # El proxy no tiene /static propio: los estilos y scripts del aplicativo deben reenviarse.
    with patch.object(proxy.requests, "request", return_value=_respuesta_backend()) as m:
        r = sesion_iniciada.get("/static/style.css")
    assert r.status_code == 200
    assert m.call_args.kwargs["url"].endswith("/static/style.css")


def test_archivos_estaticos_sin_sesion_piden_login(client):
    r = client.get("/static/dashboard.js")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/login")
