"""RF-07 / HU-06 / HU-08: offboarding en un solo paso con registro de auditoría."""


def _id_de(client, nombre):
    return next(u["id"] for u in client.get("/api/usuarios").get_json() if u["nombre"] == nombre)


def test_offboarding_revoca_todos_los_accesos(client, con_datos):
    ana = _id_de(client, "Ana Torres")
    r = client.post(f"/api/usuarios/{ana}/offboarding", json={"responsable": "admin.ti"})
    body = r.get_json()
    assert r.status_code == 200
    assert body["success"] is True
    assert set(body["aplicativos_revocados"]) == {"Slack", "Sistema de Facturación Legacy"}
    assert client.get(f"/api/usuarios/{ana}/accesos").get_json() == []

    usuario = next(u for u in client.get("/api/usuarios").get_json() if u["id"] == ana)
    assert usuario["estado"] == "offboarding"


def test_offboarding_deja_evento_de_auditoria(client, con_datos):
    ana = _id_de(client, "Ana Torres")
    client.post(f"/api/usuarios/{ana}/offboarding", json={"responsable": "admin.ti"})
    s = con_datos.SessionLocal()
    try:
        evento = s.query(con_datos.EventoOffboarding).filter_by(usuario_id=ana).one()
        assert evento.responsable == "admin.ti"
        assert "Slack" in evento.aplicativos_revocados
        assert evento.fecha is not None
    finally:
        s.close()


def test_offboarding_no_afecta_a_otros_usuarios(client, con_datos):
    ana, carlos = _id_de(client, "Ana Torres"), _id_de(client, "Carlos Ruiz")
    client.post(f"/api/usuarios/{ana}/offboarding", json={})
    assert len(client.get(f"/api/usuarios/{carlos}/accesos").get_json()) == 2


def test_offboarding_sin_responsable_queda_desconocido(client, con_datos):
    ana = _id_de(client, "Ana Torres")
    client.post(f"/api/usuarios/{ana}/offboarding")
    s = con_datos.SessionLocal()
    try:
        assert s.query(con_datos.EventoOffboarding).one().responsable == "desconocido"
    finally:
        s.close()


def test_offboarding_usuario_sin_accesos(client, con_datos):
    ana = _id_de(client, "Ana Torres")
    client.post(f"/api/usuarios/{ana}/offboarding", json={})
    r = client.post(f"/api/usuarios/{ana}/offboarding", json={})
    assert r.status_code == 200
    assert r.get_json()["aplicativos_revocados"] == []


def test_offboarding_usuario_inexistente(client, con_datos):
    r = client.post("/api/usuarios/9999/offboarding", json={})
    assert r.status_code == 404
    assert r.get_json()["error"] == "Usuario no encontrado"


def test_offboarding_indica_que_keycloak_es_simulado(client, con_datos):
    # RF-08 sigue pendiente: la API lo advierte explícitamente y la prueba lo deja registrado.
    ana = _id_de(client, "Ana Torres")
    nota = client.post(f"/api/usuarios/{ana}/offboarding", json={}).get_json()["nota"]
    assert "Keycloak" in nota


def test_offboarding_sin_cuerpo_json_responde_json(client, con_datos):
    # Regresión: antes, sin cuerpo JSON, Flask respondía 415 con una página HTML.
    ana = _id_de(client, "Ana Torres")
    r = client.post(f"/api/usuarios/{ana}/offboarding", data="", content_type="text/plain")
    assert r.status_code == 200
    assert r.is_json
