"""
IdentityHub - Conectores con proveedores de identidad.

Este módulo solo habla con las APIs externas y con el cifrado; no toca la base de datos.
app.py decide qué guardar con lo que devuelve, así la lógica de Microsoft Graph se puede
probar sin red y sin base.

Microsoft Entra ID usa el flujo client credentials con una app registrada por el
administrador del tenant y tres permisos de aplicación de solo lectura, los mínimos para lo que
se consulta (PERMISOS_ENTRA). Directory.Read.All también sirve, pero lee todo el directorio.
Ver docs/CONECTORES.md para los pasos de registro.
"""
import base64
import hashlib
import os
import re
from urllib.parse import quote

import requests
from cryptography.fernet import Fernet, InvalidToken

GRAPH = "https://graph.microsoft.com/v1.0"
LOGIN = "https://login.microsoftonline.com"
TIMEOUT = 20
# Permisos de aplicación de Microsoft Graph que necesita el conector, uno por tipo de consulta.
# Mínimo privilegio (ASVS V1.4.3): no se pide Directory.Read.All, que abarca grupos, dispositivos,
# roles y el resto del directorio.
PERMISO_USUARIOS = "User.Read.All"
PERMISO_APLICACIONES = "Application.Read.All"
PERMISO_CONCESIONES = "DelegatedPermissionGrant.Read.All"
PERMISOS_ENTRA = (PERMISO_USUARIOS, PERMISO_APLICACIONES, PERMISO_CONCESIONES)

# Parámetros OData de Microsoft Graph.
SELECT, TOP, MAXIMO = "$select", "$top", "999"
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


def _get(token, url, params=None, permiso=None):
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT,
                            headers={"Authorization": f"Bearer {token}", "ConsistencyLevel": "eventual"})
    except requests.RequestException as exc:
        raise ErrorConector("Se perdió la conexión con Microsoft Graph durante la consulta.") from exc
    if resp.status_code == 403:
        falta = permiso or ", ".join(PERMISOS_ENTRA)
        raise ErrorConector(f"Faltan permisos: la app necesita el permiso de aplicación {falta} "
                            "con consentimiento de administrador.")
    if not resp.ok:
        raise ErrorConector(f"Microsoft Graph respondió con un error ({resp.status_code}).")
    return resp.json()


def _todas_las_paginas(token, url, params=None, permiso=None):
    datos = _get(token, url, params, permiso)
    elementos = list(datos.get("value", []))
    for _ in range(MAX_PAGINAS):
        siguiente = datos.get("@odata.nextLink")
        if not siguiente:
            break
        datos = _get(token, siguiente, permiso=permiso)  # nextLink ya trae los parámetros
        elementos.extend(datos.get("value", []))
    return elementos


def probar_entra(tenant_id, client_id, client_secret):
    """Obtiene un token y comprueba cada permiso con una consulta mínima, para que un permiso
    faltante se detecte al conectar y no a mitad de la sincronización. Devuelve el nombre del
    tenant, o su ID si la app no puede leer los datos de la organización (no hace falta)."""
    token = _token(tenant_id, client_id, client_secret)
    for ruta, permiso in (("/users", PERMISO_USUARIOS), ("/servicePrincipals", PERMISO_APLICACIONES),
                          ("/oauth2PermissionGrants", PERMISO_CONCESIONES)):
        _get(token, f"{GRAPH}{ruta}", {TOP: "1"}, permiso)
    try:
        organizaciones = _get(token, f"{GRAPH}/organization", {SELECT: "id,displayName"}).get("value", [])
    except ErrorConector:
        organizaciones = []
    return organizaciones[0].get("displayName", tenant_id) if organizaciones else tenant_id


def _tipo_sso(service_principal):
    modo = (service_principal.get("preferredSingleSignOnMode") or "").lower()
    if modo in ("saml", "oidc"):
        return "nativo"
    if modo in ("password", "notsupported") or not modo:
        return "ninguno"
    return "proxy"


def _leer_usuarios(token):
    return [
        {
            "id": u["id"],
            "nombre": (u.get("displayName") or u.get("userPrincipalName") or "").strip(),
            "correo": (u.get("mail") or u.get("userPrincipalName") or "").strip().lower(),
            "activo": bool(u.get("accountEnabled", True)),
        }
        for u in _todas_las_paginas(token, f"{GRAPH}/users", {
            SELECT: "id,displayName,mail,userPrincipalName,accountEnabled", TOP: MAXIMO}, PERMISO_USUARIOS)
        if u.get("id") and (u.get("mail") or u.get("userPrincipalName"))
    ]


def _leer_empresariales(token):
    return _todas_las_paginas(token, f"{GRAPH}/servicePrincipals", {
        "$filter": "tags/any(t:t eq 'WindowsAzureActiveDirectoryIntegratedApp')",
        SELECT: "id,appId,displayName,preferredSingleSignOnMode", TOP: MAXIMO, "$count": "true"},
        PERMISO_APLICACIONES)


def _leer_asignaciones(token, empresariales):
    return [
        {"usuario_id": asignacion["principalId"], "aplicativo_id": sp["id"]}
        for sp in empresariales
        for asignacion in _todas_las_paginas(token, f"{GRAPH}/servicePrincipals/{sp['id']}/appRoleAssignedTo",
                                             {SELECT: "principalId,principalType", TOP: MAXIMO},
                                             PERMISO_APLICACIONES)
        if asignacion.get("principalType") == "User"
    ]


def _leer_concesiones(token, nombres):
    """Permisos OAuth delegados. `nombres` ({id: nombre}) se completa con las apps que falten."""
    concesiones = []
    for grant in _todas_las_paginas(token, f"{GRAPH}/oauth2PermissionGrants", {TOP: MAXIMO}, PERMISO_CONCESIONES):
        cliente = grant.get("clientId")
        if not cliente:
            continue
        if cliente not in nombres:
            datos_sp = _get(token, f"{GRAPH}/servicePrincipals/{cliente}", {SELECT: "id,displayName"},
                            PERMISO_APLICACIONES)
            nombres[cliente] = datos_sp.get("displayName") or cliente
        concesiones.append({
            "aplicativo_id": cliente,
            "nombre": nombres[cliente],
            "alcance": (grant.get("scope") or "").strip(),
            "usuario_id": grant.get("principalId") if grant.get("consentType") == "Principal" else None,
        })
    return concesiones


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
    empresariales = _leer_empresariales(token)
    nombres = {sp["id"]: sp.get("displayName") or sp["id"] for sp in empresariales}
    return {
        "usuarios": _leer_usuarios(token),
        "aplicativos": [{"id": sp["id"], "nombre": nombres[sp["id"]], "sso": _tipo_sso(sp)} for sp in empresariales],
        "asignaciones": _leer_asignaciones(token, empresariales),
        "concesiones": _leer_concesiones(token, nombres),
    }


# --------------------------------------------------------------------------- Keycloak
# La dirección de Keycloak sale del entorno (KEYCLOAK_URL) y no del formulario: así nadie
# puede usar el conector para que el inventario haga peticiones a otro servidor (SSRF).
PATRON_REALM = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
PATRON_CLIENTE_KEYCLOAK = re.compile(r"^[A-Za-z0-9._:-]{1,255}$")
SIN_PERMISOS_KEYCLOAK = ("La cuenta de servicio no tiene permisos: asígnale los roles view-users y "
                         "manage-users del cliente realm-management.")


def url_keycloak():
    url = os.environ.get("KEYCLOAK_URL", "").rstrip("/")
    if not url:
        raise ErrorConector("El servidor no tiene configurada la dirección de Keycloak (KEYCLOAK_URL).")
    return url


def validar_credenciales_keycloak(realm, client_id, client_secret, secreto_obligatorio):
    if not isinstance(realm, str) or not PATRON_REALM.match(realm):
        return "El realm solo puede tener letras, números, puntos, guiones y guiones bajos."
    if not isinstance(client_id, str) or not PATRON_CLIENTE_KEYCLOAK.match(client_id):
        return "El Client ID no es válido."
    if client_secret is not None and (not isinstance(client_secret, str) or len(client_secret) > 512):
        return "El secreto del cliente no es válido."
    if secreto_obligatorio and not client_secret:
        return "Falta el secreto del cliente."
    return None


def _token_keycloak(realm, client_id, client_secret):
    try:
        resp = requests.post(
            f"{url_keycloak()}/realms/{quote(realm, safe='')}/protocol/openid-connect/token",
            data={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise ErrorConector("No se pudo contactar a Keycloak. Si está dormido (Render gratuito), "
                            "espera un minuto y vuelve a intentarlo.") from exc
    if resp.status_code == 404:
        raise ErrorConector(f"El realm «{realm}» no existe en Keycloak.")
    if resp.status_code in (400, 401):
        raise ErrorConector("Keycloak rechazó las credenciales: revisa el Client ID, el secreto y que el "
                            "cliente tenga activadas la autenticación y las cuentas de servicio.")
    if not resp.ok:
        raise ErrorConector(f"Keycloak respondió con un error ({resp.status_code}) al pedir el token.")
    return resp.json()["access_token"]


def _admin_keycloak(metodo, token, realm, ruta, **kwargs):
    url = f"{url_keycloak()}/admin/realms/{quote(realm, safe='')}{ruta}"
    try:
        resp = requests.request(metodo, url, timeout=TIMEOUT,
                                headers={"Authorization": f"Bearer {token}"}, **kwargs)
    except requests.RequestException as exc:
        raise ErrorConector("Se perdió la conexión con Keycloak.") from exc
    if resp.status_code == 403:
        raise ErrorConector(SIN_PERMISOS_KEYCLOAK)
    if not resp.ok:
        raise ErrorConector(f"Keycloak respondió con un error ({resp.status_code}).")
    return resp


def probar_keycloak(realm, client_id, client_secret):
    """Comprueba credenciales y permisos leyendo un usuario. Devuelve el nombre del realm."""
    token = _token_keycloak(realm, client_id, client_secret)
    _admin_keycloak("GET", token, realm, "/users", params={"max": "1", "briefRepresentation": "true"})
    return realm


def deshabilitar_en_keycloak(realm, client_id, client_secret, correo):
    """
    Deshabilita la cuenta del usuario en Keycloak y cierra todas sus sesiones (RF-08).
    Busca por correo exacto y, si no aparece, por nombre de usuario igual al correo.
    Devuelve "deshabilitado" o "no_encontrado".
    """
    token = _token_keycloak(realm, client_id, client_secret)
    cuentas = []
    for campo in ("email", "username"):
        cuentas = _admin_keycloak("GET", token, realm, "/users",
                                  params={campo: correo, "exact": "true"}).json()
        if cuentas:
            break
    if not cuentas:
        return "no_encontrado"
    for cuenta in cuentas:
        ruta = f"/users/{quote(cuenta['id'], safe='')}"
        _admin_keycloak("PUT", token, realm, ruta, json={"enabled": False})
        _admin_keycloak("POST", token, realm, f"{ruta}/logout")
    return "deshabilitado"
