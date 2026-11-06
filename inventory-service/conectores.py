"""
IdentityHub - Conectores con proveedores de identidad.

Este módulo solo habla con las APIs externas y con el cifrado; no toca la base de datos.
app.py decide qué guardar con lo que devuelve, así la lógica de Microsoft Graph se puede
probar sin red y sin base.

Microsoft Entra ID usa el flujo client credentials con una app registrada por el
administrador del tenant y el permiso de aplicación Directory.Read.All (solo lectura).
Ver docs/CONECTORES.md para los pasos de registro.
"""
import base64
import hashlib
import os
import re

import requests
from cryptography.fernet import Fernet, InvalidToken

GRAPH = "https://graph.microsoft.com/v1.0"
LOGIN = "https://login.microsoftonline.com"
TIMEOUT = 20
# Tope de páginas por consulta: evita un ciclo infinito si Graph devolviera siempre nextLink.
MAX_PAGINAS = 200

PATRON_GUID = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
# El tenant se puede indicar por su ID o por un dominio verificado (empresa.onmicrosoft.com).
PATRON_DOMINIO = re.compile(r"^(?=.{3,253}$)[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+$")


class ErrorConector(Exception):
    """Error con un mensaje apto para mostrar al administrador (sin detalles internos)."""


# --------------------------------------------------------------------------- cifrado
def _fernet():
    clave = os.environ.get("CONECTORES_CLAVE", "")
    if not clave:
        raise ErrorConector("El servidor no tiene configurada la clave de cifrado (CONECTORES_CLAVE).")
    # Fernet pide 32 bytes en base64: se derivan del valor del entorno, sea cual sea su formato.
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(clave.encode()).digest()))


def cifrar(texto):
    return _fernet().encrypt(texto.encode()).decode()


def descifrar(token):
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ErrorConector("No se pudo leer el secreto guardado (la clave de cifrado cambió). "
                            "Vuelve a ingresar el secreto del cliente.") from exc


# --------------------------------------------------------------------------- validación
def validar_credenciales_entra(tenant_id, client_id, client_secret, secreto_obligatorio):
    """Devuelve un mensaje de error para el formulario, o None si todo es válido."""
    if not isinstance(tenant_id, str) or not (PATRON_GUID.match(tenant_id) or PATRON_DOMINIO.match(tenant_id)):
        return "El Tenant ID debe ser un GUID o un dominio del tenant (empresa.onmicrosoft.com)."
    if not isinstance(client_id, str) or not PATRON_GUID.match(client_id):
        return "El Client ID (Application ID) debe ser un GUID."
    if client_secret is not None and (not isinstance(client_secret, str) or len(client_secret) > 512):
        return "El secreto del cliente no es válido."
    if secreto_obligatorio and not client_secret:
        return "Falta el secreto del cliente."
    return None


# --------------------------------------------------------------------------- Microsoft Graph
def _token(tenant_id, client_id, client_secret):
    try:
        resp = requests.post(
            f"{LOGIN}/{tenant_id}/oauth2/v2.0/token",
            data={"client_id": client_id, "client_secret": client_secret,
                  "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise ErrorConector("No se pudo contactar a Microsoft. Intenta de nuevo en unos minutos.") from exc
    if resp.status_code in (400, 401):
        raise ErrorConector("Microsoft rechazó las credenciales: revisa el Tenant ID, el Client ID "
                            "y que el secreto no haya expirado.")
    if not resp.ok:
        raise ErrorConector(f"Microsoft respondió con un error ({resp.status_code}) al pedir el token.")
    return resp.json()["access_token"]


def _get(token, url, params=None):
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT,
                            headers={"Authorization": f"Bearer {token}", "ConsistencyLevel": "eventual"})
    except requests.RequestException as exc:
        raise ErrorConector("Se perdió la conexión con Microsoft Graph durante la consulta.") from exc
    if resp.status_code == 403:
        raise ErrorConector("Faltan permisos: la app necesita el permiso de aplicación Directory.Read.All "
                            "con consentimiento de administrador.")
    if not resp.ok:
        raise ErrorConector(f"Microsoft Graph respondió con un error ({resp.status_code}).")
    return resp.json()


def _todas_las_paginas(token, url, params=None):
    datos = _get(token, url, params)
    elementos = list(datos.get("value", []))
    for _ in range(MAX_PAGINAS):
        siguiente = datos.get("@odata.nextLink")
        if not siguiente:
            break
        datos = _get(token, siguiente)  # nextLink ya trae los parámetros
        elementos.extend(datos.get("value", []))
    return elementos


def probar_entra(tenant_id, client_id, client_secret):
    """Obtiene un token y lee el nombre del tenant. Devuelve el nombre visible de la organización."""
    token = _token(tenant_id, client_id, client_secret)
    organizaciones = _get(token, f"{GRAPH}/organization", {"$select": "id,displayName"}).get("value", [])
    return organizaciones[0].get("displayName", tenant_id) if organizaciones else tenant_id


def _tipo_sso(service_principal):
    modo = (service_principal.get("preferredSingleSignOnMode") or "").lower()
    if modo in ("saml", "oidc"):
        return "nativo"
    if modo in ("password", "notsupported") or not modo:
        return "ninguno"
    return "proxy"


def extraer_entra(tenant_id, client_id, client_secret):
    """
    Lee del tenant todo lo que el inventario necesita, sin escribir nada en Entra ID:

    - usuarios: miembros del directorio, con su estado (habilitado o no);
    - aplicativos: aplicaciones empresariales integradas (el catálogo gestionado por TI);
    - asignaciones: qué usuario tiene asignada cada aplicación empresarial;
    - concesiones: permisos OAuth delegados (Shadow IT), con el usuario que los otorgó cuando
      fue un consentimiento individual.

    Limitación conocida: las asignaciones hechas a grupos no se expanden a sus miembros.
    """
    token = _token(tenant_id, client_id, client_secret)

    usuarios = [
        {
            "id": u["id"],
            "nombre": (u.get("displayName") or u.get("userPrincipalName") or "").strip(),
            "correo": (u.get("mail") or u.get("userPrincipalName") or "").strip().lower(),
            "activo": bool(u.get("accountEnabled", True)),
        }
        for u in _todas_las_paginas(token, f"{GRAPH}/users", {
            "$select": "id,displayName,mail,userPrincipalName,accountEnabled", "$top": "999"})
        if u.get("id") and (u.get("mail") or u.get("userPrincipalName"))
    ]

    empresariales = _todas_las_paginas(token, f"{GRAPH}/servicePrincipals", {
        "$filter": "tags/any(t:t eq 'WindowsAzureActiveDirectoryIntegratedApp')",
        "$select": "id,appId,displayName,preferredSingleSignOnMode", "$top": "999", "$count": "true"})
    aplicativos = [
        {"id": sp["id"], "nombre": sp.get("displayName") or sp["id"], "sso": _tipo_sso(sp)}
        for sp in empresariales
    ]

    asignaciones = []
    for sp in empresariales:
        for asignacion in _todas_las_paginas(token, f"{GRAPH}/servicePrincipals/{sp['id']}/appRoleAssignedTo", {
                "$select": "principalId,principalType", "$top": "999"}):
            if asignacion.get("principalType") == "User":
                asignaciones.append({"usuario_id": asignacion["principalId"], "aplicativo_id": sp["id"]})

    nombres = {sp["id"]: sp.get("displayName") or sp["id"] for sp in empresariales}
    concesiones = []
    for grant in _todas_las_paginas(token, f"{GRAPH}/oauth2PermissionGrants", {"$top": "999"}):
        cliente = grant.get("clientId")
        if not cliente:
            continue
        if cliente not in nombres:
            datos_sp = _get(token, f"{GRAPH}/servicePrincipals/{cliente}", {"$select": "id,displayName"})
            nombres[cliente] = datos_sp.get("displayName") or cliente
        concesiones.append({
            "aplicativo_id": cliente,
            "nombre": nombres[cliente],
            "alcance": (grant.get("scope") or "").strip(),
            "usuario_id": grant.get("principalId") if grant.get("consentType") == "Principal" else None,
        })

    return {"usuarios": usuarios, "aplicativos": aplicativos,
            "asignaciones": asignaciones, "concesiones": concesiones}
