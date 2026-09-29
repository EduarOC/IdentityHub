"""
IdentityHub - Servicio de Inventario

Catálogo de aplicativos, usuarios y accesos. Este es el esqueleto inicial: modelo de datos
y endpoints básicos de lectura. La integración real con la API de administración de Keycloak
(para ejecutar la revocación de accesos en el offboarding) es el siguiente paso técnico del
proyecto, documentado en docs/ARQUITECTURA.md.
"""
import os
from datetime import datetime, timezone, timedelta

from flask import Flask, jsonify, request, render_template
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# Justificación de Seguridad (SonarCloud - CSRF):
# Este microservicio funciona exclusivamente como una API REST. No utiliza
# cookies de sesión del navegador para mantener el estado de autenticación.
# Por lo tanto, el vector de ataque CSRF no es aplicable a este servicio.
app = Flask(__name__)

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

    accesos = relationship("Acceso", back_populates="aplicativo")


class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True)
    nombre = Column(String, nullable=False)
    correo = Column(String, nullable=False, unique=True)
    keycloak_id = Column(String, nullable=True)
    # 'activo', 'offboarding', 'inactivo'
    estado = Column(String, nullable=False, default="activo")

    accesos = relationship("Acceso", back_populates="usuario")


class Acceso(Base):
    __tablename__ = "accesos"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    aplicativo_id = Column(Integer, ForeignKey("aplicativos.id"), nullable=False)
    fecha_otorgado = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    fecha_revocado = Column(DateTime, nullable=True)

    usuario = relationship("Usuario", back_populates="accesos")
    aplicativo = relationship("Aplicativo", back_populates="accesos")


class EventoOffboarding(Base):
    __tablename__ = "eventos_offboarding"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    aplicativos_revocados = Column(String)  # lista separada por comas, para el MVP
    responsable = Column(String, nullable=False)


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

    if any(p in alcance for p in ["completo", "full", "administrador", "admin", "todos los datos"]):
        base = 70
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
    """Catálogo de aplicativos registrados manualmente por TI (excluye los descubiertos vía
    Shadow IT, que tienen su propia vista en /api/aplicativos/riesgo)."""
    session = SessionLocal()
    try:
        apps = session.query(Aplicativo).filter_by(origen="manual").all()
        return jsonify([
            {
                "id": a.id, "nombre": a.nombre,
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


@app.route("/api/usuarios/<int:usuario_id>/offboarding", methods=["POST"])
def iniciar_offboarding(usuario_id):
    """
    Punto de entrada del flujo crítico del proyecto (ver docs/ARQUITECTURA.md).
    TODO técnico pendiente: reemplazar la simulación de abajo por la llamada real a la API
    de administración de Keycloak (deshabilitar el usuario) y al auth proxy (invalidar sesión).
    """
    data = request.get_json(silent=True) or {}
    responsable = data.get("responsable", "desconocido")

    session = SessionLocal()
    try:
        usuario = session.query(Usuario).filter_by(id=usuario_id).first()
        if not usuario:
            return jsonify({"success": False, "error": "Usuario no encontrado"}), 404
            
        if usuario.estado in ["offboarding", "inactivo"]:
            return jsonify({"success": False, "error": f"El usuario ya se encuentra en estado {usuario.estado}"}), 400

        accesos_activos = session.query(Acceso).filter_by(usuario_id=usuario_id, fecha_revocado=None).all()
        nombres_apps = []
        for acceso in accesos_activos:
            acceso.fecha_revocado = datetime.now(timezone.utc)
            nombres_apps.append(acceso.aplicativo.nombre)

        usuario.estado = "offboarding"

        evento = EventoOffboarding(
            usuario_id=usuario_id,
            aplicativos_revocados=", ".join(nombres_apps),
            responsable=responsable,
        )
        session.add(evento)
        session.commit()

        return jsonify({
            "success": True,
            "aplicativos_revocados": nombres_apps,
            "nota": "Simulado a nivel de base de datos. Falta integrar la revocación real en Keycloak.",
        })
    finally:
        session.close()


def init_db():
    Base.metadata.create_all(engine)


def sembrar_datos_ejemplo():
    """
    Datos de ejemplo puramente ilustrativos para poder ver el panel funcionando de inmediato.
    NO son datos reales de ninguna empresa -- deben reemplazarse por el catálogo real una vez
    el equipo complete el diagnóstico de docs/INVESTIGACION_PENDIENTE.md.
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


if __name__ == "__main__":
    init_db()
    sembrar_datos_ejemplo()
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1")
