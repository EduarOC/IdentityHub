"""Controles sobre los archivos estáticos del panel (regresiones de seguridad y accesibilidad)."""
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[1]
JS = (RAIZ / "static" / "dashboard.js").read_text(encoding="utf-8")
HTML = (RAIZ / "templates" / "dashboard.html").read_text(encoding="utf-8")


def test_panel_no_inserta_html_con_datos_del_servidor():
    # Los nombres pueden venir de Microsoft Entra ID: insertarlos como HTML permite XSS.
    assert "innerHTML" not in JS
    assert "insertAdjacentHTML" not in JS
    assert "outerHTML" not in JS


def test_panel_anuncia_los_mensajes_a_lectores_de_pantalla():
    toast = re.search(r'<output[^>]*id="toast"[^>]*>', HTML).group(0)
    assert 'aria-live="polite"' in toast


def test_tablas_del_panel_tienen_encabezados_con_alcance():
    encabezados = re.findall(r"<th\b[^>]*>", HTML)
    assert encabezados
    assert all('scope="col"' in th for th in encabezados)


def test_detalle_de_usuario_es_un_dialogo_accesible():
    dialogo = re.search(r'<dialog[^>]*id="detalle-usuario"[^>]*>', HTML).group(0)
    assert 'aria-labelledby="detalle-nombre"' in dialogo
    assert 'id="detalle-nombre"' in HTML
    # showModal() da foco atrapado, cierre con Esc y fondo inerte sin código extra.
    assert "showModal()" in JS


def test_detalle_consulta_el_historial_de_accesos():
    assert "/accesos?historial=1" in JS


def test_panel_no_inventa_el_responsable_del_offboarding():
    # El servidor toma el responsable del usuario que inició sesión en el proxy.
    assert "panel de prueba" not in JS
    assert "/api/sesion" in JS


def test_panel_ofrece_cerrar_sesion():
    assert 'href="/logout"' in HTML


def test_panel_no_muestra_textos_de_ejemplo():
    # El inventario se llena con los conectores: nada de "datos de ejemplo" en producción.
    assert "ejemplo" not in HTML.lower()
    assert "diferencial del proyecto" not in HTML


def test_panel_tiene_integraciones_con_formulario_accesible():
    assert 'href="#integraciones"' in HTML
    dialogo = re.search(r'<dialog[^>]*id="config-conector"[^>]*>', HTML).group(0)
    assert 'aria-labelledby="config-titulo"' in dialogo
    # Cada campo va dentro de su <label> y el secreto no se autocompleta ni se muestra.
    for campo in ("config-tenant", "config-cliente", "config-secreto"):
        assert re.search(rf'<label class="campo">\s*<span[^>]*>[^<]+</span>\s*<input id="{campo}"', HTML)
    assert re.search(r'<input id="config-secreto"[^>]*type="password"[^>]*autocomplete="new-password"', HTML)
    assert 'id="config-error" role="alert"' in HTML


def test_panel_usa_la_api_de_conectores():
    for ruta in ("/api/conectores", "/probar", "/sincronizar"):
        assert ruta in JS
