"""RF-10 / HU-09: importación de aplicativos descubiertos (Shadow IT)."""


def test_importar_calcula_riesgo_y_marca_origen(client, inv):
    r = client.post("/api/discovery/importar", json={"apps": [
        {"nombre": "Canva", "alcance_oauth": "Acceso completo a Drive", "fecha_ultimo_uso": None},
    ]})
    assert r.status_code == 200
    assert r.get_json()["importados"] == [{"nombre": "Canva", "puntaje_riesgo": 85}]
    lista = client.get("/api/aplicativos/riesgo").get_json()
    assert lista[0]["nombre"] == "Canva" and lista[0]["fecha_ultimo_uso"] is None
    # Los descubiertos no se mezclan con el catálogo manual.
    assert client.get("/api/aplicativos").get_json() == []


def test_importar_con_fecha(client):
    client.post("/api/discovery/importar", json={"apps": [
        {"nombre": "Notion", "alcance_oauth": "read", "fecha_ultimo_uso": "2020-01-01T00:00:00+00:00"},
    ]})
    app = client.get("/api/aplicativos/riesgo").get_json()[0]
    assert app["puntaje_riesgo"] == 50
    assert app["fecha_ultimo_uso"].startswith("2020-01-01")


def test_importar_dos_veces_actualiza_sin_duplicar(client):
    client.post("/api/discovery/importar", json={"apps": [{"nombre": "Zoom", "alcance_oauth": "read"}]})
    client.post("/api/discovery/importar", json={"apps": [{"nombre": "Zoom", "alcance_oauth": "full"}]})
    lista = client.get("/api/aplicativos/riesgo").get_json()
    assert len(lista) == 1
    assert lista[0]["alcance_oauth"] == "full"


def test_misma_app_repetida_en_un_envio_no_se_duplica(client):
    # HU-09, escenario 2: varios empleados autorizaron el mismo aplicativo.
    client.post("/api/discovery/importar", json={"apps": [
        {"nombre": "Miro", "alcance_oauth": "read"}, {"nombre": "Miro", "alcance_oauth": "read"},
    ]})
    assert len(client.get("/api/aplicativos/riesgo").get_json()) == 1


def test_entradas_sin_nombre_se_ignoran(client):
    r = client.post("/api/discovery/importar", json={"apps": [{"alcance_oauth": "read"}, {"nombre": "Trello"}]})
    assert [a["nombre"] for a in r.get_json()["importados"]] == ["Trello"]


def test_importar_lista_vacia_es_error(client):
    r = client.post("/api/discovery/importar", json={"apps": []})
    assert r.status_code == 400 and r.get_json()["success"] is False


def test_importar_formato_invalido_es_error(client):
    assert client.post("/api/discovery/importar", json={"apps": "no-es-lista"}).status_code == 400
    assert client.post("/api/discovery/importar", json={}).status_code == 400


def test_importar_sin_cuerpo_json_responde_json(client):
    r = client.post("/api/discovery/importar", data="x", content_type="text/plain")
    assert r.status_code == 400 and r.is_json
