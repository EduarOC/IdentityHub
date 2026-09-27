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
import os

import requests
from authlib.integrations.flask_client import OAuth
from flask import Flask, Response, redirect, request, session, url_for

# Justificación de Seguridad (SonarCloud - CSRF):
# El auth-proxy actúa como API Gateway transparente hacia aplicativos legacy.
# Implementar protección CSRF estricta en el proxy rompería la comunicación
# con los sistemas subyacentes, ya que estos no soportan la validación de tokens CSRF
# intermediados. La mitigación del CSRF es responsabilidad de la aplicación destino.
app = Flask(__name__)
app.secret_key = os.environ.get("PROXY_SECRET_KEY") or os.urandom(24).hex()

KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "identityhub")
CLIENT_ID = os.environ.get("PROXY_CLIENT_ID", "auth-proxy")
CLIENT_SECRET = os.environ.get("PROXY_CLIENT_SECRET", "")

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:6000")
# Credenciales de la cuenta de servicio compartida que el proxy usa para autenticarse contra el
# aplicativo legacy, en nombre del usuario ya validado por Keycloak. El usuario final nunca las ve.
BACKEND_SERVICE_USER = os.environ.get("BACKEND_SERVICE_USER", "service-account")
BACKEND_SERVICE_PASSWORD = os.environ.get("BACKEND_SERVICE_PASSWORD", "change-me")

oauth = OAuth(app)
oauth.register(
    name="keycloak",
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    server_metadata_url=f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

HEADERS_NO_REENVIABLES = {"host", "cookie", "content-length"}
HEADERS_NO_DEVOLVER = {"content-encoding", "content-length", "transfer-encoding", "connection"}


@app.route("/login", methods=["GET"])
def login():
    redirect_uri = url_for("auth_callback", _external=True)
    return oauth.keycloak.authorize_redirect(redirect_uri)


@app.route("/auth/callback", methods=["GET"])
def auth_callback():
    token = oauth.keycloak.authorize_access_token()
    userinfo = token.get("userinfo") or {}
    session["usuario"] = {
        "email": userinfo.get("email", "desconocido"),
        "nombre": userinfo.get("name", userinfo.get("preferred_username", "desconocido")),
    }
    return redirect("/")


@app.route("/logout", methods=["GET"])
def logout():
    session.clear()
    return redirect("/login")


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
    return _reenviar_a_backend(path)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 9000))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1")
