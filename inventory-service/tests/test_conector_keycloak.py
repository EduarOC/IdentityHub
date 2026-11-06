"""Conector de Keycloak (RF-08): deshabilitar la cuenta en el SSO al ejecutar un offboarding."""
import base64
from unittest.mock import MagicMock, patch

import pytest
import requests

import conectores as mod

KC = "https://sso.test"
CUENTA = {"Authorization": "Basic " + base64.b64encode(b"svc:clave").decode()}


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    monkeypatch.setenv("CONECTORES_CLAVE", "clave")
    monkeypatch.setenv("KEYCLOAK_URL", KC + "/")


def _resp(json_data=None, status=200):
    r = MagicMock(status_code=status, ok=200 <= status < 300)
    r.json.return_value = json_data if json_data is not None else {}
    return r


def _configurar(client, **cambios):
    datos = {"tenant_id": "identityhub", "client_id": "identityhub-inventario", "client_secret": "s3creto", **cambios}
    return client.put("/api/conectores/keycloak", json=datos)


def _conectar(client, inv):
    assert _configurar(client).status_code == 200
    with patch.object(inv.conectores, "probar_keycloak", return_value="identityhub"):
        assert client.post("/api/conectores/keycloak/probar").status_code == 200


def _ana(client):
    return next(u["id"] for u in client.get("/api/usuarios").get_json() if u["nombre"] == "Ana Torres")


# ------------------------------------------------------------------ rutas
def test_keycloak_aparece_disponible_con_su_servidor(client):
    kc = next(c for c in client.get("/api/conectores").get_json() if c["tipo"] == "keycloak")
    assert kc["disponible"] is True
    assert kc["servidor"] == KC + "/"


@pytest.mark.parametrize("cambios, mensaje", [
    ({"tenant_id": "realm con espacios"}, "realm"),
    ({"tenant_id": None}, "realm"),
    ({"client_id": "cliente/raro"}, "Client ID"),
    ({"client_secret": None}, "secreto"),
    ({"client_secret": "x" * 600}, "secreto"),
])
def test_configurar_keycloak_valida_los_datos(client, cambios, mensaje):
    r = _configurar(client, **cambios)
    assert r.status_code == 400
    assert mensaje in r.get_json()["error"]


def test_probar_keycloak_usa_sus_credenciales(client, inv):
    _configurar(client)
    with patch.object(inv.conectores, "probar_keycloak", return_value="identityhub") as m:
        r = client.post("/api/conectores/keycloak/probar")
    assert r.status_code == 200
    assert m.call_args.args == ("identityhub", "identityhub-inventario", "s3creto")


def test_keycloak_no_se_sincroniza(client, inv):
    _conectar(client, inv)
    r = client.post("/api/conectores/keycloak/sincronizar")
    assert r.status_code == 400
    assert "offboarding" in r.get_json()["error"]


def test_offboarding_deshabilita_la_cuenta_en_keycloak(client, con_datos):
    _conectar(client, con_datos)
    with patch.object(con_datos.conectores, "deshabilitar_en_keycloak", return_value="deshabilitado") as m:
        r = client.post(f"/api/usuarios/{_ana(client)}/offboarding", json={})
    assert r.status_code == 200
    assert r.get_json()["sso"]["resultado"] == "deshabilitado"
    assert m.call_args.args == ("identityhub", "identityhub-inventario", "s3creto", "ana@empresa-ejemplo.com")
    with con_datos.SessionLocal() as s:
        assert s.query(con_datos.EventoOffboarding).one().resultado_sso == "deshabilitado"


def test_offboarding_de_usuario_sin_cuenta_en_keycloak(client, con_datos):
    _conectar(client, con_datos)
    with patch.object(con_datos.conectores, "deshabilitar_en_keycloak", return_value="no_encontrado"):
        sso = client.post(f"/api/usuarios/{_ana(client)}/offboarding", json={}).get_json()["sso"]
    assert sso["resultado"] == "no_encontrado"


def test_si_keycloak_falla_el_retiro_se_registra_igual(client, con_datos):
    _conectar(client, con_datos)
    error = con_datos.conectores.ErrorConector("Se perdió la conexión con Keycloak.")
    with patch.object(con_datos.conectores, "deshabilitar_en_keycloak", side_effect=error):
        r = client.post(f"/api/usuarios/{_ana(client)}/offboarding", json={})
    assert r.status_code == 200
    assert r.get_json()["sso"]["resultado"] == "error"
    assert "Se perdió la conexión" in r.get_json()["sso"]["mensaje"]
    with con_datos.SessionLocal() as s:
        assert s.query(con_datos.Acceso).filter_by(fecha_revocado=None).count() == 2  # solo los de Carlos
        assert s.query(con_datos.EventoOffboarding).one().resultado_sso == "error"


def test_repetir_el_offboarding_reintenta_el_sso(client, con_datos):
    _conectar(client, con_datos)
    ana = _ana(client)
    error = con_datos.conectores.ErrorConector("caído")
    with patch.object(con_datos.conectores, "deshabilitar_en_keycloak", side_effect=error):
        client.post(f"/api/usuarios/{ana}/offboarding", json={})
    with patch.object(con_datos.conectores, "deshabilitar_en_keycloak", return_value="deshabilitado"):
        sso = client.post(f"/api/usuarios/{ana}/offboarding", json={}).get_json()["sso"]
    assert sso["resultado"] == "deshabilitado"
    with con_datos.SessionLocal() as s:
        assert [e.resultado_sso for e in s.query(con_datos.EventoOffboarding).order_by(con_datos.EventoOffboarding.id)] == ["error", "deshabilitado"]


def test_keycloak_con_error_en_la_prueba_no_actua_en_el_offboarding(client, con_datos):
    _configurar(client)  # guardado pero sin probar: estado 'pendiente'
    with patch.object(con_datos.conectores, "deshabilitar_en_keycloak") as m:
        sso = client.post(f"/api/usuarios/{_ana(client)}/offboarding", json={}).get_json()["sso"]
    m.assert_not_called()
    assert sso["resultado"] == "sin_conector"


def test_no_se_puede_ejecutar_el_propio_offboarding(client, con_datos, monkeypatch):
    monkeypatch.setenv("BACKEND_SERVICE_USER", "svc")
    monkeypatch.setenv("BACKEND_SERVICE_PASSWORD", "clave")
    with con_datos.SessionLocal() as s:
        ana = s.query(con_datos.Usuario).filter_by(nombre="Ana Torres").one().id
    r = client.post(f"/api/usuarios/{ana}/offboarding", json={},
                    headers={**CUENTA, "X-Forwarded-User": "ANA@empresa-ejemplo.com"})
    assert r.status_code == 400
    assert "propio offboarding" in r.get_json()["error"]
    with con_datos.SessionLocal() as s:
        assert s.query(con_datos.EventoOffboarding).count() == 0


# ------------------------------------------------------------------ API de Keycloak (simulada)
def test_sin_url_de_keycloak(monkeypatch):
    monkeypatch.delenv("KEYCLOAK_URL")
    with pytest.raises(mod.ErrorConector, match="KEYCLOAK_URL"):
        mod.url_keycloak()


@pytest.mark.parametrize("status, texto", [(404, "no existe"), (401, "rechazó"), (400, "rechazó"), (500, "500")])
def test_token_keycloak_con_error(status, texto):
    with patch.object(mod.requests, "post", return_value=_resp(status=status)):
        with pytest.raises(mod.ErrorConector, match=texto):
            mod._token_keycloak("identityhub", "c", "s")


def test_token_keycloak_sin_red():
    with patch.object(mod.requests, "post", side_effect=requests.ConnectionError("x")):
        with pytest.raises(mod.ErrorConector, match="dormido"):
            mod._token_keycloak("identityhub", "c", "s")


def test_token_keycloak_pide_client_credentials_al_realm():
    with patch.object(mod.requests, "post", return_value=_resp({"access_token": "tok"})) as m:
        assert mod._token_keycloak("identityhub", "c", "s") == "tok"
    assert m.call_args.args[0] == f"{KC}/realms/identityhub/protocol/openid-connect/token"
    assert m.call_args.kwargs["data"]["grant_type"] == "client_credentials"


def test_admin_keycloak_sin_permisos_o_con_error():
    with patch.object(mod.requests, "request", return_value=_resp(status=403)):
        with pytest.raises(mod.ErrorConector, match="manage-users"):
            mod._admin_keycloak("GET", "tok", "identityhub", "/users")
    with patch.object(mod.requests, "request", return_value=_resp(status=502)):
        with pytest.raises(mod.ErrorConector, match="502"):
            mod._admin_keycloak("GET", "tok", "identityhub", "/users")
    with patch.object(mod.requests, "request", side_effect=requests.Timeout("x")):
        with pytest.raises(mod.ErrorConector, match="conexión"):
            mod._admin_keycloak("GET", "tok", "identityhub", "/users")


def test_probar_keycloak_lee_un_usuario():
    with patch.object(mod.requests, "post", return_value=_resp({"access_token": "tok"})), \
         patch.object(mod.requests, "request", return_value=_resp([])) as m:
        assert mod.probar_keycloak("identityhub", "c", "s") == "identityhub"
    assert m.call_args.args == ("GET", f"{KC}/admin/realms/identityhub/users")


def test_deshabilitar_busca_por_correo_y_cierra_sesiones():
    llamadas = []

    def falso(metodo, url, **kwargs):
        llamadas.append((metodo, url.replace(KC, ""), kwargs.get("params"), kwargs.get("json")))
        if metodo == "GET":
            return _resp([{"id": "kc-1"}])
        return _resp(status=204)

    with patch.object(mod.requests, "post", return_value=_resp({"access_token": "tok"})), \
         patch.object(mod.requests, "request", side_effect=falso):
        assert mod.deshabilitar_en_keycloak("identityhub", "c", "s", "ana@empresa.com") == "deshabilitado"
    assert llamadas == [
        ("GET", "/admin/realms/identityhub/users", {"email": "ana@empresa.com", "exact": "true"}, None),
        ("PUT", "/admin/realms/identityhub/users/kc-1", None, {"enabled": False}),
        ("POST", "/admin/realms/identityhub/users/kc-1/logout", None, None),
    ]


def test_deshabilitar_prueba_por_nombre_de_usuario_y_si_no_existe_lo_dice():
    respuestas = iter([_resp([]), _resp([])])
    with patch.object(mod.requests, "post", return_value=_resp({"access_token": "tok"})), \
         patch.object(mod.requests, "request", side_effect=lambda *a, **k: next(respuestas)) as m:
        assert mod.deshabilitar_en_keycloak("identityhub", "c", "s", "nadie@empresa.com") == "no_encontrado"
    assert m.call_args.kwargs["params"] == {"username": "nadie@empresa.com", "exact": "true"}
