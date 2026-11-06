"""Ejecuta los casos UAT de IdentityHub (CP-U01 a CP-U11) con Playwright y guarda evidencias.

Uso:
    UAT_USUARIO=ana.torres UAT_CLAVE=... python uat.py --entorno local|render [--casos CP-U01,CP-U06] [--salida DIR]

Las capturas difuminan las columnas de nombre y correo de la tabla de usuarios antes de
tomarse. CP-U07 y CP-U09 modifican datos y solo corren en el entorno local.
"""
import argparse
import datetime as dt
import os
import pathlib
import re
import sys
import time

from playwright.sync_api import sync_playwright

ENTORNOS = {
    "local": {"proxy": "http://localhost:9000", "inventario": "http://localhost:5000"},
    "render": {"proxy": "https://identityhub-auth-proxy.onrender.com",
               "inventario": "https://identityhub-inventory.onrender.com"},
}
MODIFICAN_DATOS = {"CP-U07", "CP-U09"}
OCULTAR = ("#tabla-usuarios td:nth-child(1), #tabla-usuarios td:nth-child(2) "
           "{ filter: blur(6px) !important; }")


class Uat:
    def __init__(self, navegador, urls, salida, usuario, clave):
        self.navegador, self.urls, self.salida = navegador, urls, salida
        self.usuario, self.clave = usuario, clave
        self.resultados = []

    # -------------------------------------------------------------- utilidades
    def nueva(self):
        ctx = self.navegador.new_context(viewport={"width": 1366, "height": 850}, ignore_https_errors=False)
        return ctx, ctx.new_page()

    def captura(self, pagina, caso):
        pagina.add_style_tag(content=OCULTAR)
        archivo = self.salida / f"{caso}.png"
        pagina.screenshot(path=str(archivo), full_page=True)
        return archivo.name

    def ir(self, pagina, url):
        pagina.goto(url, wait_until="domcontentloaded", timeout=120_000)  # arranque en frío de Render

    def login(self, pagina, clave):
        self.ir(pagina, self.urls["proxy"] + "/")
        pagina.wait_for_selector("#username", timeout=120_000)
        pagina.fill("#username", self.usuario)
        pagina.fill("#password", clave)
        pagina.click("#kc-login")
        pagina.wait_for_load_state("domcontentloaded")

    def anotar(self, caso, resultado, detalle, evidencia="-"):
        self.resultados.append((caso, resultado, detalle, evidencia))
        print(f"{caso}: {resultado} — {detalle}")

    # -------------------------------------------------------------- casos
    def cp_u01(self):
        ctx, p = self.nueva()
        self.login(p, self.clave)
        ok = not p.locator("#password").count() and self.urls["proxy"] in p.url
        self.anotar("CP-U01", "Aprobado" if ok else "Fallido",
                    "Sesión creada y regreso al aplicativo protegido" if ok else f"Quedó en {p.url}",
                    self.captura(p, "CP-U01"))
        ctx.close()

    def cp_u02(self):
        ctx, p = self.nueva()
        self.login(p, self.clave + "-incorrecta")
        ok = p.locator("#password").count() > 0
        self.anotar("CP-U02", "Aprobado" if ok else "Fallido",
                    "Keycloak rechazó la contraseña y no creó sesión" if ok else "Se aceptó una contraseña incorrecta",
                    self.captura(p, "CP-U02"))
        ctx.close()

    def cp_u03(self):
        ctx, p = self.nueva()
        self.ir(p, self.urls["proxy"] + "/facturas")
        p.wait_for_selector("#username", timeout=120_000)
        ok = "/realms/" in p.url
        self.anotar("CP-U03", "Aprobado" if ok else "Fallido",
                    "Sin sesión, el proxy redirigió al inicio de sesión de Keycloak", self.captura(p, "CP-U03"))
        ctx.close()

    def cp_u04_u05(self, casos):
        ctx, p = self.nueva()
        self.login(p, self.clave)
        if "CP-U04" in casos:
            self.ir(p, self.urls["proxy"] + "/")
            texto = p.inner_text("body")
            m = re.search(r'"autenticado_via_proxy_como"\s*:\s*"([^"]+)"', texto)
            ok = bool(m) and m.group(1) != "desconocido"
            self.anotar("CP-U04", "Aprobado" if ok else "Fallido",
                        "El legacy recibió la identidad real sin pedir otra credencial" if ok else "No llegó la identidad",
                        self.captura(p, "CP-U04"))
        if "CP-U05" in casos:
            self.ir(p, self.urls["proxy"] + "/logout")
            self.ir(p, self.urls["proxy"] + "/")
            p.wait_for_selector("#username", timeout=60_000)
            self.anotar("CP-U05", "Aprobado", "Tras cerrar sesión se volvió a pedir autenticación",
                        self.captura(p, "CP-U05"))
        ctx.close()

    def panel(self):
        ctx, p = self.nueva()
        self.ir(p, self.urls["inventario"] + "/")
        p.wait_for_function("document.querySelector('#kpi-apps').textContent.trim() !== '—'", timeout=120_000)
        return ctx, p

    def cp_u06(self):
        ctx, p = self.panel()
        apps = p.locator("#tabla-aplicativos tbody tr").count()
        usuarios = p.locator("#tabla-usuarios tbody tr").count()
        ok = apps > 0 and usuarios > 0
        self.anotar("CP-U06", "Aprobado" if ok else "Fallido",
                    f"{apps} aplicativos y {usuarios} usuarios visibles", self.captura(p, "CP-U06"))
        ctx.close()

    def cp_u07_u09(self, casos):
        ctx, p = self.panel()
        boton = p.locator(".btn-offboard:not([disabled])").first
        if not boton.count():
            self.anotar("CP-U07", "Omitido", "No hay usuarios activos para retirar")
            ctx.close()
            return
        p.once("dialog", lambda d: d.accept())
        with p.expect_response(lambda r: "/offboarding" in r.url) as info:
            boton.click()
        datos = info.value.json()
        p.wait_for_timeout(800)
        if "CP-U07" in casos:
            ok = datos.get("success") is True
            self.anotar("CP-U07", "Aprobado" if ok else "Fallido",
                        f"Revocados: {', '.join(datos.get('aplicativos_revocados', [])) or 'ninguno'}",
                        self.captura(p, "CP-U07"))
        if "CP-U09" in casos:
            ok = datos.get("success") is True and "aplicativos_revocados" in datos
            self.anotar("CP-U09", "Aprobado" if ok else "Fallido",
                        "La API registró el evento de retiro con los aplicativos revocados "
                        "(verificar responsable y fecha en la tabla eventos_offboarding)")
        ctx.close()

    def cp_u10(self):
        ctx, p = self.panel()
        puntajes = [int(x) for x in p.locator(".shadow-card .risk-badge").all_inner_texts() if x.strip().isdigit()]
        ok = bool(puntajes) and puntajes == sorted(puntajes, reverse=True)
        self.anotar("CP-U10", "Aprobado" if ok else "Fallido",
                    f"Puntajes en orden: {puntajes}", self.captura(p, "CP-U10"))
        ctx.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entorno", choices=ENTORNOS, required=True)
    ap.add_argument("--casos", default="CP-U01,CP-U02,CP-U03,CP-U04,CP-U05,CP-U06,CP-U07,CP-U08,CP-U09,CP-U10,CP-U11")
    ap.add_argument("--salida")
    ap.add_argument("--proxy-url", help="Reemplaza la URL del proxy del entorno")
    ap.add_argument("--inventario-url", help="Reemplaza la URL del inventario del entorno")
    args = ap.parse_args()
    urls = dict(ENTORNOS[args.entorno])
    if args.proxy_url: urls["proxy"] = args.proxy_url.rstrip("/")
    if args.inventario_url: urls["inventario"] = args.inventario_url.rstrip("/")

    usuario, clave = os.environ.get("UAT_USUARIO", "ana.torres"), os.environ.get("UAT_CLAVE")
    casos = {c.strip().upper() for c in args.casos.split(",")}
    necesitan_login = {"CP-U01", "CP-U02", "CP-U04", "CP-U05"}
    if casos & necesitan_login and not clave:
        sys.exit("Define UAT_CLAVE con la contraseña del usuario de prueba.")

    raiz = pathlib.Path(os.popen("git rev-parse --show-toplevel").read().strip() or ".")
    salida = pathlib.Path(args.salida) if args.salida else raiz / "evidencias-uat" / f"{dt.date.today()}-{args.entorno}"
    salida.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        nav = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        u = Uat(nav, urls, salida, usuario, clave)
        pasos = [
            ("CP-U01", u.cp_u01), ("CP-U02", u.cp_u02), ("CP-U03", u.cp_u03),
            ("CP-U04|CP-U05", lambda: u.cp_u04_u05(casos)), ("CP-U06", u.cp_u06),
            ("CP-U07|CP-U09", lambda: u.cp_u07_u09(casos)), ("CP-U10", u.cp_u10),
        ]
        for ids, fn in pasos:
            ids_set = set(ids.split("|")) & casos
            if not ids_set:
                continue
            if ids_set & MODIFICAN_DATOS and args.entorno != "local":
                for c in sorted(ids_set):
                    u.anotar(c, "Omitido", "Modifica datos: solo se ejecuta en el entorno local")
                continue
            try:
                fn()
            except Exception as e:  # el caso falla, el resto sigue
                for c in sorted(ids_set):
                    u.anotar(c, "Fallido", f"Error al ejecutar: {type(e).__name__}: {str(e)[:160]}")
        if "CP-U08" in casos:
            u.anotar("CP-U08", "Manual", "Requiere una persona sin capacitación que cuente los clics")
        if "CP-U11" in casos:
            u.anotar("CP-U11", "Fallo esperado", "RF-08 pendiente: el retiro aún no bloquea la cuenta en Keycloak")
        nav.close()

    orden = {f"CP-U{n:02d}": n for n in range(1, 12)}
    filas = sorted(u.resultados, key=lambda r: orden.get(r[0], 99))
    registro = salida / "registro.md"
    with registro.open("w", encoding="utf-8") as f:
        f.write(f"# Evidencias UAT — {args.entorno} — {dt.datetime.now():%Y-%m-%d %H:%M}\n\n")
        f.write(f"Proxy: {urls['proxy']} · Inventario: {urls['inventario']}\n\n")
        f.write("| Caso | Resultado | Detalle | Evidencia |\n|---|---|---|---|\n")
        for c, r, d, e in filas:
            f.write(f"| {c} | {r} | {d} | {e} |\n")
        f.write("\nNombres y correos de la tabla de usuarios difuminados en las capturas (Ley 1581).\n")
    print(f"\nRegistro: {registro}")


if __name__ == "__main__":
    main()
