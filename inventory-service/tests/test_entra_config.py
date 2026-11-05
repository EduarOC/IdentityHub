"""RF-10 / HU-09: pruebas de la configuración dinámica y sincronización de Microsoft Entra ID."""
from unittest.mock import patch


def test_obtener_config_vacia_por_defecto(client):
    r = client.get("/api/conector/entra-id")
    assert r.status_code == 200
    data = r.get_json()
    assert data["configurado"] is False
    assert data["tiene_secreto"] is False


def test_guardar_config_y_recuperar(client):
    # Guardar
    r = client.post("/api/conector/entra-id", json={
        "tenant_id": "tenant-test-123",
        "client_id": "client-test-456",
        "client_secret": "secret-super-seguro",
    })
    assert r.status_code == 200
    assert r.get_json()["success"] is True

    # Recuperar
    r = client.get("/api/conector/entra-id")
    data = r.get_json()
    assert data["configurado"] is True
    assert data["tenant_id"] == "tenant-test-123"
    assert data["client_id"] == "client-test-456"
    assert data["tiene_secreto"] is True
    assert "client_secret" not in data


def test_guardar_con_campos_vacios_da_error(client):
    r = client.post("/api/conector/entra-id", json={"tenant_id": "", "client_id": ""})
    assert r.status_code == 400
    assert r.get_json()["success"] is False


def test_probar_conexion_exitosa(client, inv):
    with patch.object(inv, "obtener_token_entra", return_value="fake-token-123"):
        r = client.post("/api/conector/entra-id/probar", json={
            "tenant_id": "tenant-1",
            "client_id": "client-1",
            "client_secret": "secret-1",
        })
    assert r.status_code == 200
    assert r.get_json()["success"] is True


def test_probar_conexion_error(client, inv):
    with patch.object(inv, "obtener_token_entra", side_effect=ValueError("Credenciales inválidas")):
        r = client.post("/api/conector/entra-id/probar", json={
            "tenant_id": "tenant-1",
            "client_id": "client-1",
            "client_secret": "secret-1",
        })
    assert r.status_code == 400
    assert "Credenciales inválidas" in r.get_json()["error"]


def test_sincronizar_sin_configurar_retorna_400(client):
    r = client.post("/api/conector/entra-id/sincronizar")
    assert r.status_code == 400
    assert "no está configurado" in r.get_json()["error"]


def test_sincronizar_importa_apps_y_calcula_riesgo(client, inv):
    # 1. Configurar
    client.post("/api/conector/entra-id", json={
        "tenant_id": "tenant-corp",
        "client_id": "client-corp",
        "client_secret": "secret-corp",
    })

    # 2. Simular descubrimiento desde Entra ID
    apps_mock = [
        {"nombre": "Trello Corporate", "alcance_oauth": "Acceso completo a Drive", "fecha_ultimo_uso": None},
        {"nombre": "Grammarly", "alcance_oauth": "Lectura básica", "fecha_ultimo_uso": None},
    ]

    with patch.object(inv, "descubrir_apps_entra", return_value=apps_mock):
        r = client.post("/api/conector/entra-id/sincronizar")

    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert data["total_descubiertas"] == 2

    # Verificar que aparecen en /api/aplicativos/riesgo
    riesgos = client.get("/api/aplicativos/riesgo").get_json()
    nombres = [a["nombre"] for a in riesgos]
    assert "Trello Corporate" in nombres
    assert "Grammarly" in nombres
