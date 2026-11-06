"""
IdentityHub - Auth Reverse Proxy

Extiende SSO a aplicativos que no soportan ningún protocolo de federación (OIDC/SAML) de forma
nativa. El usuario se autentica una sola vez contra Keycloak; este proxy valida esa sesión y, en
cada petición, la traduce a las credenciales que el aplicativo protegido SÍ entiende (en este
esqueleto: HTTP Basic Auth con una cuenta de servicio compartida) — sin que el aplicativo
protegido necesite ningún cambio, y sin que el usuario final vea o conozca esa credencial.

Decisión de arquitectura (ver docs/ARQUITECTURA.md, Decisión 1): esto NO reimplementa el
protocolo OIDC. Usa Authlib (biblioteca madura y auditada por la comunidad de seguridad) para el
flujo de autorización contra Keycloak.
"""
import base64
import json
import os
from urllib.parse import urlencode, urlsplit

import requests
from authlib.integrations.flask_client import OAuth
from flask import Flask, Response, redirect, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

# Justificación de Seguridad (SonarCloud - CSRF):
# El auth-proxy actúa como API Gateway transparente hacia aplicativos legacy, que no saben
# validar tokens CSRF intermediados. Por eso la defensa vive aquí, sin tokens: la cookie de
# sesión es SameSite=Lax y las peticiones que cambian datos (POST, PUT, PATCH, DELETE) se
# rechazan si Origin o Referer indican otro sitio (ver _mismo_origen).
# Sin carpeta estática propia: Flask atiende /static/... por defecto y así interceptaba los
# estilos y el JavaScript del aplicativo protegido (el panel del inventario quedaba sin ellos).
app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("PROXY_SECRET_KEY") or os.urandom(24).hex()
# En Render, HTTPS termina en el balanceador y llega HTTP al contenedor. ProxyFix hace que
# Flask respete X-Forwarded-Proto/Host, para que la URL de retorno a Keycloak sea https://.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
# La sesión vive en una cookie: SameSite=Lax impide que otro sitio la use en peticiones POST
# (CSRF) y Secure la limita a HTTPS cuando el proxy está publicado (PROXY_COOKIE_SECURE=1).
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.environ.get("PROXY_COOKIE_SECURE", "0") == "1",
)

KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "identityhub")
CLIENT_ID = os.environ.get("PROXY_CLIENT_ID", "auth-proxy")
CLIENT_SECRET = os.environ.get("PROXY_CLIENT_SECRET", "")
# Rol de Keycloak que debe tener el usuario para pasar por este proxy (vacío = cualquier usuario
# autenticado). La instancia que protege el inventario exige "admin-ti".
ROL_REQUERIDO = os.environ.get("PROXY_REQUIRED_ROLE", "").strip()

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:6000")
# Credenciales de la cuenta de servicio compartida que el proxy usa para autenticarse contra el
# aplicativo legacy, en nombre del usuario ya validado por Keycloak. El usuario final nunca las ve.
BACKEND_SERVICE_USER = os.environ.get("BACKEND_SERVICE_USER", "service-account")
BACKEND_SERVICE_PASSWORD = os.environ.get("BACKEND_SERVICE_PASSWORD", "change-me")

KEYCLOAK_EXTERNAL_URL = os.environ.get("KEYCLOAK_EXTERNAL_URL", "http://localhost:8080")

try:
    metadata = requests.get(
        f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/.well-known/openid-configuration",
        timeout=5,
    ).json()
    if KEYCLOAK_EXTERNAL_URL != KEYCLOAK_URL:
        metadata["issuer"] = metadata["issuer"].replace(KEYCLOAK_URL, KEYCLOAK_EXTERNAL_URL)
        metadata["authorization_endpoint"] = metadata["authorization_endpoint"].replace(KEYCLOAK_URL, KEYCLOAK_EXTERNAL_URL)
        if metadata.get("end_session_endpoint"):
            metadata["end_session_endpoint"] = metadata["end_session_endpoint"].replace(KEYCLOAK_URL, KEYCLOAK_EXTERNAL_URL)
    # Cierre de sesión en Keycloak (RP-initiated logout), al que se envía el navegador.
    FIN_SESION_URL = metadata.get("end_session_endpoint")

    oauth = OAuth(app)
    oauth.register(
        name="keycloak",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        server_metadata=metadata,
        authorize_url=metadata["authorization_endpoint"],
        access_token_url=metadata["token_endpoint"],
        jwks_uri=metadata.get("jwks_uri"),
        userinfo_endpoint=metadata.get("userinfo_endpoint"),
        client_kwargs={"scope": "openid email profile"},
    )
except Exception:
    FIN_SESION_URL = None
    oauth = OAuth(app)
    oauth.register(
        name="keycloak",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        server_metadata_url=f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

HEADERS_NO_REENVIABLES = {"host", "cookie", "content-length", "accept-encoding"}
HEADERS_NO_DEVOLVER = {"content-encoding", "content-length", "transfer-encoding", "connection"}


@app.route("/login", methods=["GET"])
def login():
    redirect_uri = url_for("auth_callback", _external=True)
    return oauth.keycloak.authorize_redirect(redirect_uri)


def _roles_del_token(token):
    """Roles de realm y de cliente que Keycloak incluye en el access token.

    El token llega directo del endpoint de tokens de Keycloak por el canal de servidor a
    servidor (TLS, autenticado con el secreto del cliente), no desde el navegador; por eso se
    leen sus afirmaciones sin volver a validar la firma.
    """
    try:
        carga = token["access_token"].split(".")[1]
        datos = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
        return set()
    roles = set(datos.get("realm_access", {}).get("roles", []))
    for cliente in datos.get("resource_access", {}).values():
        roles.update(cliente.get("roles", []))
    return roles


@app.route("/auth/callback", methods=["GET"])
def auth_callback():
    token = oauth.keycloak.authorize_access_token()
    if ROL_REQUERIDO and ROL_REQUERIDO not in _roles_del_token(token):
        session.clear()
        session["id_token"] = token.get("id_token")  # para que «Volver» cierre también Keycloak
        return Response(
            "<!doctype html><meta charset='utf-8'><title>Acceso denegado</title>"
            "<p>Tu usuario no tiene permiso para entrar a este aplicativo. "
            "Pide al área de TI el rol correspondiente.</p><p><a href='/logout'>Volver</a></p>",
            status=403, mimetype="text/html",
        )
    userinfo = token.get("userinfo") or {}
    session["id_token"] = token.get("id_token")
    session["usuario"] = {
        "email": userinfo.get("email", "desconocido"),
        "nombre": userinfo.get("name", userinfo.get("preferred_username", "desconocido")),
    }
    return redirect("/")


def _url_fin_sesion():
    """URL de cierre de sesión de Keycloak. Si el proxy arrancó antes que Keycloak (pasa en
    Render al desplegar todo junto), se consulta ahora en lugar de quedar desactivada."""
    if FIN_SESION_URL:
        return FIN_SESION_URL
    try:
        url = oauth.keycloak.load_server_metadata().get("end_session_endpoint")
    except Exception:
        return None
    return url.replace(KEYCLOAK_URL, KEYCLOAK_EXTERNAL_URL) if url else None


@app.route("/logout", methods=["GET"])
def logout():
    id_token = session.get("id_token")
    session.clear()
    fin_sesion = _url_fin_sesion()
    if not fin_sesion:
        return redirect("/login")
    # Cierra también la sesión de Keycloak: si solo se borrara la del proxy, el siguiente /login
    # entraría sin pedir contraseña (riesgo en equipos compartidos, HU-03).
    parametros = {"client_id": CLIENT_ID, "post_logout_redirect_uri": url_for("login", _external=True)}
    if id_token:
        parametros["id_token_hint"] = id_token
    return redirect(f"{fin_sesion}?{urlencode(parametros)}")


def _mismo_origen():
    """Defensa contra CSRF para métodos que cambian datos: si el navegador envía Origin (o, en su
    defecto, Referer), debe ser el mismo host del proxy. Sin ninguno de los dos se acepta, porque
    los navegadores siempre los envían en peticiones de otro sitio y las herramientas de línea de
    comandos no tienen la cookie de sesión."""
    origen = request.headers.get("Origin") or request.headers.get("Referer")
    if not origen:
        return True
    return urlsplit(origen).netloc == request.host


def _reenviar_a_backend(path):
    """
    Núcleo del componente: reenvía la petición ya autenticada al aplicativo protegido,
    inyectando (a) un header con el usuario real para trazabilidad, y (b) las credenciales
    de la cuenta de servicio compartida para que el aplicativo legacy acepte la petición.
    """
    usuario = session["usuario"]
    url_destino = f"{BACKEND_URL}/{path}"
    headers_reenviados = {
        k: v for k, v in request.headers.items() if k.lower() not in HEADERS_NO_REENVIABLES
    }
    headers_reenviados["X-Forwarded-User"] = usuario["email"]

    respuesta = requests.request(
        method=request.method,
        url=url_destino,
        headers=headers_reenviados,
        params=request.args,
        data=request.get_data(),
        auth=(BACKEND_SERVICE_USER, BACKEND_SERVICE_PASSWORD),
        allow_redirects=False,
        timeout=10,
    )

    headers_respuesta = [
        (k, v) for k, v in respuesta.raw.headers.items() if k.lower() not in HEADERS_NO_DEVOLVER
    ]
    return Response(respuesta.content, respuesta.status_code, headers_respuesta)


@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def proxy(path):
    if not session.get("usuario"):
        return redirect(url_for("login"))
    if request.method not in ("GET", "HEAD", "OPTIONS") and not _mismo_origen():
        return Response("Origen no permitido", status=403, mimetype="text/plain")
    return _reenviar_a_backend(path)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 9000))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1")
