"""Conectores con proveedores de identidad: configuración, prueba, sincronización y desconexión."""
import base64
import json
from unittest.mock import patch

import pytest

TENANT = "11111111-2222-3333-4444-555555555555"
CLIENTE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SECRETO = "secreto-super-privado"
CUENTA = {"Authorization": "Basic " + base64.b64encode(b"svc:clave").decode(),
          "X-Forwarded-User": "admin.ti@empresa.com"}


@pytest.fixture(autouse=True)
def clave_cifrado(monkeypatch, inv):
    monkeypatch.setenv("CONECTORES_CLAVE", "clave-de-cifrado-de-prueba")
    # La sincronización corre en línea para poder revisar el resultado en la misma prueba.
    monkeypatch.setattr(inv, "ejecutar_en_segundo_plano", lambda funcion: funcion())


@pytest.fixture
def protegido(monkeypatch):
    monkeypatch.setenv("BACKEND_SERVICE_USER", "svc")
    monkeypatch.setenv("BACKEND_SERVICE_PASSWORD", "clave")


def _configurar(client, **cambios):
    datos = {"tenant_id": TENANT, "client_id": CLIENTE, "client_secret": SECRETO, **cambios}
    return client.put("/api/conectores/entra_id", json=datos)


def _conectar(client, inv):
    assert _configurar(client).status_code == 200
    with patch.object(inv.conectores, "probar_entra", return_value="Contoso S.A.S."):
        assert client.post("/api/conectores/entra_id/probar").status_code == 200


def _entra(usuarios=None, aplicativos=None, asignaciones=None, concesiones=None):
    return {
        "usuarios": usuarios if usuarios is not None else [
            {"id": "u1", "nombre": "Laura Gómez", "correo": "laura@contoso.com", "activo": True},
            {"id": "u2", "nombre": "Pedro Ruiz", "correo": "pedro@contoso.com", "activo": False},
        ],
        "aplicativos": aplicativos if aplicativos is not None else [
            {"id": "sp-sf", "nombre": "Salesforce", "sso": "nativo"},
        ],
        "asignaciones": asignaciones if asignaciones is not None else [
            {"usuario_id": "u1", "aplicativo_id": "sp-sf"},
        ],
        "concesiones": concesiones if concesiones is not None else [
            {"aplicativo_id": "sp-canva", "nombre": "Canva", "alcance": "Files.ReadWrite.All", "usuario_id": "u1"},
            {"aplicativo_id": "sp-canva", "nombre": "Canva", "alcance": "User.Read", "usuario_id": None},
        ],
    }


def _sincronizar(client, inv, datos):
    with patch.object(inv.conectores, "extraer_entra", return_value=datos):
        return client.post("/api/conectores/entra_id/sincronizar")


def _entra_id(client):
    return next(c for c in client.get("/api/conectores").get_json() if c["tipo"] == "entra_id")


# ------------------------------------------------------------------ listado y configuración
def test_listado_inicial_muestra_el_catalogo_sin_configurar(client):
    conectores = client.get("/api/conectores").get_json()
    assert [c["tipo"] for c in conectores] == ["entra_id", "google_workspace", "keycloak"]
    entra = conectores[0]
    assert entra["disponible"] is True
    assert entra["estado"] == "desconectado"
    assert entra["tiene_secreto"] is False
    assert conectores[1]["disponible"] is False
    assert conectores[2]["disponible"] is True
    assert entra["sincroniza"] is True
    assert conectores[2]["sincroniza"] is False


def test_configurar_guarda_el_secreto_cifrado_y_nunca_lo_devuelve(client, inv):
    r = _configurar(client)
    assert r.status_code == 200
    assert SECRETO not in r.get_data(as_text=True)
    assert r.get_json()["tiene_secreto"] is True
    assert r.get_json()["estado"] == "pendiente"
    assert SECRETO not in client.get("/api/conectores").get_data(as_text=True)
    with inv.SessionLocal() as s:
        guardado = s.query(inv.Conector).one()
        assert SECRETO not in guardado.secreto_cifrado
        assert inv.conectores.descifrar(guardado.secreto_cifrado) == SECRETO
        assert s.query(inv.EventoConector).filter_by(accion="configurar").count() == 1


def test_configurar_sin_secreto_conserva_el_anterior(client, inv):
    _configurar(client)
    r = _configurar(client, client_secret="", tenant_id="contoso.onmicrosoft.com")
    assert r.status_code == 200
    with inv.SessionLocal() as s:
        guardado = s.query(inv.Conector).one()
        assert guardado.tenant_id == "contoso.onmicrosoft.com"
        assert inv.conectores.descifrar(guardado.secreto_cifrado) == SECRETO


@pytest.mark.parametrize("cambios, mensaje", [
    ({"tenant_id": "no es un tenant"}, "Tenant ID"),
    ({"tenant_id": None}, "Tenant ID"),
    ({"client_id": "123"}, "Client ID"),
    ({"client_id": 5}, "Client ID"),
    ({"client_secret": None}, "secreto"),
    ({"client_secret": "x" * 600}, "secreto"),
    ({"client_secret": ["lista"]}, "secreto"),
])
def test_configurar_con_datos_invalidos_responde_400(client, inv, cambios, mensaje):
    r = _configurar(client, **cambios)
    assert r.status_code == 400
    assert mensaje in r.get_json()["error"]
    with inv.SessionLocal() as s:
        assert s.query(inv.Conector).count() == 0


def test_configurar_sin_cuerpo_responde_400(client):
    assert client.put("/api/conectores/entra_id", data="x", content_type="text/plain").status_code == 400


def test_configurar_sin_clave_de_cifrado_responde_503(client, inv, monkeypatch):
    monkeypatch.delenv("CONECTORES_CLAVE")
    r = _configurar(client)
    assert r.status_code == 503
    assert "CONECTORES_CLAVE" in r.get_json()["error"]
    with inv.SessionLocal() as s:
        assert s.query(inv.Conector).count() == 0


@pytest.mark.parametrize("tipo", ["google_workspace", "inexistente"])
def test_conectores_no_disponibles_responden_404(client, tipo):
    assert client.put(f"/api/conectores/{tipo}", json={}).status_code == 404
    assert client.post(f"/api/conectores/{tipo}/probar").status_code == 404
    assert client.post(f"/api/conectores/{tipo}/sincronizar").status_code == 404
    assert client.delete(f"/api/conectores/{tipo}").status_code == 404


def test_sin_cuenta_de_servicio_no_se_puede_configurar(client, inv, protegido):
    assert _configurar(client).status_code == 401
    assert client.get("/api/conectores").status_code == 401
    with inv.SessionLocal() as s:
        assert s.query(inv.Conector).count() == 0


def test_el_responsable_es_el_usuario_conectado(client, inv, protegido):
    r = client.put("/api/conectores/entra_id", headers=CUENTA,
                   json={"tenant_id": TENANT, "client_id": CLIENTE, "client_secret": SECRETO})
    assert r.status_code == 200
    with inv.SessionLocal() as s:
        assert s.query(inv.Conector).one().actualizado_por == "admin.ti@empresa.com"
        assert s.query(inv.EventoConector).one().responsable == "admin.ti@empresa.com"


# ------------------------------------------------------------------ probar
def test_probar_antes_de_configurar_responde_400(client):
    assert client.post("/api/conectores/entra_id/probar").status_code == 400


def test_probar_correcto_deja_el_conector_conectado(client, inv):
    _configurar(client)
    with patch.object(inv.conectores, "probar_entra", return_value="Contoso S.A.S.") as m:
        r = client.post("/api/conectores/entra_id/probar")
    assert r.status_code == 200
    assert r.get_json()["nombre_tenant"] == "Contoso S.A.S."
    assert m.call_args.args == (TENANT, CLIENTE, SECRETO)
    entra = _entra_id(client)
    assert entra["estado"] == "conectado"
    assert entra["nombre_tenant"] == "Contoso S.A.S."


def test_probar_fallido_guarda_el_error_sin_detalles_internos(client, inv):
    _configurar(client)
    error = inv.conectores.ErrorConector("Microsoft rechazó las credenciales.")
    with patch.object(inv.conectores, "probar_entra", side_effect=error):
        r = client.post("/api/conectores/entra_id/probar")
    assert r.status_code == 502
    assert r.get_json()["error"] == "Microsoft rechazó las credenciales."
    assert _entra_id(client)["estado"] == "error"


# ------------------------------------------------------------------ sincronizar
def test_sincronizar_antes_de_probar_responde_400(client):
    _configurar(client)
    assert client.post("/api/conectores/entra_id/sincronizar").status_code == 400


def test_sincronizar_trae_usuarios_aplicativos_accesos_y_shadow_it(client, inv):
    _conectar(client, inv)
    r = _sincronizar(client, inv, _entra())
    assert r.status_code == 202

    entra = _entra_id(client)
    assert entra["estado"] == "conectado"
    assert entra["ultima_sincronizacion"]
    assert entra["resumen"] == {"usuarios": 2, "aplicativos": 1, "shadow_it": 1,
                                "accesos_nuevos": 2, "accesos_revocados": 0}

    usuarios = {u["correo"]: u for u in client.get("/api/usuarios").get_json()}
    assert usuarios["laura@contoso.com"]["estado"] == "activo"
    assert usuarios["laura@contoso.com"]["accesos_activos"] == 2
    assert usuarios["pedro@contoso.com"]["estado"] == "inactivo"

    catalogo = client.get("/api/aplicativos").get_json()
    assert [(a["nombre"], a["origen"], a["tipo_soporte_sso"]) for a in catalogo] == [("Salesforce", "entra_id", "nativo")]

    shadow = client.get("/api/aplicativos/riesgo").get_json()
    assert len(shadow) == 1
    assert shadow[0]["nombre"] == "Canva"
    assert shadow[0]["alcance_oauth"] == "Files.ReadWrite.All User.Read"
    assert shadow[0]["puntaje_riesgo"] == 85  # permiso amplio (70) + sin fecha de uso (15)


def test_resincronizar_revoca_sin_borrar_y_respeta_el_offboarding(client, inv):
    _conectar(client, inv)
    _sincronizar(client, inv, _entra())
    with inv.SessionLocal() as s:
        laura = s.query(inv.Usuario).filter_by(correo="laura@contoso.com").one().id
    client.post(f"/api/usuarios/{laura}/offboarding", json={})

    # En Entra le reasignan Salesforce a Laura (sigue con acceso) y Pedro desaparece del tenant.
    datos = _entra(usuarios=[{"id": "u1", "nombre": "Laura Gómez", "correo": "laura@contoso.com", "activo": True}],
                   concesiones=[])
    _sincronizar(client, inv, datos)

    with inv.SessionLocal() as s:
        assert s.get(inv.Usuario, laura).estado == "offboarding"
        assert s.query(inv.Usuario).filter_by(correo="pedro@contoso.com").one().estado == "inactivo"
        # El historial completo se conserva: los dos revocados en el offboarding siguen ahí.
        assert s.query(inv.Acceso).filter_by(usuario_id=laura).count() == 3
        assert s.query(inv.EventoOffboarding).count() == 1
    assert _entra_id(client)["resumen"]["accesos_nuevos"] == 1  # Salesforce reaparece en Entra


def test_resincronizar_marca_revocados_los_accesos_que_ya_no_existen(client, inv):
    _conectar(client, inv)
    _sincronizar(client, inv, _entra())
    _sincronizar(client, inv, _entra(asignaciones=[], concesiones=[]))
    assert _entra_id(client)["resumen"]["accesos_revocados"] == 2
    with inv.SessionLocal() as s:
        accesos = s.query(inv.Acceso).all()
        assert len(accesos) == 2
        assert all(a.fecha_revocado for a in accesos)


def test_sincronizar_no_toca_accesos_registrados_a_mano(client, con_datos):
    _conectar(client, con_datos)
    with con_datos.SessionLocal() as s:
        manuales = s.query(con_datos.Acceso).count()
    _sincronizar(client, con_datos, _entra(asignaciones=[], concesiones=[]))
    with con_datos.SessionLocal() as s:
        assert s.query(con_datos.Acceso).filter_by(origen="manual", fecha_revocado=None).count() == manuales


def test_sincronizacion_con_error_de_microsoft_deja_el_mensaje(client, inv):
    _conectar(client, inv)
    error = inv.conectores.ErrorConector("Faltan permisos: Directory.Read.All")
    with patch.object(inv.conectores, "extraer_entra", side_effect=error):
        client.post("/api/conectores/entra_id/sincronizar")
    entra = _entra_id(client)
    assert entra["estado"] == "error"
    assert entra["ultimo_error"] == "Faltan permisos: Directory.Read.All"
    with inv.SessionLocal() as s:
        assert s.query(inv.Usuario).count() == 0


def test_sincronizacion_con_fallo_inesperado_no_expone_detalles(client, inv):
    _conectar(client, inv)
    with patch.object(inv.conectores, "extraer_entra", side_effect=KeyError("detalle interno")):
        client.post("/api/conectores/entra_id/sincronizar")
    entra = _entra_id(client)
    assert entra["estado"] == "error"
    assert "detalle interno" not in entra["ultimo_error"]


def test_no_se_permiten_dos_sincronizaciones_a_la_vez(client, inv):
    _conectar(client, inv)
    assert inv._bloqueo_sincronizacion.acquire(blocking=False)
    try:
        r = client.post("/api/conectores/entra_id/sincronizar")
    finally:
        inv._bloqueo_sincronizacion.release()
    assert r.status_code == 409


def test_mientras_sincroniza_no_se_cambian_credenciales_ni_se_desconecta(client, inv):
    _conectar(client, inv)
    with inv.SessionLocal() as s:
        s.query(inv.Conector).one().estado = "sincronizando"
        s.commit()
    assert _configurar(client).status_code == 409
    assert client.delete("/api/conectores/entra_id").status_code == 409


def test_reinicio_durante_la_sincronizacion_libera_el_estado(client, inv):
    _conectar(client, inv)
    with inv.SessionLocal() as s:
        s.query(inv.Conector).one().estado = "sincronizando"
        s.commit()
    inv._recuperar_sincronizaciones_interrumpidas()
    entra = _entra_id(client)
    assert entra["estado"] == "error"
    assert "reinicio" in entra["ultimo_error"]


# ------------------------------------------------------------------ desconectar
def test_desconectar_borra_credenciales_y_conserva_los_datos(client, inv):
    _conectar(client, inv)
    _sincronizar(client, inv, _entra())
    r = client.delete("/api/conectores/entra_id")
    assert r.status_code == 200
    entra = _entra_id(client)
    assert entra["estado"] == "desconectado"
    assert entra["tiene_secreto"] is False
    assert entra["tenant_id"] is None
    with inv.SessionLocal() as s:
        assert s.query(inv.Usuario).count() == 2
        assert s.query(inv.Acceso).count() == 2
        assert s.query(inv.EventoConector).filter_by(accion="desconectar").count() == 1


def test_desconectar_sin_configurar_responde_404(client):
    assert client.delete("/api/conectores/entra_id").status_code == 404


def test_secreto_ilegible_tras_cambiar_la_clave_pide_ingresarlo_de_nuevo(client, inv, monkeypatch):
    _configurar(client)
    monkeypatch.setenv("CONECTORES_CLAVE", "otra-clave")
    r = client.post("/api/conectores/entra_id/probar")
    assert r.status_code == 502
    assert "Vuelve a ingresar el secreto" in r.get_json()["error"]


# ------------------------------------------------------------------ datos de ejemplo y migración
def test_purgar_retira_solo_los_datos_de_ejemplo(client, con_datos):
    _conectar(client, con_datos)
    _sincronizar(client, con_datos, _entra())
    with con_datos.SessionLocal() as s:
        ana = s.query(con_datos.Usuario).filter_by(correo="ana@empresa-ejemplo.com").one().id
    client.post(f"/api/usuarios/{ana}/offboarding", json={})

    assert con_datos.purgar_datos_ejemplo() > 0
    with con_datos.SessionLocal() as s:
        correos = {u.correo for u in s.query(con_datos.Usuario).all()}
        assert correos == {"laura@contoso.com", "pedro@contoso.com"}
        nombres = {a.nombre for a in s.query(con_datos.Aplicativo).all()}
        assert nombres == {"Salesforce", "Canva"}
        assert s.query(con_datos.EventoOffboarding).count() == 0
        assert s.query(con_datos.Acceso).count() == 2
    assert con_datos.purgar_datos_ejemplo() == 0


def test_preparar_base_siembra_solo_si_se_pide(inv, monkeypatch):
    monkeypatch.setenv("SEMBRAR_DATOS_EJEMPLO", "1")
    inv.preparar_base()
    with inv.SessionLocal() as s:
        assert s.query(inv.Usuario).count() == 2
    monkeypatch.delenv("SEMBRAR_DATOS_EJEMPLO")
    inv.preparar_base()
    with inv.SessionLocal() as s:
        assert s.query(inv.Usuario).count() == 0


def test_migracion_agrega_columnas_a_una_base_existente(inv):
    from sqlalchemy import inspect, text
    with inv.engine.begin() as c:
        c.execute(text("ALTER TABLE accesos DROP COLUMN origen"))
        c.execute(text("ALTER TABLE usuarios DROP COLUMN id_externo"))
    inv.init_db()
    columnas = {col["name"] for col in inspect(inv.engine).get_columns("accesos")}
    assert "origen" in columnas
    assert "id_externo" in {col["name"] for col in inspect(inv.engine).get_columns("usuarios")}


def test_resumen_guardado_es_json_valido(client, inv):
    _conectar(client, inv)
    _sincronizar(client, inv, _entra())
    with inv.SessionLocal() as s:
        evento = s.query(inv.EventoConector).filter_by(accion="sincronizar").order_by(inv.EventoConector.id.desc()).first()
        assert json.loads(evento.detalle)["usuarios"] == 2
