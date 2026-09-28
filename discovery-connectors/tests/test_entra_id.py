"""RF-10 / HU-09: conector de Microsoft Entra ID. Microsoft Graph se simula (sin red)."""
import importlib.util
import pathlib
from unittest.mock import MagicMock, patch

import pytest

MOD_PATH = pathlib.Path(__file__).resolve().parents[1] / "entra_id.py"


@pytest.fixture
def entra(monkeypatch):
    spec = importlib.util.spec_from_file_location("entra_id", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "TENANT_ID", "tenant-x")
    monkeypatch.setattr(mod, "CLIENT_ID", "client-x")
    monkeypatch.setattr(mod, "CLIENT_SECRET", "secret-x")
    monkeypatch.setattr(mod, "INVENTORY_URL", "http://inventario.test")
    return mod


def _resp(json_data=None, ok=True):
    r = MagicMock(ok=ok)
    r.json.return_value = json_data or {}
    return r


def test_token_sin_variables_termina_con_error(entra, monkeypatch, capsys):
    monkeypatch.setattr(entra, "CLIENT_SECRET", None)
    with pytest.raises(SystemExit) as e:
        entra.obtener_token()
    assert e.value.code == 1
    assert "ENTRA_CLIENT_SECRET" in capsys.readouterr().out


def test_token_usa_client_credentials(entra):
    with patch.object(entra.requests, "post", return_value=_resp({"access_token": "tok"})) as m:
        assert entra.obtener_token() == "tok"
    assert m.call_args.args[0] == "https://login.microsoftonline.com/tenant-x/oauth2/v2.0/token"
    assert m.call_args.kwargs["data"]["grant_type"] == "client_credentials"
    assert m.call_args.kwargs["data"]["scope"] == "https://graph.microsoft.com/.default"


def test_nombre_de_app_usa_cache(entra):
    cache = {}
    with patch.object(entra.requests, "get", return_value=_resp({"displayName": "Canva"})) as m:
        assert entra.obtener_nombre_app("tok", "sp-1", cache) == "Canva"
        assert entra.obtener_nombre_app("tok", "sp-1", cache) == "Canva"
    assert m.call_count == 1  # la segunda vez sale de la caché


def test_nombre_de_app_si_graph_falla_usa_el_id(entra):
    with patch.object(entra.requests, "get", return_value=_resp(ok=False)):
        assert entra.obtener_nombre_app("tok", "sp-9", {}) == "sp-9"


def test_descubrir_apps_formatea_para_el_inventario(entra):
    grants = {"value": [
        {"clientId": "sp-1", "scope": " Mail.Read User.Read "},
        {"clientId": "sp-1", "scope": None},
    ]}

    def fake_get(url, **_):
        return _resp(grants) if url.endswith("oauth2PermissionGrants") else _resp({"displayName": "Canva"})

    with patch.object(entra.requests, "get", side_effect=fake_get) as m:
        apps = entra.descubrir_apps(token="tok")
    assert apps == [
        {"nombre": "Canva", "alcance_oauth": "Mail.Read User.Read", "fecha_ultimo_uso": None},
        {"nombre": "Canva", "alcance_oauth": "", "fecha_ultimo_uso": None},
    ]
    assert m.call_count == 2  # 1 para los grants + 1 para el nombre (el segundo sale de caché)


def test_descubrir_apps_pide_token_si_no_se_pasa(entra):
    with patch.object(entra, "obtener_token", return_value="tok") as t, \
         patch.object(entra.requests, "get", return_value=_resp({"value": []})):
        assert entra.descubrir_apps() == []
    t.assert_called_once()


def test_importar_al_inventario(entra):
    with patch.object(entra.requests, "post", return_value=_resp({"success": True})) as m:
        assert entra.importar_al_inventario([{"nombre": "Canva"}]) == {"success": True}
    assert m.call_args.args[0] == "http://inventario.test/api/discovery/importar"
    assert m.call_args.kwargs["json"] == {"apps": [{"nombre": "Canva"}]}
