"""Captura el panel del inventario en escritorio y móvil con Playwright.

Uso:
    python capturas.py <etiqueta> [--url http://127.0.0.1:5055] [--extremos]

--extremos importa por la API un hallazgo de Shadow IT con nombre extremo y un alcance
que contiene HTML, para ver cómo aguanta la interfaz (y si interpreta HTML).
Solo úsalo contra el servidor local de levantar_panel.sh (SQLite temporal).
"""
import argparse
import json
import os
import pathlib
import sys
import urllib.request

from playwright.sync_api import sync_playwright

DIR = pathlib.Path(__file__).resolve().parents[1] / "capturas"
VISTAS = {"escritorio": {"width": 1440, "height": 900}, "movil": {"width": 390, "height": 844}}


def sembrar_extremos(url):
    if "127.0.0.1" not in url and "localhost" not in url:
        sys.exit("--extremos solo se permite contra el servidor local.")
    nombre = "Aplicación con un nombre extraordinariamente largo que no debería romper nada " * 2
    datos = json.dumps({"apps": [{"nombre": nombre.strip(), "alcance_oauth": "Acceso completo <b>a todo</b>",
                                  "fecha_ultimo_uso": None}]}).encode()
    req = urllib.request.Request(f"{url}/api/discovery/importar", data=datos,
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=10).read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("etiqueta")
    ap.add_argument("--url", default="http://127.0.0.1:5055")
    ap.add_argument("--extremos", action="store_true")
    args = ap.parse_args()

    if args.extremos:
        sembrar_extremos(args.url)

    salida = DIR / args.etiqueta
    salida.mkdir(parents=True, exist_ok=True)
    errores = []
    with sync_playwright() as p:
        navegador = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        for nombre, vista in VISTAS.items():
            pagina = navegador.new_page(viewport=vista, device_scale_factor=1)
            pagina.on("console", lambda m: m.type == "error" and errores.append(m.text))
            pagina.on("pageerror", lambda e: errores.append(str(e)))
            pagina.goto(args.url, wait_until="networkidle")
            pagina.wait_for_timeout(500)
            archivo = salida / f"{nombre}.png"
            pagina.screenshot(path=str(archivo), full_page=True)
            ancho = pagina.evaluate("document.documentElement.scrollWidth")
            desborde = " (¡desplazamiento horizontal!)" if ancho > vista["width"] else ""
            print(f"{archivo}  ancho del documento: {ancho}px{desborde}")
            pagina.close()
        navegador.close()
    if errores:
        print("Errores de JavaScript en la página:")
        for e in errores:
            print("  -", e)


if __name__ == "__main__":
    main()
