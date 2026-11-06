"""
IdentityHub - Conector de descubrimiento de Shadow IT para Microsoft Entra ID

Consulta los permisos OAuth (delegated permission grants) realmente otorgados en el tenant de
Entra ID de la empresa, vía Microsoft Graph API, y los importa al servicio de inventario para
que calcular_puntaje_riesgo() (inventory-service/app.py) les asigne un puntaje de riesgo.

------------------------------------------------------------------------------------------
REQUISITOS PREVIOS (una sola vez, los hace un administrador real de Entra ID de la empresa)
------------------------------------------------------------------------------------------

1. Entra admin center (https://entra.microsoft.com) -> Identity -> Applications ->
   App registrations -> New registration.
   Nombre sugerido: "IdentityHub - Discovery Connector". Tipo de cuenta: el que aplique a este
   tenant (normalmente "Solo en este directorio organizativo").

2. En la app recién creada: Certificates & secrets -> Client secrets -> New client secret.
   Copiar el VALOR del secreto inmediatamente -- no se vuelve a mostrar después.

3. API permissions -> Add a permission -> Microsoft Graph -> Application permissions
   -> agregar: Directory.Read.All
   (permite leer oauth2PermissionGrants y servicePrincipals de todo el tenant; es de solo
   lectura, no puede modificar nada).

4. Clic en "Grant admin consent for [nombre del tenant]". Este paso requiere el rol de
   Administrador Global o Administrador de Aplicaciones en Entra ID -- sin él, las consultas
   de este script fallan con error 403.

5. En la pestaña "Overview" de la app registrada, copiar: Application (client) ID y
   Directory (tenant) ID.

------------------------------------------------------------------------------------------
VARIABLES DE ENTORNO NECESARIAS PARA CORRER ESTE SCRIPT
------------------------------------------------------------------------------------------
    ENTRA_TENANT_ID       Directory (tenant) ID del paso 5
    ENTRA_CLIENT_ID       Application (client) ID del paso 5
    ENTRA_CLIENT_SECRET   El secreto generado en el paso 2
    INVENTORY_URL         URL del servicio de inventario (por defecto http://localhost:5000)

Uso:
    python discovery-connectors/entra_id.py

------------------------------------------------------------------------------------------
LIMITACIÓN CONOCIDA (documentada, no oculta)
------------------------------------------------------------------------------------------
Microsoft Graph no expone la fecha de "último uso" directamente en oauth2PermissionGrants.
Obtenerla requiere correlacionar con el log de inicios de sesión (auditLogs/signIns), que puede
necesitar licencia Entra ID P1/P2 según cuánto historial se quiera consultar. Por ahora, este
conector importa fecha_ultimo_uso=null para todas las apps -- calcular_puntaje_riesgo() ya trata
eso como riesgo medio (ver inventory-service/app.py). Correlacionar con signIns es una mejora
natural pendiente, no un dato inventado.
"""
import os
import sys

import requests

TENANT_ID = os.environ.get("ENTRA_TENANT_ID")
CLIENT_ID = os.environ.get("ENTRA_CLIENT_ID")
CLIENT_SECRET = os.environ.get("ENTRA_CLIENT_SECRET")
INVENTORY_URL = os.environ.get("INVENTORY_URL", "http://localhost:5000")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def obtener_token():
    if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
        print(
            "Faltan variables de entorno: ENTRA_TENANT_ID, ENTRA_CLIENT_ID, ENTRA_CLIENT_SECRET.\n"
            "Ver las instrucciones en la parte superior de este archivo para obtenerlas."
        )
        sys.exit(1)

    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    resp = requests.post(url, data=data, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def obtener_nombre_app(token, service_principal_id, cache):
    """Resuelve el nombre visible de la app a partir de su service principal, con caché
    simple para no repetir la consulta si varios usuarios otorgaron permisos a la misma app."""
    if service_principal_id in cache:
        return cache[service_principal_id]

    resp = requests.get(
        f"{GRAPH_BASE}/servicePrincipals/{service_principal_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    nombre = resp.json().get("displayName", service_principal_id) if resp.ok else service_principal_id
    cache[service_principal_id] = nombre
    return nombre


def descubrir_apps(token=None):
    """Consulta las concesiones OAuth reales del tenant y las devuelve en el formato que
    espera POST /api/discovery/importar del servicio de inventario."""
    token = token or obtener_token()

    resp = requests.get(
        f"{GRAPH_BASE}/oauth2PermissionGrants",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    grants = resp.json().get("value", [])

    cache_nombres = {}
    apps = []
    for grant in grants:
        nombre = obtener_nombre_app(token, grant["clientId"], cache_nombres)
        apps.append({
            "nombre": nombre,
            "alcance_oauth": (grant.get("scope") or "").strip(),
            "fecha_ultimo_uso": None,
        })
    return apps


def _credenciales_inventario():
    """El inventario exige la cuenta de servicio cuando corre en despliegue. Sin contraseña
    configurada (desarrollo local) se llama sin autenticación."""
    clave = os.environ.get("INVENTORY_SERVICE_PASSWORD")
    if not clave:
        return None
    return (os.environ.get("INVENTORY_SERVICE_USER", "service-account"), clave)


def importar_al_inventario(apps):
    resp = requests.post(f"{INVENTORY_URL}/api/discovery/importar", json={"apps": apps},
                         auth=_credenciales_inventario(), timeout=15)
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    apps_encontradas = descubrir_apps()
    print(f"Se encontraron {len(apps_encontradas)} concesiones OAuth en el tenant de Entra ID.")

    if apps_encontradas:
        resultado = importar_al_inventario(apps_encontradas)
        print("Respuesta del servicio de inventario:", resultado)
    else:
        print("No hay aplicativos para importar (0 concesiones OAuth encontradas).")
