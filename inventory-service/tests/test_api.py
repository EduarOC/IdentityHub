"""Endpoints del servicio de inventario (RF-05, RF-06, RF-07, RF-10, RF-12, RF-13)."""


def test_panel_se_renderiza(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"<html" in r.data.lower()


def test_listar_usuarios_vacio(client):
    assert client.get("/api/usuarios").get_json() == []


def test_listar_usuarios_con_accesos(client, con_datos):
    usuarios = {u["correo"]: u for u in client.get("/api/usuarios").get_json()}
    assert usuarios["ana@empresa-ejemplo.com"]["accesos_activos"] == 2
    assert usuarios["ana@empresa-ejemplo.com"]["estado"] == "activo"


def test_catalogo_solo_incluye_aplicativos_manuales(client, con_datos):
    apps = client.get("/api/aplicativos").get_json()
    assert {a["nombre"] for a in apps} == {"Slack", "Sistema de Facturación Legacy", "CRM Interno"}
    assert all({"tipo_soporte_sso", "costo_licencia_mensual"} <= a.keys() for a in apps)


def test_accesos_de_usuario(client, con_datos):
    ana = next(u for u in client.get("/api/usuarios").get_json() if u["nombre"] == "Ana Torres")
    accesos = client.get(f"/api/usuarios/{ana['id']}/accesos").get_json()
    assert len(accesos) == 2
    assert all("fecha_otorgado" in a for a in accesos)


def test_sembrar_datos_no_duplica(con_datos):
    con_datos.sembrar_datos_ejemplo()  # segunda vez: no debe volver a insertar
    s = con_datos.SessionLocal()
    try:
        assert s.query(con_datos.Aplicativo).count() == 6
    finally:
        s.close()


def test_riesgo_ordenado_descendente(client, con_datos):
    puntajes = [a["puntaje_riesgo"] for a in client.get("/api/aplicativos/riesgo").get_json()]
    assert len(puntajes) == 3
    assert puntajes == sorted(puntajes, reverse=True)
