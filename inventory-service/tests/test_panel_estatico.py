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
    toast = re.search(r'<div[^>]*id="toast"[^>]*>', HTML).group(0)
    assert 'aria-live="polite"' in toast


def test_tablas_del_panel_tienen_encabezados_con_alcance():
    encabezados = re.findall(r"<th\b[^>]*>", HTML)
    assert encabezados
    assert all('scope="col"' in th for th in encabezados)
