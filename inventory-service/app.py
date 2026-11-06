"""
IdentityHub - Servicio de Inventario

Catálogo de aplicativos, usuarios y accesos, alimentado por conectores con el proveedor de
identidad de la empresa (hoy Microsoft Entra ID; ver conectores.py y docs/CONECTORES.md).
La revocación real en Keycloak durante el offboarding sigue pendiente (RF-08).
"""
import hmac
import json
import os
import threading
from datetime import datetime, timezone, timedelta

from flask import Flask, Response, jsonify, request, render_template
from sqlalchemy import create_engine, inspect, text, Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

import conectores

# Justificación de Seguridad (SonarCloud - CSRF):
# Este servicio no emite cookies propias. En despliegue queda detrás de una instancia del
# auth-proxy (inventory-proxy), que autentica con Keycloak, exige el rol de administrador de TI
# y reenvía cada petición con la cuenta de servicio (HTTP Basic) y el header X-Forwarded-User.
# La cookie de sesión vive en el proxy, que la marca SameSite=Lax y rechaza las peticiones que
# cambian datos si llegan desde otro origen. Por eso aquí no se agrega un token CSRF.
app = Flask(__name__)

# Rutas que responden sin la cuenta de servicio: solo la verificación de salud de Render.
RUTAS_PUBLICAS = {"/salud"}


def _clave_servicio():
    """Contraseña de la cuenta de servicio que usa el proxy. Si no está definida (desarrollo y
    pruebas), el servicio no exige autenticación."""
    return os.environ.get("BACKEND_SERVICE_PASSWORD", "")


@app.before_request
def exigir_cuenta_de_servicio():
    clave = _clave_servicio()
    if not clave or request.path in RUTAS_PUBLICAS:
        return None
    usuario = os.environ.get("BACKEND_SERVICE_USER", "service-account")
    auth = request.authorization
    valido = (
        auth is not None
        and hmac.compare_digest((auth.username or "").encode(), usuario.encode())
        and hmac.compare_digest((auth.password or "").encode(), clave.encode())
    )
    if not valido:
        return Response("Se requiere iniciar sesión a través de IdentityHub.", 401,
                        {"WWW-Authenticate": 'Basic realm="identityhub-inventario"'})
    return None


def usuario_conectado():
    """Correo del administrador que inició sesión en el proxy. Solo se confía en el header
    cuando la petición pasó la cuenta de servicio; sin ella, cualquiera podría inventarlo."""
    if not _clave_servicio():
        return None
    return request.headers.get("X-Forwarded-User") or None

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://identityhub:identityhub_dev_password@localhost:5432/identityhub")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Aplicativo(Base):
    __tablename__ = "aplicativos"
    id = Column(Integer, primary_key=True)
    nombre = Column(String, nullable=False)
    # 'nativo' = soporta OIDC/SAML directamente; 'proxy' = requiere el auth reverse proxy;
    # 'ninguno' = todavía sin integrar.
    tipo_soporte_sso = Column(String, nullable=False, default="ninguno")
    costo_licencia_mensual = Column(Float, default=0)

    # --- Descubrimiento de Shadow IT (diferencial del proyecto) ---
    # 'manual' = registrado a mano por un administrador; 'oauth_discovery' = descubierto
    # automáticamente a partir de los permisos OAuth otorgados en Google Workspace / Microsoft 365.
    origen = Column(String, nullable=False, default="manual")
    # Descripción del alcance de permisos OAuth otorgado (ej. "Acceso completo a Drive y Gmail").
    alcance_oauth = Column(String, nullable=True)
    fecha_ultimo_uso = Column(DateTime, nullable=True)
    # Calculado por calcular_puntaje_riesgo() a partir del alcance y la inactividad. 0-100.
    puntaje_riesgo = Column(Float, nullable=True)
    # Identificador en el proveedor (p. ej. id del service principal en Entra ID).
    id_externo = Column(String, nullable=True)

    accesos = relationship("Acceso", back_populates="aplicativo")


class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True)
    nombre = Column(String, nullable=False)
    correo = Column(String, nullable=False, unique=True)
    keycloak_id = Column(String, nullable=True)
    # 'activo', 'offboarding', 'inactivo'
    estado = Column(String, nullable=False, default="activo")
    # 'manual' o el conector que lo trajo ('entra_id'), con su identificador allá.
    origen = Column(String, nullable=False, default="manual")
    id_externo = Column(String, nullable=True)

    accesos = relationship("Acceso", back_populates="usuario")


class Acceso(Base):
    __tablename__ = "accesos"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    aplicativo_id = Column(Integer, ForeignKey("aplicativos.id"), nullable=False)
    fecha_otorgado = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    fecha_revocado = Column(DateTime, nullable=True)
    # 'manual' o el conector que lo registró. La sincronización solo revoca los suyos.
    origen = Column(String, nullable=False, default="manual")

    usuario = relationship("Usuario", back_populates="accesos")
    aplicativo = relationship("Aplicativo", back_populates="accesos")


class EventoOffboarding(Base):
    __tablename__ = "eventos_offboarding"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    aplicativos_revocados = Column(String)  # lista separada por comas, para el MVP
    responsable = Column(String, nullable=False)
    # Resultado en el SSO (RF-08): 'deshabilitado', 'no_encontrado', 'error' o 'sin_conector'.
    resultado_sso = Column(String, nullable=True)


class Conector(Base):
    """Conexión con un proveedor de identidad. El secreto se guarda cifrado (conectores.cifrar)
    y la API nunca lo devuelve: solo informa si existe."""
    __tablename__ = "conectores"
    id = Column(Integer, primary_key=True)
    tipo = Column(String, nullable=False, unique=True)  # 'entra_id'
    tenant_id = Column(String, nullable=True)
    client_id = Column(String, nullable=True)
    secreto_cifrado = Column(Text, nullable=True)
    # 'desconectado', 'pendiente' (guardado sin probar), 'conectado', 'sincronizando', 'error'
    estado = Column(String, nullable=False, default="desconectado")
    nombre_tenant = Column(String, nullable=True)
    ultimo_error = Column(String, nullable=True)
    ultima_sincronizacion = Column(DateTime, nullable=True)
    resumen = Column(Text, nullable=True)  # JSON con los conteos de la última sincronización
    actualizado_por = Column(String, nullable=True)
    actualizado_en = Column(DateTime, nullable=True)


class EventoConector(Base):
    """Auditoría de cambios en los conectores (configurar, probar, sincronizar, desconectar)."""
    __tablename__ = "eventos_conector"
    id = Column(Integer, primary_key=True)
    tipo = Column(String, nullable=False)
    accion = Column(String, nullable=False)
    responsable = Column(String, nullable=False)
    fecha = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    detalle = Column(String, nullable=True)


def calcular_puntaje_riesgo(alcance_oauth: str, fecha_ultimo_uso):
    """
    Puntaje de riesgo (0-100) para un aplicativo descubierto vía OAuth grants.

    Regla simple, pensada para ser defendible y explicable (no una caja negra):
    - Alcance de permisos: mientras más amplio el acceso otorgado, mayor el riesgo base.
    - Inactividad: un token OAuth que nadie usa hace meses es más peligroso que uno activo,
      porque es exactamente el patrón de una cuenta de exempleado que nadie revocó (el
      hallazgo más citado en la investigación de shadow apps).

    Esto es intencionalmente basado en reglas, no en Machine Learning, para la primera
    versión: es más fácil de explicar y defender en la sustentación. Migrar a un modelo
    entrenado con datos reales de uso es una mejora natural para el tercer corte, una vez
    haya suficiente historial.
    """
    alcance = (alcance_oauth or "").lower()

    # Además de las descripciones en español, se reconocen los permisos de Microsoft Graph
    # (p. ej. "Mail.ReadWrite Files.Read.All"): todo lo que abarca el tenant entero (.All),
    # escribe o envía no puede quedar como "solo lectura" aunque contenga la palabra "Read".
    if any(p in alcance for p in ["completo", "full", "administrador", "admin", "todos los datos",
                                  "readwrite", ".all", "directory.", "mail.send"]):
        base = 70
    elif any(p in alcance for p in ["write", "send", "manage"]):
        base = 40
    elif any(p in alcance for p in ["lectura", "read", "solo perfil", "basico", "básico"]):
        base = 20
    else:
        base = 40

    bonus_inactividad = 0
    if fecha_ultimo_uso is not None:
        dias_inactivo = (datetime.now(timezone.utc) - fecha_ultimo_uso.replace(tzinfo=timezone.utc)).days
        if dias_inactivo > 180:
            bonus_inactividad = 30
        elif dias_inactivo > 90:
            bonus_inactividad = 20
        elif dias_inactivo > 30:
            bonus_inactividad = 10
    else:
        # Sin fecha de último uso registrada: se trata como inactividad desconocida, riesgo medio.
        bonus_inactividad = 15

    return min(100, base + bonus_inactividad)


@app.route("/salud", methods=["GET"])
def salud():
    return jsonify({"estado": "ok"})


@app.route("/api/sesion", methods=["GET"])
def sesion_actual():
    """Quién está usando el panel. None cuando el servicio corre sin proxy (desarrollo)."""
    return jsonify({"usuario": usuario_conectado()})


@app.route("/", methods=["GET"])
def panel():
    """Panel visual del servicio de inventario. Consume las mismas APIs JSON ya existentes."""
    return render_template("dashboard.html")


@app.route("/api/usuarios", methods=["GET"])
def listar_usuarios():
    session = SessionLocal()
    try:
        usuarios = session.query(Usuario).all()
        resultado = []
        for u in usuarios:
            num_accesos = session.query(Acceso).filter_by(usuario_id=u.id, fecha_revocado=None).count()
            resultado.append({
                "id": u.id, "nombre": u.nombre, "correo": u.correo,
                "estado": u.estado, "accesos_activos": num_accesos,
            })
        return jsonify(resultado)
    finally:
        session.close()


@app.route("/api/discovery/importar", methods=["POST"])
def importar_apps_descubiertas():
    """
    Punto de entrada del componente de descubrimiento de Shadow IT (diferencial del proyecto).

    TODO técnico pendiente (requiere credenciales reales de la empresa, no disponibles en este
    entorno de desarrollo): reemplazar esta importación manual por una llamada real a:
    - Google Workspace Admin SDK (Reports API / Token API), si la empresa usa Google Workspace, o
    - Microsoft Graph API (oauth2PermissionGrants), si usa Microsoft 365.

    Mientras tanto, este endpoint acepta una lista ya extraída manualmente (por ejemplo, copiada
    desde Admin Console -> Security -> API Controls -> App Access Control) para poder probar el
    cálculo de riesgo y la integración con el offboarding sin depender de esas credenciales.

    Body esperado: {"apps": [{"nombre": str, "alcance_oauth": str, "fecha_ultimo_uso": "ISO8601" | null}]}
    """
    data = request.get_json(silent=True) or {}
    apps = data.get("apps", [])
    if not isinstance(apps, list) or len(apps) == 0:
        return jsonify({"success": False, "error": "No se recibieron aplicativos para importar."}), 400

    session = SessionLocal()
    try:
        importados = []
        for entry in apps:
            nombre = entry.get("nombre")
            if not nombre:
                continue
            alcance = entry.get("alcance_oauth")
            fecha_str = entry.get("fecha_ultimo_uso")
            fecha_ultimo_uso = datetime.fromisoformat(fecha_str) if fecha_str else None

            riesgo = calcular_puntaje_riesgo(alcance, fecha_ultimo_uso)

            existente = session.query(Aplicativo).filter_by(nombre=nombre, origen="oauth_discovery").first()
            if existente:
                existente.alcance_oauth = alcance
                existente.fecha_ultimo_uso = fecha_ultimo_uso
                existente.puntaje_riesgo = riesgo
            else:
                session.add(Aplicativo(
                    nombre=nombre, tipo_soporte_sso="ninguno", costo_licencia_mensual=0,
                    origen="oauth_discovery", alcance_oauth=alcance,
                    fecha_ultimo_uso=fecha_ultimo_uso, puntaje_riesgo=riesgo,
                ))
            importados.append({"nombre": nombre, "puntaje_riesgo": riesgo})

        session.commit()
        return jsonify({"success": True, "importados": importados})
    finally:
        session.close()


@app.route("/api/aplicativos/riesgo", methods=["GET"])
def listar_por_riesgo():
    """Lista los aplicativos descubiertos vía OAuth, ordenados de mayor a menor riesgo."""
    session = SessionLocal()
    try:
        apps = (
            session.query(Aplicativo)
            .filter_by(origen="oauth_discovery")
            .order_by(Aplicativo.puntaje_riesgo.desc())
            .all()
        )
        return jsonify([
            {
                "id": a.id, "nombre": a.nombre, "alcance_oauth": a.alcance_oauth,
                "fecha_ultimo_uso": a.fecha_ultimo_uso.isoformat() if a.fecha_ultimo_uso else None,
                "puntaje_riesgo": a.puntaje_riesgo,
            } for a in apps
        ])
    finally:
        session.close()


@app.route("/api/aplicativos", methods=["GET"])
def listar_aplicativos():
    """Catálogo de aplicativos gestionados por TI: los registrados a mano y las aplicaciones
    empresariales que trae el conector (excluye el Shadow IT, que tiene su propia vista en
    /api/aplicativos/riesgo)."""
    session = SessionLocal()
    try:
        apps = (session.query(Aplicativo).filter(Aplicativo.origen.in_(["manual", "entra_id"]))
                .order_by(Aplicativo.nombre).all())
        return jsonify([
            {
                "id": a.id, "nombre": a.nombre, "origen": a.origen,
                "tipo_soporte_sso": a.tipo_soporte_sso,
                "costo_licencia_mensual": a.costo_licencia_mensual,
            } for a in apps
        ])
    finally:
        session.close()


@app.route("/api/usuarios/<int:usuario_id>/accesos", methods=["GET"])
def accesos_de_usuario(usuario_id):
    """Accesos vigentes del usuario. Con ?historial=1 incluye también los revocados (HU-05)."""
    incluir_revocados = request.args.get("historial") in ("1", "true")
    session = SessionLocal()
    try:
        consulta = session.query(Acceso).filter_by(usuario_id=usuario_id)
        if not incluir_revocados:
            consulta = consulta.filter_by(fecha_revocado=None)
        return jsonify([
            {
                "aplicativo_id": a.aplicativo_id,
                "aplicativo": a.aplicativo.nombre,
                "fecha_otorgado": a.fecha_otorgado.isoformat(),
                "fecha_revocado": a.fecha_revocado.isoformat() if a.fecha_revocado else None,
            }
            for a in consulta.order_by(Acceso.fecha_otorgado).all()
        ])
    finally:
        session.close()


MENSAJES_SSO = {
    "deshabilitado": "Cuenta deshabilitada en Keycloak y sesiones cerradas.",
    "no_encontrado": "El usuario no tiene cuenta en Keycloak: no había nada que deshabilitar.",
    "sin_conector": "Keycloak no está conectado: la cuenta en el SSO sigue activa.",
}


def _deshabilitar_en_sso(session, correo):
    """Deshabilita la cuenta en Keycloak si el conector está conectado. Nunca lanza: el retiro en
    el inventario se registra igual y el resultado queda en el evento para hacer seguimiento."""
    conector = session.query(Conector).filter_by(tipo="keycloak").first()
    if not conector or conector.estado != "conectado":
        return "sin_conector", MENSAJES_SSO["sin_conector"]
    try:
        resultado = conectores.deshabilitar_en_keycloak(*_credenciales(conector), correo)
    except conectores.ErrorConector as exc:
        app.logger.warning("No se pudo deshabilitar una cuenta en Keycloak durante un offboarding")
        return "error", f"No se pudo deshabilitar la cuenta en Keycloak: {exc} Hazlo a mano o vuelve a intentarlo."
    return resultado, MENSAJES_SSO[resultado]


@app.route("/api/usuarios/<int:usuario_id>/offboarding", methods=["POST"])
def iniciar_offboarding(usuario_id):
    """
    Flujo crítico del proyecto (ver docs/ARQUITECTURA.md): revoca los accesos en el inventario y,
    con el conector de Keycloak conectado, deshabilita la cuenta en el SSO y cierra sus sesiones
    (RF-08). Repetirlo sobre un usuario ya retirado reintenta el paso del SSO.
    """
    data = request.get_json(silent=True) or {}
    # Detrás del proxy, el responsable es quien inició sesión, no lo que diga el cuerpo.
    responsable = usuario_conectado() or data.get("responsable") or "desconocido"

    session = SessionLocal()
    try:
        usuario = session.query(Usuario).filter_by(id=usuario_id).first()
        if not usuario:
            return jsonify({"success": False, "error": "Usuario no encontrado"}), 404
        if usuario_conectado() and usuario.correo.lower() == usuario_conectado().lower():
            return jsonify({"success": False,
                            "error": "No puedes ejecutar tu propio offboarding: te quedarías sin acceso."}), 400

        accesos_activos = session.query(Acceso).filter_by(usuario_id=usuario_id, fecha_revocado=None).all()
        nombres_apps = []
        for acceso in accesos_activos:
            acceso.fecha_revocado = datetime.now(timezone.utc)
            nombres_apps.append(acceso.aplicativo.nombre)

        usuario.estado = "offboarding"
        resultado_sso, mensaje_sso = _deshabilitar_en_sso(session, usuario.correo)

        evento = EventoOffboarding(
            usuario_id=usuario_id,
            aplicativos_revocados=", ".join(nombres_apps),
            responsable=responsable,
            resultado_sso=resultado_sso,
        )
        session.add(evento)
        session.commit()

        return jsonify({
            "success": True,
            "aplicativos_revocados": nombres_apps,
            "sso": {"resultado": resultado_sso, "mensaje": mensaje_sso},
        })
    finally:
        session.close()


# --------------------------------------------------------------------------- conectores
# Catálogo de integraciones que muestra el panel. Solo las "disponibles" se pueden configurar.
CATALOGO_CONECTORES = [
    {"tipo": "entra_id", "nombre": "Microsoft Entra ID", "disponible": True,
     "descripcion": "Usuarios, aplicaciones empresariales, asignaciones y permisos OAuth (Shadow IT) "
                    "de tu tenant de Microsoft 365."},
    {"tipo": "google_workspace", "nombre": "Google Workspace", "disponible": False,
     "descripcion": "Usuarios y aplicaciones con acceso OAuth a cuentas de Google."},
    {"tipo": "keycloak", "nombre": "Keycloak", "disponible": True,
     "descripcion": "Al ejecutar un offboarding, deshabilita la cuenta del usuario en el SSO y cierra "
                    "todas sus sesiones (RF-08)."},
]
TIPOS_DISPONIBLES = {c["tipo"] for c in CATALOGO_CONECTORES if c["disponible"]}
VALIDAR_CREDENCIALES = {"entra_id": conectores.validar_credenciales_entra,
                        "keycloak": conectores.validar_credenciales_keycloak}
PROBAR_CONEXION = {"entra_id": lambda *c: conectores.probar_entra(*c),
                   "keycloak": lambda *c: conectores.probar_keycloak(*c)}
CONECTORES_QUE_SINCRONIZAN = {"entra_id"}
_bloqueo_sincronizacion = threading.Lock()


def ejecutar_en_segundo_plano(funcion):
    """La sincronización puede tardar más que el tiempo de espera del proxy: corre aparte y el
    panel consulta el estado. Las pruebas reemplazan esta función para correrla en línea."""
    threading.Thread(target=funcion, daemon=True).start()


def _responsable():
    return usuario_conectado() or "desconocido"


def _registrar_evento(session, tipo, accion, detalle=None):
    session.add(EventoConector(tipo=tipo, accion=accion, responsable=_responsable(), detalle=detalle))


def _conector_a_json(definicion, conector):
    datos = dict(definicion)
    datos["sincroniza"] = definicion["tipo"] in CONECTORES_QUE_SINCRONIZAN
    if definicion["tipo"] == "keycloak":
        datos["servidor"] = os.environ.get("KEYCLOAK_URL") or None
    datos.update({"estado": "desconectado", "tenant_id": None, "client_id": None, "tiene_secreto": False,
                  "nombre_tenant": None, "ultimo_error": None, "ultima_sincronizacion": None, "resumen": None})
    if conector:
        datos.update({
            "estado": conector.estado,
            "tenant_id": conector.tenant_id,
            "client_id": conector.client_id,
            "tiene_secreto": bool(conector.secreto_cifrado),
            "nombre_tenant": conector.nombre_tenant,
            "ultimo_error": conector.ultimo_error,
            "ultima_sincronizacion": (conector.ultima_sincronizacion.isoformat()
                                      if conector.ultima_sincronizacion else None),
            "resumen": json.loads(conector.resumen) if conector.resumen else None,
        })
    return datos


def _conector_disponible(session, tipo):
    if tipo not in TIPOS_DISPONIBLES:
        return None, (jsonify({"error": "Conector no disponible."}), 404)
    return session.query(Conector).filter_by(tipo=tipo).first(), None


@app.route("/api/conectores", methods=["GET"])
def listar_conectores():
    session = SessionLocal()
    try:
        guardados = {c.tipo: c for c in session.query(Conector).all()}
        return jsonify([_conector_a_json(d, guardados.get(d["tipo"])) for d in CATALOGO_CONECTORES])
    finally:
        session.close()


@app.route("/api/conectores/<tipo>", methods=["PUT"])
def guardar_conector(tipo):
    """Guarda las credenciales. El secreto puede omitirse para conservar el que ya está guardado."""
    data = request.get_json(silent=True) or {}
    # Los textos llegan recortados; cualquier otro tipo pasa tal cual para que la validación lo rechace.
    tenant_id, client_id, secreto = (
        (v.strip() or None) if isinstance(v, str) else v
        for v in (data.get("tenant_id"), data.get("client_id"), data.get("client_secret"))
    )

    session = SessionLocal()
    try:
        conector, error = _conector_disponible(session, tipo)
        if error:
            return error
        mensaje = VALIDAR_CREDENCIALES[tipo](
            tenant_id, client_id, secreto,
            secreto_obligatorio=not (conector and conector.secreto_cifrado))
        if mensaje:
            return jsonify({"error": mensaje}), 400
        if conector and conector.estado == "sincronizando":
            return jsonify({"error": "Hay una sincronización en curso. Espera a que termine."}), 409
        try:
            secreto_cifrado = conectores.cifrar(secreto) if secreto else None
        except conectores.ErrorConector as exc:
            app.logger.exception("No se pudo cifrar el secreto de un conector")
            return jsonify({"error": str(exc)}), 503

        if not conector:
            conector = Conector(tipo=tipo)
            session.add(conector)
        cambio_de_tenant = conector.tenant_id not in (None, tenant_id)
        conector.tenant_id, conector.client_id = tenant_id, client_id
        if secreto_cifrado:
            conector.secreto_cifrado = secreto_cifrado
        conector.estado, conector.ultimo_error = "pendiente", None
        if cambio_de_tenant:
            conector.nombre_tenant = None
        conector.actualizado_por, conector.actualizado_en = _responsable(), datetime.now(timezone.utc)
        _registrar_evento(session, tipo, "configurar",
                          f"tenant {tenant_id}" + (" · secreto nuevo" if secreto_cifrado else ""))
        session.commit()
        definicion = next(d for d in CATALOGO_CONECTORES if d["tipo"] == tipo)
        return jsonify(_conector_a_json(definicion, conector))
    finally:
        session.close()


def _credenciales(conector):
    if not conector or not conector.secreto_cifrado:
        raise conectores.ErrorConector("El conector no está configurado.")
    return conector.tenant_id, conector.client_id, conectores.descifrar(conector.secreto_cifrado)


@app.route("/api/conectores/<tipo>/probar", methods=["POST"])
def probar_conector(tipo):
    session = SessionLocal()
    try:
        conector, error = _conector_disponible(session, tipo)
        if error:
            return error
        if not conector or not conector.secreto_cifrado:
            return jsonify({"error": "Primero guarda las credenciales del conector."}), 400
        try:
            nombre = PROBAR_CONEXION[tipo](*_credenciales(conector))
        except conectores.ErrorConector as exc:
            conector.estado, conector.ultimo_error = "error", str(exc)
            _registrar_evento(session, tipo, "probar", "fallida")
            session.commit()
            return jsonify({"error": str(exc)}), 502
        conector.estado, conector.ultimo_error, conector.nombre_tenant = "conectado", None, nombre
        _registrar_evento(session, tipo, "probar", "correcta")
        session.commit()
        return jsonify({"ok": True, "nombre_tenant": nombre})
    finally:
        session.close()


@app.route("/api/conectores/<tipo>/sincronizar", methods=["POST"])
def sincronizar_conector(tipo):
    session = SessionLocal()
    try:
        conector, error = _conector_disponible(session, tipo)
        if error:
            return error
        if tipo not in CONECTORES_QUE_SINCRONIZAN:
            return jsonify({"error": "Este conector no sincroniza datos: actúa durante el offboarding."}), 400
        if not conector or conector.estado not in ("conectado", "error") or not conector.secreto_cifrado:
            return jsonify({"error": "Prueba la conexión antes de sincronizar."}), 400
        if not _bloqueo_sincronizacion.acquire(blocking=False):
            return jsonify({"error": "Ya hay una sincronización en curso."}), 409
        conector.estado, conector.ultimo_error = "sincronizando", None
        _registrar_evento(session, tipo, "sincronizar", "iniciada")
        session.commit()
        conector_id, responsable = conector.id, _responsable()
    finally:
        session.close()

    def tarea():
        try:
            _sincronizar_entra(conector_id, responsable)
        finally:
            _bloqueo_sincronizacion.release()

    ejecutar_en_segundo_plano(tarea)
    return jsonify({"estado": "sincronizando"}), 202


@app.route("/api/conectores/<tipo>", methods=["DELETE"])
def desconectar_conector(tipo):
    """Borra las credenciales y deja de sincronizar. Los usuarios, aplicativos, accesos y eventos
    ya registrados se conservan: son la evidencia de auditoría (RNF-11)."""
    session = SessionLocal()
    try:
        conector, error = _conector_disponible(session, tipo)
        if error:
            return error
        if not conector or conector.estado == "desconectado":
            return jsonify({"error": "El conector no está configurado."}), 404
        if conector.estado == "sincronizando":
            return jsonify({"error": "Hay una sincronización en curso. Espera a que termine."}), 409
        conector.tenant_id = conector.client_id = conector.secreto_cifrado = None
        conector.nombre_tenant = conector.ultimo_error = None
        conector.estado = "desconectado"
        conector.actualizado_por, conector.actualizado_en = _responsable(), datetime.now(timezone.utc)
        _registrar_evento(session, tipo, "desconectar", "credenciales eliminadas; datos conservados")
        session.commit()
        return jsonify({"ok": True})
    finally:
        session.close()


def _sincronizar_entra(conector_id, responsable):
    session = SessionLocal()
    try:
        conector = session.get(Conector, conector_id)
        try:
            datos = conectores.extraer_entra(*_credenciales(conector))
            resumen = aplicar_sincronizacion_entra(session, datos)
        except conectores.ErrorConector as exc:
            session.rollback()
            conector = session.get(Conector, conector_id)
            conector.estado, conector.ultimo_error = "error", str(exc)
            session.add(EventoConector(tipo=conector.tipo, accion="sincronizar", responsable=responsable,
                                       detalle="fallida"))
            session.commit()
            return
        except Exception:  # noqa: BLE001 - cualquier fallo inesperado deja el conector en error
            app.logger.exception("Fallo inesperado al sincronizar el conector %s", conector_id)
            session.rollback()
            conector = session.get(Conector, conector_id)
            conector.estado = "error"
            conector.ultimo_error = "La sincronización falló por un error interno. Revisa los registros del servidor."
            session.commit()
            return
        conector.estado, conector.ultimo_error = "conectado", None
        conector.ultima_sincronizacion = datetime.now(timezone.utc)
        conector.resumen = json.dumps(resumen)
        session.add(EventoConector(tipo=conector.tipo, accion="sincronizar", responsable=responsable,
                                   detalle=json.dumps(resumen)))
        session.commit()
    finally:
        session.close()


def _recuperar_sincronizaciones_interrumpidas():
    """Si el servidor se reinició a mitad de una sincronización, el conector no debe quedar
    marcado como 'sincronizando' para siempre."""
    session = SessionLocal()
    try:
        for conector in session.query(Conector).filter_by(estado="sincronizando").all():
            conector.estado = "error"
            conector.ultimo_error = "La sincronización se interrumpió por un reinicio del servidor. Vuelve a ejecutarla."
        session.commit()
    finally:
        session.close()


def _guardar_usuario(session, u):
    usuario = (session.query(Usuario).filter_by(origen="entra_id", id_externo=u["id"]).first()
               or session.query(Usuario).filter_by(correo=u["correo"]).first())
    if not usuario:
        usuario = Usuario(nombre=u["nombre"] or u["correo"], correo=u["correo"])
        session.add(usuario)
    usuario.nombre = u["nombre"] or u["correo"]
    usuario.origen, usuario.id_externo = "entra_id", u["id"]
    if usuario.estado != "offboarding":
        usuario.estado = "activo" if u["activo"] else "inactivo"
    session.flush()
    return usuario


def _sincronizar_usuarios(session, usuarios_entra):
    """Crea o actualiza los usuarios. Devuelve {id en Entra: Usuario}."""
    por_externo = {u["id"]: _guardar_usuario(session, u) for u in usuarios_entra if u["correo"]}

    vistos = {usuario.id for usuario in por_externo.values()}
    for usuario in session.query(Usuario).filter_by(origen="entra_id", estado="activo").all():
        if usuario.id not in vistos:
            usuario.estado = "inactivo"
    return por_externo


def _sincronizar_catalogo(session, aplicativos_entra):
    """Aplicaciones empresariales del tenant. Devuelve {id del service principal: Aplicativo}."""
    por_externo = {}
    for a in aplicativos_entra:
        aplicativo = session.query(Aplicativo).filter_by(origen="entra_id", id_externo=a["id"]).first()
        if not aplicativo:
            aplicativo = Aplicativo(origen="entra_id", id_externo=a["id"], costo_licencia_mensual=0)
            session.add(aplicativo)
        aplicativo.nombre, aplicativo.tipo_soporte_sso = a["nombre"], a["sso"]
        session.flush()
        por_externo[a["id"]] = aplicativo
    return por_externo


def _sincronizar_shadow_it(session, concesiones):
    """Una fila por aplicación con permisos OAuth, con la unión de los alcances concedidos.
    Devuelve {id del service principal: Aplicativo}."""
    alcances = {}
    for c in concesiones:
        alcances.setdefault(c["aplicativo_id"], {"nombre": c["nombre"], "alcances": set()})
        alcances[c["aplicativo_id"]]["alcances"].update(c["alcance"].split())

    por_externo = {}
    for externo, info in alcances.items():
        aplicativo = (session.query(Aplicativo).filter_by(origen="oauth_discovery", id_externo=externo).first()
                      or session.query(Aplicativo).filter_by(origen="oauth_discovery", nombre=info["nombre"],
                                                             id_externo=None).first())
        if not aplicativo:
            aplicativo = Aplicativo(origen="oauth_discovery", tipo_soporte_sso="ninguno", costo_licencia_mensual=0)
            session.add(aplicativo)
        alcance = " ".join(sorted(info["alcances"]))
        aplicativo.nombre, aplicativo.id_externo, aplicativo.alcance_oauth = info["nombre"], externo, alcance
        aplicativo.puntaje_riesgo = calcular_puntaje_riesgo(alcance, aplicativo.fecha_ultimo_uso)
        session.flush()
        por_externo[externo] = aplicativo
    return por_externo


def _sincronizar_accesos(session, datos, usuarios, catalogo, shadow):
    """Deja vigentes exactamente los accesos que hay en Entra ID. Los que sobran se revocan con
    fecha, nunca se borran. Devuelve (nuevos, revocados)."""
    deseados = {
        (usuarios[a["usuario_id"]].id, catalogo[a["aplicativo_id"]].id)
        for a in datos["asignaciones"]
        if a["usuario_id"] in usuarios and a["aplicativo_id"] in catalogo
    } | {
        (usuarios[c["usuario_id"]].id, shadow[c["aplicativo_id"]].id)
        for c in datos["concesiones"]
        if c["usuario_id"] in usuarios
    }

    vigentes = {(a.usuario_id, a.aplicativo_id): a
                for a in session.query(Acceso).filter_by(origen="entra_id", fecha_revocado=None).all()}
    ahora = datetime.now(timezone.utc)
    revocados = [acceso for clave, acceso in vigentes.items() if clave not in deseados]
    for acceso in revocados:
        acceso.fecha_revocado = ahora
    nuevos = deseados - set(vigentes)
    for usuario_id, aplicativo_id in nuevos:
        session.add(Acceso(usuario_id=usuario_id, aplicativo_id=aplicativo_id, origen="entra_id"))
    return len(nuevos), len(revocados)


def aplicar_sincronizacion_entra(session, datos):
    """Refleja en el inventario lo que hay en Entra ID. No borra nada: los accesos que ya no
    existen allá se marcan como revocados y los usuarios que desaparecieron, como inactivos."""
    usuarios = _sincronizar_usuarios(session, datos["usuarios"])
    catalogo = _sincronizar_catalogo(session, datos["aplicativos"])
    shadow = _sincronizar_shadow_it(session, datos["concesiones"])
    nuevos, revocados = _sincronizar_accesos(session, datos, usuarios, catalogo, shadow)
    session.commit()
    return {"usuarios": len(usuarios), "aplicativos": len(catalogo), "shadow_it": len(shadow),
            "accesos_nuevos": nuevos, "accesos_revocados": revocados}


# Columnas agregadas después de que la base de producción ya existía. create_all() crea tablas
# nuevas pero no altera las existentes, así que se agregan aquí si faltan. Nombres y tipos son
# constantes del código, nunca entrada del usuario.
COLUMNAS_NUEVAS = {
    "aplicativos": {"id_externo": "VARCHAR"},
    "usuarios": {"origen": "VARCHAR NOT NULL DEFAULT 'manual'", "id_externo": "VARCHAR"},
    "accesos": {"origen": "VARCHAR NOT NULL DEFAULT 'manual'"},
    "eventos_offboarding": {"resultado_sso": "VARCHAR"},
}


def _migrar_columnas():
    inspector = inspect(engine)
    with engine.begin() as conexion:
        for tabla, columnas in COLUMNAS_NUEVAS.items():
            existentes = {c["name"] for c in inspector.get_columns(tabla)}
            for nombre, tipo in columnas.items():
                if nombre not in existentes:
                    conexion.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}"))


def init_db():
    Base.metadata.create_all(engine)
    _migrar_columnas()


# Lo que sembraba sembrar_datos_ejemplo() en versiones anteriores, para retirarlo de las bases
# que ya lo tienen. Solo coincide con esos registros exactos.
DOMINIO_EJEMPLO = "@empresa-ejemplo.com"
APLICATIVOS_EJEMPLO = {
    "manual": ["Slack", "Sistema de Facturación Legacy", "CRM Interno"],
    "oauth_discovery": ["Canva (conectado por Marketing)", "Notion (conectado por Ventas)",
                        "App desconocida (token huérfano)"],
}


def purgar_datos_ejemplo():
    """Quita los datos ilustrativos de versiones anteriores. Sus accesos y eventos de offboarding
    también son ficticios, así que se van con ellos; nada que provenga de un conector o que se
    haya registrado a mano con otros datos se toca."""
    session = SessionLocal()
    try:
        usuarios = session.query(Usuario).filter(Usuario.correo.like(f"%{DOMINIO_EJEMPLO}")).all()
        ids_usuarios = [u.id for u in usuarios]
        aplicativos = [
            a for origen, nombres in APLICATIVOS_EJEMPLO.items()
            for a in session.query(Aplicativo).filter(Aplicativo.origen == origen,
                                                      Aplicativo.nombre.in_(nombres),
                                                      Aplicativo.id_externo.is_(None)).all()
        ]
        ids_aplicativos = [a.id for a in aplicativos]
        if not ids_usuarios and not ids_aplicativos:
            return 0
        session.query(EventoOffboarding).filter(EventoOffboarding.usuario_id.in_(ids_usuarios)).delete(
            synchronize_session=False)
        session.query(Acceso).filter(
            Acceso.usuario_id.in_(ids_usuarios) | Acceso.aplicativo_id.in_(ids_aplicativos)
        ).delete(synchronize_session=False)
        for registro in usuarios + aplicativos:
            session.delete(registro)
        session.commit()
        app.logger.info("Datos de ejemplo retirados: %s usuarios, %s aplicativos",
                        len(ids_usuarios), len(ids_aplicativos))
        return len(ids_usuarios) + len(ids_aplicativos)
    finally:
        session.close()


def sembrar_datos_ejemplo():
    """
    Datos ilustrativos para desarrollo y pruebas (SEMBRAR_DATOS_EJEMPLO=1). En despliegue no se
    usan: el inventario se llena con los conectores.
    """
    session = SessionLocal()
    try:
        if session.query(Aplicativo).count() > 0:
            return  # ya hay datos (reales o de una corrida anterior); no sobreescribir

        slack = Aplicativo(nombre="Slack", tipo_soporte_sso="nativo", costo_licencia_mensual=8.0)
        facturacion = Aplicativo(nombre="Sistema de Facturación Legacy", tipo_soporte_sso="proxy", costo_licencia_mensual=25.0)
        crm = Aplicativo(nombre="CRM Interno", tipo_soporte_sso="ninguno", costo_licencia_mensual=15.0)
        session.add_all([slack, facturacion, crm])
        session.commit()

        ana = Usuario(nombre="Ana Torres", correo="ana@empresa-ejemplo.com", estado="activo")
        carlos = Usuario(nombre="Carlos Ruiz", correo="carlos@empresa-ejemplo.com", estado="activo")
        session.add_all([ana, carlos])
        session.commit()

        session.add_all([
            Acceso(usuario_id=ana.id, aplicativo_id=slack.id),
            Acceso(usuario_id=ana.id, aplicativo_id=facturacion.id),
            Acceso(usuario_id=carlos.id, aplicativo_id=slack.id),
            Acceso(usuario_id=carlos.id, aplicativo_id=crm.id),
        ])
        session.commit()

        # Ejemplos de Shadow IT descubierto, con distinto nivel de riesgo para mostrar el ordenamiento.
        ahora = datetime.now(timezone.utc)
        ejemplos_shadow_it = [
            {"nombre": "Canva (conectado por Marketing)", "alcance_oauth": "Acceso completo a Drive y perfil", "fecha_ultimo_uso": ahora - timedelta(days=200)},
            {"nombre": "Notion (conectado por Ventas)", "alcance_oauth": "Solo lectura de perfil básico", "fecha_ultimo_uso": ahora - timedelta(days=5)},
            {"nombre": "App desconocida (token huérfano)", "alcance_oauth": "Acceso completo a Gmail", "fecha_ultimo_uso": None},
        ]
        for ej in ejemplos_shadow_it:
            riesgo = calcular_puntaje_riesgo(ej["alcance_oauth"], ej["fecha_ultimo_uso"])
            session.add(Aplicativo(
                nombre=ej["nombre"], tipo_soporte_sso="ninguno", costo_licencia_mensual=0,
                origen="oauth_discovery", alcance_oauth=ej["alcance_oauth"],
                fecha_ultimo_uso=ej["fecha_ultimo_uso"], puntaje_riesgo=riesgo,
            ))
        session.commit()
    finally:
        session.close()





def preparar_base():
    init_db()
    if os.environ.get("SEMBRAR_DATOS_EJEMPLO") == "1":
        sembrar_datos_ejemplo()
    else:
        purgar_datos_ejemplo()
    _recuperar_sincronizaciones_interrumpidas()


if __name__ == "__main__":
    preparar_base()
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1")
