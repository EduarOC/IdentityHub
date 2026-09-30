"""
IdentityHub - Aplicativo Legacy de Demostración

Simula un aplicativo real de una empresa que NO tiene ningún soporte de SSO/OIDC/SAML — solo
entiende autenticación básica HTTP con una cuenta de servicio fija. Existe para poder probar el
auth reverse proxy de extremo a extremo sin depender de un aplicativo real de producción.

Importante: esta app NUNCA se modifica para hablar con Keycloak. Esa es justo la idea del
componente: el proxy resuelve el problema sin tocar el aplicativo protegido.
"""
import os
from flask import Flask, request, Response, jsonify

app = Flask(__name__)

SERVICE_USER = os.environ.get("BACKEND_SERVICE_USER", "service-account")
SERVICE_PASSWORD = os.environ.get("BACKEND_SERVICE_PASSWORD", "change-me")


def _no_autorizado():
    return Response(
        "Acceso no autorizado. Esta app solo acepta autenticación básica HTTP.",
        401,
        {"WWW-Authenticate": 'Basic realm="Sistema de Facturacion Legacy"'},
    )


@app.before_request
def exigir_basic_auth():
    auth = request.authorization
    if not auth or auth.username != SERVICE_USER or auth.password != SERVICE_PASSWORD:
        return _no_autorizado()


@app.route("/")
def home():
    # El header X-Forwarded-User lo agrega el auth-proxy, no el usuario final. Sirve para que
    # esta app (o sus logs) sepan quién hizo la petición real, aunque la autenticación hacia
    # ella use siempre la misma cuenta de servicio compartida.
    usuario_real = request.headers.get("X-Forwarded-User", "desconocido")
    return jsonify({
        "mensaje": "Bienvenido al Sistema de Facturación Legacy (demo)",
        "autenticado_via_proxy_como": usuario_real,
        "nota": "Esta app solo entiende HTTP Basic Auth. Nunca se modificó para soportar SSO.",
    })


@app.route("/facturas")
def facturas():
    usuario_real = request.headers.get("X-Forwarded-User", "desconocido")
    return jsonify({
        "usuario": usuario_real,
        "facturas": [
            {"id": 1, "cliente": "Cliente Ejemplo S.A.S", "monto": 1250000},
            {"id": 2, "cliente": "Otro Cliente Ltda", "monto": 480000},
        ],
    })



@app.after_request
def add_security_headers(response):
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 6000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1")
