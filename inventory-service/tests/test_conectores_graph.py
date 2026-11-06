"""conectores.py: cifrado, validación y lectura de Microsoft Graph (simulada, sin red)."""
from unittest.mock import MagicMock, patch

import pytest
import requests

import conectores as mod

T, C = "11111111-2222-3333-4444-555555555555", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _resp(json_data=None, status=200):
    r = MagicMock(status_code=status, ok=200 <= status < 300)
    r.json.return_value = json_data or {}
    return r


@pytest.fixture(autouse=True)
def clave(monkeypatch):
    monkeypatch.setenv("CONECTORES_CLAVE", "clave")


def test_cifrar_y_descifrar(monkeypatch):
    token = mod.cifrar("s3creto")
    assert "s3creto" not in token
    assert mod.descifrar(token) == "s3creto"
    monkeypatch.setenv("CONECTORES_CLAVE", "otra")
    with pytest.raises(mod.ErrorConector):
        mod.descifrar(token)


def test_sin_clave_no_cifra(monkeypatch):
    monkeypatch.delenv("CONECTORES_CLAVE")
    with pytest.raises(mod.ErrorConector):
        mod.cifrar("x")


@pytest.mark.parametrize("tenant, cliente, secreto, obligatorio, valido", [
    (T, C, "s", True, True),
    ("contoso.onmicrosoft.com", C, None, False, True),
    ("contoso", C, "s", True, False),
    (T, "x", "s", True, False),
    (T, C, None, True, False),
])
def test_validar_credenciales(tenant, cliente, secreto, obligatorio, valido):
    assert (mod.validar_credenciales_entra(tenant, cliente, secreto, obligatorio) is None) is valido


@pytest.mark.parametrize("status, texto", [(401, "rechazó"), (400, "rechazó"), (500, "500")])
def test_token_con_error(status, texto):
    with patch.object(mod.requests, "post", return_value=_resp(status=status)):
        with pytest.raises(mod.ErrorConector, match=texto):
            mod._token(T, C, "s")


def test_token_sin_red():
    with patch.object(mod.requests, "post", side_effect=requests.ConnectionError("x")):
        with pytest.raises(mod.ErrorConector, match="contactar"):
            mod._token(T, C, "s")


def test_get_sin_permisos_y_con_error():
    with patch.object(mod.requests, "get", return_value=_resp(status=403)):
        with pytest.raises(mod.ErrorConector, match="Directory.Read.All"):
            mod._get("tok", "https://graph")
    with patch.object(mod.requests, "get", return_value=_resp(status=503)):
        with pytest.raises(mod.ErrorConector, match="503"):
            mod._get("tok", "https://graph")
    with patch.object(mod.requests, "get", side_effect=requests.Timeout("x")):
        with pytest.raises(mod.ErrorConector, match="conexión"):
            mod._get("tok", "https://graph")


def test_paginacion_sigue_next_link():
    paginas = [_resp({"value": [1, 2], "@odata.nextLink": "https://graph/p2"}), _resp({"value": [3]})]
    with patch.object(mod.requests, "get", side_effect=paginas) as m:
        assert mod._todas_las_paginas("tok", "https://graph/p1") == [1, 2, 3]
    assert m.call_args.args[0] == "https://graph/p2"


def test_probar_devuelve_el_nombre_del_tenant():
    with patch.object(mod.requests, "post", return_value=_resp({"access_token": "tok"})), \
         patch.object(mod.requests, "get", return_value=_resp({"value": [{"displayName": "Contoso"}]})):
        assert mod.probar_entra(T, C, "s") == "Contoso"
    with patch.object(mod.requests, "post", return_value=_resp({"access_token": "tok"})), \
         patch.object(mod.requests, "get", return_value=_resp({"value": []})):
        assert mod.probar_entra(T, C, "s") == T


@pytest.mark.parametrize("modo, esperado", [("saml", "nativo"), ("oidc", "nativo"), ("password", "ninguno"),
                                            (None, "ninguno"), ("integratedWindowsAuth", "proxy")])
def test_tipo_sso(modo, esperado):
    assert mod._tipo_sso({"preferredSingleSignOnMode": modo}) == esperado


def test_extraer_entra_arma_usuarios_aplicativos_asignaciones_y_concesiones():
    respuestas = {
        "/users": {"value": [
            {"id": "u1", "displayName": "Laura", "mail": "Laura@Contoso.com", "accountEnabled": True},
            {"id": "u2", "displayName": "Invitado", "userPrincipalName": "inv#EXT#@contoso.com", "accountEnabled": False},
            {"id": "u3", "displayName": "Sin correo"},
        ]},
        "/servicePrincipals": {"value": [{"id": "sp1", "displayName": "Salesforce", "preferredSingleSignOnMode": "saml"}]},
        "/servicePrincipals/sp1/appRoleAssignedTo": {"value": [
            {"principalId": "u1", "principalType": "User"}, {"principalId": "g1", "principalType": "Group"}]},
        "/oauth2PermissionGrants": {"value": [
            {"clientId": "sp1", "scope": " User.Read ", "consentType": "AllPrincipals"},
            {"clientId": "sp9", "scope": "Mail.Read", "consentType": "Principal", "principalId": "u1"},
            {"scope": "sin cliente"},
        ]},
        "/servicePrincipals/sp9": {"displayName": "App externa"},
    }

    def falso_get(url, params=None, timeout=None, headers=None):
        assert timeout
        assert headers["Authorization"] == "Bearer tok"
        return _resp(respuestas[url.replace(mod.GRAPH, "")])

    with patch.object(mod.requests, "post", return_value=_resp({"access_token": "tok"})), \
         patch.object(mod.requests, "get", side_effect=falso_get):
        datos = mod.extraer_entra(T, C, "s")

    assert datos["usuarios"] == [
        {"id": "u1", "nombre": "Laura", "correo": "laura@contoso.com", "activo": True},
        {"id": "u2", "nombre": "Invitado", "correo": "inv#ext#@contoso.com", "activo": False},
    ]
    assert datos["aplicativos"] == [{"id": "sp1", "nombre": "Salesforce", "sso": "nativo"}]
    assert datos["asignaciones"] == [{"usuario_id": "u1", "aplicativo_id": "sp1"}]
    assert datos["concesiones"] == [
        {"aplicativo_id": "sp1", "nombre": "Salesforce", "alcance": "User.Read", "usuario_id": None},
        {"aplicativo_id": "sp9", "nombre": "App externa", "alcance": "Mail.Read", "usuario_id": "u1"},
    ]
