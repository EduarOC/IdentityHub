"""El inventario solo atiende al auth-proxy (cuenta de servicio) cuando hay clave configurada."""
import base64

import pytest

USUARIO, CLAVE = "cuenta-inventario", "clave-de-prueba"


def _basic(usuario=USUARIO, clave=CLAVE):
    token = base64.b64encode(f"{usuario}:{clave}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def protegido(monkeypatch):
    monkeypatch.setenv("BACKEND_SERVICE_USER", USUARIO)
    monkeypatch.setenv("BACKEND_SERVICE_PASSWORD", CLAVE)


@pytest.mark.parametrize("ruta", ["/", "/api/usuarios", "/api/aplicativos", "/api/sesion"])
def test_sin_credenciales_responde_401(client, protegido, ruta):
    r = client.get(ruta)
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"].startswith("Basic")


def test_offboarding_sin_credenciales_no_modifica_nada(client, con_datos, protegido):
    with con_datos.SessionLocal() as s:
        ana = s.query(con_datos.Usuario).filter_by(nombre="Ana Torres").one().id
    assert client.post(f"/api/usuarios/{ana}/offboarding", json={}).status_code == 401
    with con_datos.SessionLocal() as s:
        assert s.query(con_datos.EventoOffboarding).count() == 0
        assert s.get(con_datos.Usuario, ana).estado == "activo"


def test_clave_incorrecta_responde_401(client, protegido):
    assert client.get("/api/usuarios", headers=_basic(clave="otra")).status_code == 401
    assert client.get("/api/usuarios", headers=_basic(usuario="otro")).status_code == 401


def test_con_la_cuenta_de_servicio_responde(client, protegido):
    assert client.get("/api/usuarios", headers=_basic()).status_code == 200


def test_salud_es_publica(client, protegido):
    r = client.get("/salud")
    assert r.status_code == 200
    assert r.get_json() == {"estado": "ok"}


def test_sin_clave_configurada_no_exige_autenticacion(client, monkeypatch):
    monkeypatch.delenv("BACKEND_SERVICE_PASSWORD", raising=False)
    assert client.get("/api/usuarios").status_code == 200
    assert client.get("/api/sesion").get_json() == {"usuario": None}


def test_sesion_devuelve_el_usuario_del_proxy(client, protegido):
    r = client.get("/api/sesion", headers={**_basic(), "X-Forwarded-User": "ana.torres@identityhub.local"})
    assert r.get_json() == {"usuario": "ana.torres@identityhub.local"}


def test_sin_proxy_el_header_de_usuario_se_ignora(client, monkeypatch):
    # Sin cuenta de servicio cualquiera podría enviar el header: no se le cree.
    monkeypatch.delenv("BACKEND_SERVICE_PASSWORD", raising=False)
    r = client.get("/api/sesion", headers={"X-Forwarded-User": "intruso@x.com"})
    assert r.get_json() == {"usuario": None}


def test_responsable_del_offboarding_es_el_usuario_conectado(client, con_datos, protegido):
    with con_datos.SessionLocal() as s:
        ana = s.query(con_datos.Usuario).filter_by(nombre="Ana Torres").one().id
    r = client.post(f"/api/usuarios/{ana}/offboarding", json={"responsable": "suplantado"},
                    headers={**_basic(), "X-Forwarded-User": "admin.ti@identityhub.local"})
    assert r.status_code == 200
    with con_datos.SessionLocal() as s:
        assert s.query(con_datos.EventoOffboarding).one().responsable == "admin.ti@identityhub.local"
