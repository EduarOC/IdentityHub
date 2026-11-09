"""Actividad: línea de tiempo de auditoría de solo lectura, con filtros y exportación a CSV."""
import base64
import csv
import io
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

CUENTA = {"Authorization": "Basic " + base64.b64encode(b"svc:clave").decode()}


@pytest.fixture(autouse=True)
def entorno(monkeypatch, inv):
    monkeypatch.setenv("CONECTORES_CLAVE", "clave")
    monkeypatch.setattr(inv, "ejecutar_en_segundo_plano", lambda funcion: funcion())


def _como(usuario):
    return {**CUENTA, "X-Forwarded-User": usuario}


@pytest.fixture
def protegido(monkeypatch):
    monkeypatch.setenv("BACKEND_SERVICE_USER", "svc")
    monkeypatch.setenv("BACKEND_SERVICE_PASSWORD", "clave")


def _id(client, nombre, cabeceras=None):
    return next(u["id"] for u in client.get("/api/usuarios", headers=cabeceras or {}).get_json()
                if u["nombre"] == nombre)


def _poblar(client, inv, protegido_activo=True):
    """Un administrador conecta Entra ID y sincroniza; otro hace un offboarding."""
    datos = {"tenant_id": "11111111-2222-3333-4444-555555555555",
             "client_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "client_secret": "s"}
    cab_a, cab_b = _como("admin.a@empresa.com"), _como("admin.b@empresa.com")
    client.put("/api/conectores/entra_id", json=datos, headers=cab_a)
    with patch.object(inv.conectores, "probar_entra", return_value="Contoso"):
        client.post("/api/conectores/entra_id/probar", headers=cab_a)
    entra = {"usuarios": [], "aplicativos": [], "asignaciones": [], "concesiones": []}
    with patch.object(inv.conectores, "extraer_entra", return_value=entra):
        client.post("/api/conectores/entra_id/sincronizar", headers=cab_a)
    client.post(f"/api/usuarios/{_id(client, 'Ana Torres', cab_b)}/offboarding", json={}, headers=cab_b)


def test_linea_de_tiempo_completa_y_ordenada(client, con_datos, protegido):
    _poblar(client, con_datos)
    datos = client.get("/api/actividad", headers=CUENTA).get_json()
    acciones = [e["accion"] for e in datos["eventos"]]
    # Del más reciente al más antiguo; el «iniciada» de la sincronización no aparece.
    assert acciones == ["offboarding", "sincronizar", "probar", "configurar"]
    assert datos["responsables"] == ["admin.a@empresa.com", "admin.b@empresa.com"]

    offboarding = datos["eventos"][0]
    assert offboarding["objetivo"] == "Ana Torres"
    assert offboarding["correo"] == "ana@empresa-ejemplo.com"
    assert offboarding["responsable"] == "admin.b@empresa.com"
    assert sorted(offboarding["aplicativos"]) == ["Sistema de Facturación Legacy", "Slack"]
    assert offboarding["resultado_sso"] == "sin_conector"

    sincronizacion = datos["eventos"][1]
    assert sincronizacion["objetivo"] == "Microsoft Entra ID"
    assert sincronizacion["resultado"] == "correcto"
    assert sincronizacion["resumen"]["usuarios"] == 0


def test_filtros_por_accion_responsable_y_fecha(client, con_datos, protegido):
    _poblar(client, con_datos)
    def acciones(consulta):
        return [e["accion"] for e in client.get(f"/api/actividad?{consulta}", headers=CUENTA).get_json()["eventos"]]
    assert acciones("accion=offboarding") == ["offboarding"]
    assert acciones("accion=probar") == ["probar"]
    assert acciones("responsable=admin.b@empresa.com") == ["offboarding"]
    hoy = datetime.now(timezone.utc).date()
    assert len(acciones(f"desde={hoy}&hasta={hoy}")) == 4
    assert acciones(f"desde={hoy + timedelta(days=1)}") == []
    assert acciones(f"hasta={hoy - timedelta(days=1)}") == []
    assert acciones("limite=2") == ["offboarding", "sincronizar"]


@pytest.mark.parametrize("consulta", ["accion=borrar", "desde=07/11/2026", "hasta=mañana", "limite=muchos"])
def test_filtros_invalidos_responden_400(client, consulta):
    r = client.get(f"/api/actividad?{consulta}")
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_limite_se_acota(client, inv):
    assert client.get("/api/actividad?limite=999999").get_json()["limite"] == 1000
    assert client.get("/api/actividad?limite=-5").get_json()["limite"] == 1


def test_sin_cuenta_de_servicio_no_se_ve_la_actividad(client, protegido):
    assert client.get("/api/actividad").status_code == 401
    assert client.get("/api/actividad?formato=csv").status_code == 401


def test_la_actividad_es_de_solo_lectura(client):
    for metodo in ("post", "put", "delete", "patch"):
        assert getattr(client, metodo)("/api/actividad").status_code == 405


def test_exportar_csv(client, con_datos, protegido):
    _poblar(client, con_datos)
    r = client.get("/api/actividad?formato=csv&accion=offboarding", headers=CUENTA)
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert r.headers["Content-Disposition"].startswith('attachment; filename="identityhub-actividad-')
    texto = r.get_data(as_text=True)
    assert texto.startswith("﻿")
    filas = list(csv.reader(io.StringIO(texto.lstrip("﻿"))))
    assert filas[0][:3] == ["fecha", "accion", "responsable"]
    assert len(filas) == 2
    assert filas[1][1:4] == ["offboarding", "admin.b@empresa.com", "Ana Torres"]


def test_csv_neutraliza_formulas(client, inv):
    # Un nombre que viene del tenant no debe ejecutarse como fórmula al abrir el CSV en Excel.
    with inv.SessionLocal() as s:
        u = inv.Usuario(nombre="=HYPERLINK(\"http://malo\")", correo="x@y.com")
        s.add(u)
        s.flush()
        s.add(inv.EventoOffboarding(usuario_id=u.id, aplicativos_revocados="+cmd", responsable="@admin"))
        s.commit()
    filas = list(csv.reader(io.StringIO(client.get("/api/actividad?formato=csv").get_data(as_text=True).lstrip("﻿"))))
    assert filas[1][2] == "'@admin"
    assert filas[1][3] == "'=HYPERLINK(\"http://malo\")"
    assert filas[1][6] == "'+cmd"


def test_resultados_fallidos_se_marcan(client, inv):
    with inv.SessionLocal() as s:
        s.add_all([
            inv.EventoConector(tipo="entra_id", accion="probar", responsable="a", detalle="fallida"),
            inv.EventoConector(tipo="entra_id", accion="sincronizar", responsable="a", detalle="fallida"),
            inv.EventoConector(tipo="keycloak", accion="desconectar", responsable="a", detalle="credenciales eliminadas"),
        ])
        s.commit()
    eventos = {e["accion"]: e for e in client.get("/api/actividad").get_json()["eventos"]}
    assert eventos["probar"]["resultado"] == "fallido"
    assert eventos["sincronizar"]["resultado"] == "fallido"
    assert eventos["desconectar"]["objetivo"] == "Keycloak"
    assert eventos["desconectar"]["detalle"] == "credenciales eliminadas"


def test_offboarding_de_usuario_que_ya_no_existe(client, inv):
    with inv.SessionLocal() as s:
        s.add(inv.EventoOffboarding(usuario_id=999, aplicativos_revocados="", responsable="a"))
        s.commit()
    evento = client.get("/api/actividad").get_json()["eventos"][0]
    assert evento["objetivo"] == "Usuario #999"
    assert evento["aplicativos"] == []


def test_sincronizacion_con_fallo_inesperado_queda_en_la_actividad(client, inv):
    datos = {"tenant_id": "11111111-2222-3333-4444-555555555555",
             "client_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "client_secret": "s"}
    client.put("/api/conectores/entra_id", json=datos)
    with patch.object(inv.conectores, "probar_entra", return_value="Contoso"):
        client.post("/api/conectores/entra_id/probar")
    with patch.object(inv.conectores, "extraer_entra", side_effect=KeyError("x")):
        client.post("/api/conectores/entra_id/sincronizar")
    evento = client.get("/api/actividad?accion=sincronizar").get_json()["eventos"][0]
    assert evento["resultado"] == "fallido"


def test_reinicio_durante_la_sincronizacion_queda_en_la_actividad(client, inv):
    with inv.SessionLocal() as s:
        s.add(inv.Conector(tipo="entra_id", estado="sincronizando"))
        s.commit()
    inv._recuperar_sincronizaciones_interrumpidas()
    evento = client.get("/api/actividad").get_json()["eventos"][0]
    assert evento["responsable"] == "sistema"
    assert evento["resultado"] == "fallido"
    assert evento["detalle"] == "interrumpida"
