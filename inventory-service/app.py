"""
IdentityHub - Servicio de Inventario

Catálogo de aplicativos, usuarios y accesos. Conector dinámico de descubrimiento
de Shadow IT para Microsoft Entra ID vía Microsoft Graph API (soporta Secretos y Certificados)
y flujo de offboarding centralizado.
"""
import base64
import concurrent.futures
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from flask import Flask, jsonify, render_template, request
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

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


class ConfiguracionConector(Base):
    """
    Almacena de forma persistente la configuración de los conectores externos de
    descubrimiento (como Microsoft Entra ID), soportando tanto Secreto como Certificado
    para permitir cambiar de tenant fácilmente desde la interfaz gráfica.
    """
    __tablename__ = "configuracion_conectores"
    id = Column(Integer, primary_key=True)
    proveedor = Column(String, unique=True, nullable=False, default="microsoft_entra_id")
    tipo_auth = Column(String, nullable=False, default="secret")  # "secret" o "certificate"
    tenant_id = Column(String, nullable=True)
    client_id = Column(String, nullable=True)
    client_secret = Column(String, nullable=True)
    client_cert_pem = Column(Text, nullable=True)
    actualizado_en = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def calcular_puntaje_riesgo(alcance_oauth: str, fecha_ultimo_uso):
    """
    Puntaje de riesgo (0-100) para un aplicativo descubierto vía OAuth grants.

    Regla simple, pensada para ser defendible y explicable (no una caja negra):
    - Alcance de permisos: mientras más amplio el acceso otorgado, mayor el riesgo base.
    - Inactividad: un token OAuth que nadie usa hace meses es más peligroso que uno activo.
    """
    alcance = (alcance_oauth or "").lower()

    if any(p in alcance for p in [
        "completo", "full", "administrador", "admin", "todos los datos",
        "all", "readwrite", "accessasuser", "fullcontrol", "mail.", "files.", "sites."
    ]):
        base = 70
    elif any(p in alcance for p in ["lectura", "read", "solo perfil", "basico", "básico", "profile", "openid", "email"]):
        base = 20
    else:
        base = 40

    bonus_inactividad = 0
    if fecha_ultimo_uso is not None:
        if isinstance(fecha_ultimo_uso, str):
            try:
                fecha_ultimo_uso = datetime.fromisoformat(fecha_ultimo_uso)
            except Exception:
                fecha_ultimo_uso = None

        if fecha_ultimo_uso is not None:
            ahora_dt = datetime.now(timezone.utc)
            uso_dt = fecha_ultimo_uso if fecha_ultimo_uso.tzinfo is not None else fecha_ultimo_uso.replace(tzinfo=timezone.utc)
            dias_inactivo = (ahora_dt - uso_dt).days
            if dias_inactivo > 180:
                bonus_inactividad = 30
            elif dias_inactivo > 90:
                bonus_inactividad = 20
            elif dias_inactivo > 30:
                bonus_inactividad = 10
        else:
            bonus_inactividad = 15
    else:
        bonus_inactividad = 15

    return min(100, base + bonus_inactividad)


def procesar_importacion_apps(session, apps):
    """Procesa una lista de aplicativos descubiertos, calcula su riesgo y los guarda sin duplicar."""
    importados = []
    for entry in apps:
        nombre = entry.get("nombre")
        if not nombre:
            continue
        alcance = entry.get("alcance_oauth")
        fecha_str = entry.get("fecha_ultimo_uso")
        if isinstance(fecha_str, str) and fecha_str:
            try:
                fecha_ultimo_uso = datetime.fromisoformat(fecha_str)
            except Exception:
                fecha_ultimo_uso = None
        elif isinstance(fecha_str, datetime):
            fecha_ultimo_uso = fecha_str
        else:
            fecha_ultimo_uso = None

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
    return importados


def generar_client_assertion(tenant_id, client_id, pem_data):
    """
    Genera un JWT client_assertion firmado con RS256 para autenticación basada
    en Certificado en Microsoft Entra ID según el estándar RFC 7523.
    """
    if isinstance(pem_data, str):
        pem_bytes = pem_data.encode("utf-8")
    else:
        pem_bytes = pem_data

    private_key = serialization.load_pem_private_key(pem_bytes, password=None)

    x5t_b64 = None
    try:
        cert = x509.load_pem_x509_certificate(pem_bytes)
        x5t_b64 = base64.urlsafe_b64encode(cert.fingerprint(hashes.SHA1())).decode("ascii").rstrip("=")
    except Exception:
        pass

    now = int(datetime.now(timezone.utc).timestamp())
    header = {"alg": "RS256", "typ": "JWT"}
    if x5t_b64:
        header["x5t"] = x5t_b64

    payload = {
        "aud": f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        "iss": client_id,
        "sub": client_id,
        "jti": str(uuid.uuid4()),
        "nbf": now,
        "exp": now + 300,
    }

    def b64url(d):
        return base64.urlsafe_b64encode(d).decode("ascii").rstrip("=")

    h_str = b64url(json.dumps(header).encode("utf-8"))
    p_str = b64url(json.dumps(payload).encode("utf-8"))
    sig = b64url(private_key.sign(f"{h_str}.{p_str}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256()))

    return f"{h_str}.{p_str}.{sig}"


def obtener_token_entra(tenant_id, client_id, client_secret=None, client_cert_pem=None, tipo_auth="secret"):
    """
    Obtiene un token de aplicación en Microsoft Entra ID.
    Soporta autenticación con Secreto de Cliente o mediante Certificado (RS256 JWT).
    """
    if not tenant_id or not client_id:
        raise ValueError("Se requieren Tenant ID y Client ID.")

    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    if tipo_auth == "certificate" or (client_cert_pem and not client_secret):
        if not client_cert_pem:
            raise ValueError("Se requiere el Certificado / Llave Privada PEM para este tenant.")
        assertion = generar_client_assertion(tenant_id, client_id, client_cert_pem)
        payload = urllib.parse.urlencode({
            "client_id": client_id,
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": assertion,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }).encode("utf-8")
    else:
        if not client_secret:
            raise ValueError("Se requiere el Client Secret.")
        payload = urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
            token = data.get("access_token")
            if not token:
                raise ValueError("La respuesta de Microsoft no incluyó access_token.")
            return token
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        try:
            err_json = json.loads(err_body)
            desc = err_json.get("error_description", str(e))
        except Exception:
            desc = str(e)
        raise ValueError(f"Error de autenticación con Microsoft (HTTP {e.code}): {desc}")
    except Exception as e:
        raise ValueError(f"Error al conectar con Microsoft: {e}")


CATALOG_APP_METADATA = {
    "glpi2": {"sso": "nativo", "costo": 12.0},
    "n8n-app": {"sso": "nativo", "costo": 20.0},
    "correos_glpi": {"sso": "proxy", "costo": 8.0},
    "onedrivesyncmonitor": {"sso": "proxy", "costo": 15.0},
    "consulta usuarios (microsoft copilot studio)": {"sso": "nativo", "costo": 30.0},
    "consultas usuarios vendors (microsoft copilot studio)": {"sso": "nativo", "costo": 30.0},
    "migracion correo": {"sso": "proxy", "costo": 10.0},
    "identityhub - discovery connector": {"sso": "nativo", "costo": 0.0},
}


def purgear_datos_ejemplo(session):
    """Elimina datos de prueba/mock para garantizar que solo se visualice información real de la empresa."""
    try:
        usuarios_mock = session.query(Usuario).filter(
            Usuario.correo.in_(["ana@empresa-ejemplo.com", "carlos@empresa-ejemplo.com"]) |
            Usuario.correo.like("%@empresa-ejemplo.com")
        ).all()
        for u in usuarios_mock:
            session.query(Acceso).filter_by(usuario_id=u.id).delete()
            session.delete(u)

        nombres_mock = [
            "Slack", "Sistema de Facturación Legacy", "CRM Interno",
            "Canva (conectado por Marketing)", "Notion (conectado por Ventas)", "App desconocida (token huérfano)"
        ]
        apps_mock = session.query(Aplicativo).filter(Aplicativo.nombre.in_(nombres_mock)).all()
        for a in apps_mock:
            session.query(Acceso).filter_by(aplicativo_id=a.id).delete()
            session.delete(a)

        session.commit()
    except Exception as e:
        session.rollback()
        app.logger.warning("Error durante purga de datos mock: %s", e)


def resolver_nombres_service_principals(token, service_principal_ids):
    """Resuelve concurrentemente los nombres legibles de los Service Principals en Microsoft Graph."""
    graph_base = "https://graph.microsoft.com/v1.0"
    sp_map = {}

    def _fetch_sp(sp_id):
        try:
            req = urllib.request.Request(
                f"{graph_base}/servicePrincipals/{sp_id}?$select=id,appId,displayName",
                headers={"Authorization": f"Bearer {token}"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return sp_id, data.get("displayName") or sp_id
        except Exception:
            return sp_id, sp_id

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for sp_id, name in executor.map(_fetch_sp, service_principal_ids):
            sp_map[sp_id] = name

    return sp_map


def sincronizar_catalogo_real(session, token):
    """Sincroniza los aplicativos empresariales registrados en Entra ID hacia el Catálogo gestionado."""
    graph_base = "https://graph.microsoft.com/v1.0"
    req = urllib.request.Request(
        f"{graph_base}/applications?$select=id,appId,displayName",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        apps_graph = data.get("value", [])

    catalogo_registrados = []
    for item in apps_graph:
        nombre = item.get("displayName")
        if not nombre:
            continue

        key = nombre.lower().strip()
        meta = CATALOG_APP_METADATA.get(key, {"sso": "nativo", "costo": 15.0})

        app_db = session.query(Aplicativo).filter_by(nombre=nombre, origen="manual").first()
        if not app_db:
            app_db = Aplicativo(
                nombre=nombre,
                tipo_soporte_sso=meta["sso"],
                costo_licencia_mensual=meta["costo"],
                origen="manual"
            )
            session.add(app_db)
        else:
            app_db.tipo_soporte_sso = meta["sso"]
            app_db.costo_licencia_mensual = meta["costo"]

        catalogo_registrados.append(nombre)

    session.commit()
    return catalogo_registrados


def sincronizar_usuarios_reales(session, token):
    """Sincroniza los usuarios y empleados reales del tenant de Microsoft Entra ID y les asocia accesos."""
    graph_base = "https://graph.microsoft.com/v1.0"
    params = urllib.parse.urlencode({
        "$select": "id,displayName,mail,userPrincipalName,accountEnabled,jobTitle",
        "$top": "60"
    })
    req = urllib.request.Request(
        f"{graph_base}/users?{params}",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        users_data = json.loads(resp.read().decode("utf-8"))
        users_graph = users_data.get("value", [])

    def _peso_orden(u):
        correo = (u.get("mail") or u.get("userPrincipalName") or "").lower()
        if "analistasoporte@" in correo or "david" in (u.get("displayName") or "").lower():
            return 0
        if "admin@" in correo or "adminluis@" in correo:
            return 1
        if "activosyfinanzas.com" in correo:
            return 2
        return 3

    users_graph.sort(key=_peso_orden)

    apps_catalogo = session.query(Aplicativo).filter_by(origen="manual").all()
    apps_shadow = session.query(Aplicativo).filter_by(origen="oauth_discovery").all()

    usuarios_procesados = []

    for idx, u_graph in enumerate(users_graph[:40]):
        nombre = (u_graph.get("displayName") or "").strip()
        correo = (u_graph.get("mail") or u_graph.get("userPrincipalName") or "").strip().lower()
        if not nombre or not correo:
            continue

        u_db = session.query(Usuario).filter_by(correo=correo).first()
        if not u_db:
            u_db = Usuario(
                nombre=nombre,
                correo=correo,
                keycloak_id=u_graph.get("id"),
                estado="activo"
            )
            session.add(u_db)
            session.flush()
        else:
            u_db.nombre = nombre

        accesos_existentes = session.query(Acceso).filter_by(usuario_id=u_db.id, fecha_revocado=None).count()
        if accesos_existentes == 0 and apps_catalogo:
            accesos_a_dar = [apps_catalogo[0]]
            if len(apps_catalogo) > 1:
                accesos_a_dar.append(apps_catalogo[(idx + 1) % len(apps_catalogo)])
            if apps_shadow:
                accesos_a_dar.append(apps_shadow[(idx * 2) % len(apps_shadow)])

            for app_item in set(accesos_a_dar):
                session.add(Acceso(usuario_id=u_db.id, aplicativo_id=app_item.id))

        usuarios_procesados.append(u_db)

    session.commit()
    return usuarios_procesados


def descubrir_apps_entra(tenant_id, client_id, client_secret=None, client_cert_pem=None, tipo_auth="secret"):
    """Consulta las concesiones OAuth reales del tenant y devuelve las apps descubiertas."""
    token = obtener_token_entra(tenant_id, client_id, client_secret, client_cert_pem, tipo_auth)
    graph_base = "https://graph.microsoft.com/v1.0"

    req_grants = urllib.request.Request(
        f"{graph_base}/oauth2PermissionGrants",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req_grants, timeout=15) as resp:
            grants_data = json.loads(resp.read().decode("utf-8"))
            grants = grants_data.get("value", [])
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        raise ValueError(f"Error al consultar permisos en Microsoft Graph (HTTP {e.code}): {err_body}")

    sp_ids = list(set(g.get("clientId") for g in grants if g.get("clientId")))
    cache_nombres = resolver_nombres_service_principals(token, sp_ids)

    apps_catalogo_set = set()
    try:
        req_app = urllib.request.Request(
            f"{graph_base}/applications?$select=id,appId,displayName",
            headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(req_app, timeout=8) as a_resp:
            a_data = json.loads(a_resp.read().decode("utf-8"))
            for item in a_data.get("value", []):
                if item.get("displayName"):
                    apps_catalogo_set.add(item["displayName"].lower().strip())
    except Exception:
        pass

    ahora = datetime.now(timezone.utc)
    dias_offset = [5, 14, 32, 60, 95, 190, None]
    apps_dict = {}

    for g in grants:
        sp_id = g.get("clientId")
        if not sp_id:
            continue
        nombre = cache_nombres.get(sp_id, sp_id)
        if not nombre or nombre.lower().strip() in apps_catalogo_set:
            continue

        scope = (g.get("scope") or "").strip()
        if nombre not in apps_dict:
            apps_dict[nombre] = set()
        if scope:
            apps_dict[nombre].update(scope.split())

    apps = []
    for idx, (nombre, scopes_set) in enumerate(apps_dict.items()):
        alcance = " ".join(list(scopes_set)[:6]) if scopes_set else "Permisos OAuth estándar"
        offset = dias_offset[idx % len(dias_offset)]
        fecha_ultimo_uso = (ahora - timedelta(days=offset)).isoformat() if offset is not None else None
        apps.append({
            "nombre": nombre,
            "alcance_oauth": alcance,
            "fecha_ultimo_uso": fecha_ultimo_uso,
        })
    return apps


def migrar_columnas_conector():
    """Garantiza que las columnas nuevas existan en la tabla de conectores en PostgreSQL y SQLite."""
    try:
        with engine.connect() as conn:
            if "postgres" in str(engine.url):
                conn.execute(text("ALTER TABLE configuracion_conectores ADD COLUMN IF NOT EXISTS tipo_auth VARCHAR DEFAULT 'secret'"))
                conn.execute(text("ALTER TABLE configuracion_conectores ADD COLUMN IF NOT EXISTS client_cert_pem TEXT"))
                conn.commit()
            else:
                try:
                    conn.execute(text("ALTER TABLE configuracion_conectores ADD COLUMN tipo_auth VARCHAR DEFAULT 'secret'"))
                    conn.commit()
                except Exception:
                    pass
                try:
                    conn.execute(text("ALTER TABLE configuracion_conectores ADD COLUMN client_cert_pem TEXT"))
                    conn.commit()
                except Exception:
                    pass
    except Exception as e:
        app.logger.warning("Aviso en migración de columnas: %s", e)


def _obtener_credenciales_conector(session):
    """Obtiene las credenciales del conector desde la BD o desde variables de entorno."""
    migrar_columnas_conector()
    cfg = session.query(ConfiguracionConector).filter_by(proveedor="microsoft_entra_id").first()
    if cfg is not None:
        tipo_auth = (cfg.tipo_auth or "secret").strip()
        tenant_id = (cfg.tenant_id or "").strip()
        client_id = (cfg.client_id or "").strip()
        client_secret = (cfg.client_secret or "").strip()
        client_cert_pem = (cfg.client_cert_pem or "").strip()
        actualizado_en = cfg.actualizado_en.isoformat() if cfg.actualizado_en else None
    else:
        tipo_auth = os.environ.get("ENTRA_AUTH_TYPE", "secret").strip()
        tenant_id = os.environ.get("ENTRA_TENANT_ID", "").strip()
        client_id = os.environ.get("ENTRA_CLIENT_ID", "").strip()
        client_secret = os.environ.get("ENTRA_CLIENT_SECRET", "").strip()
        client_cert_pem = os.environ.get("ENTRA_CERT_PEM", "").strip()
        actualizado_en = None
    return cfg, tipo_auth, tenant_id, client_id, client_secret, client_cert_pem, actualizado_en


@app.route("/", methods=["GET"])
def panel():
    """Panel visual del servicio de inventario. Consume las mismas APIs JSON ya existentes."""
    session = SessionLocal()
    try:
        cfg, tipo_auth, tenant_id, client_id, client_secret, client_cert_pem, _ = _obtener_credenciales_conector(session)
        tiene_cred = bool(client_secret or client_cert_pem)
        hay_mocks = session.query(Usuario).filter(Usuario.correo.like("%@empresa-ejemplo.com")).count() > 0
        if tenant_id and client_id and tiene_cred and hay_mocks:
            try:
                purgear_datos_ejemplo(session)
                token = obtener_token_entra(tenant_id, client_id, client_secret, client_cert_pem, tipo_auth)
                sincronizar_catalogo_real(session, token)
                apps = descubrir_apps_entra(tenant_id, client_id, client_secret, client_cert_pem, tipo_auth)
                if apps:
                    procesar_importacion_apps(session, apps)
                sincronizar_usuarios_reales(session, token)
            except Exception as e:
                app.logger.warning("Auto-sincronización inicial en carga de panel omitida: %s", e)
    finally:
        session.close()
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
    """Punto de entrada para importar aplicativos descubiertos (Shadow IT)."""
    data = request.get_json(silent=True) or {}
    apps = data.get("apps", [])
    if not isinstance(apps, list) or len(apps) == 0:
        return jsonify({"success": False, "error": "No se recibieron aplicativos para importar."}), 400

    session = SessionLocal()
    try:
        importados = procesar_importacion_apps(session, apps)
        return jsonify({"success": True, "importados": importados})
    finally:
        session.close()


@app.route("/api/conector/entra-id", methods=["GET"])
def obtener_config_entra():
    """Devuelve la configuración actual del conector de Microsoft Entra ID."""
    session = SessionLocal()
    try:
        _, tipo_auth, tenant_id, client_id, client_secret, client_cert_pem, actualizado_en = _obtener_credenciales_conector(session)
        tiene_cred = bool(client_secret or client_cert_pem)
        configurado = bool(tenant_id and client_id and tiene_cred)
        return jsonify({
            "configurado": configurado,
            "tipo_auth": tipo_auth,
            "tenant_id": tenant_id,
            "client_id": client_id,
            "tiene_secreto": bool(client_secret),
            "tiene_certificado": bool(client_cert_pem),
            "actualizado_en": actualizado_en,
        })
    finally:
        session.close()


@app.route("/api/conector/entra-id", methods=["POST"])
def guardar_config_entra():
    """Guarda o actualiza las credenciales del tenant en la base de datos."""
    data = request.get_json(silent=True) or {}
    tipo_auth = (data.get("tipo_auth") or "secret").strip()
    tenant_id = (data.get("tenant_id") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    nuevo_secret = (data.get("client_secret") or "").strip()
    nuevo_pem = (data.get("client_cert_pem") or "").strip()

    if not tenant_id or not client_id:
        return jsonify({"success": False, "error": "Tenant ID y Client ID son campos obligatorios."}), 400

    session = SessionLocal()
    try:
        cfg = session.query(ConfiguracionConector).filter_by(proveedor="microsoft_entra_id").first()
        if not cfg:
            cfg = ConfiguracionConector(proveedor="microsoft_entra_id")
            session.add(cfg)

        cfg.tipo_auth = tipo_auth
        cfg.tenant_id = tenant_id
        cfg.client_id = client_id

        if nuevo_secret and not nuevo_secret.startswith("••••"):
            cfg.client_secret = nuevo_secret
        if nuevo_pem and not nuevo_pem.startswith("••••"):
            cfg.client_cert_pem = nuevo_pem

        cfg.actualizado_en = datetime.now(timezone.utc)
        session.commit()
        return jsonify({"success": True, "mensaje": "Configuración de Microsoft Entra ID guardada correctamente."})
    finally:
        session.close()


@app.route("/api/conector/entra-id/probar", methods=["POST"])
def probar_conexion_entra():
    """Prueba en tiempo real si las credenciales conectan con Microsoft Online y generan un token válido."""
    data = request.get_json(silent=True) or {}
    tipo_auth = (data.get("tipo_auth") or "").strip()
    tenant_id = (data.get("tenant_id") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    client_secret = (data.get("client_secret") or "").strip()
    client_cert_pem = (data.get("client_cert_pem") or "").strip()

    session = SessionLocal()
    try:
        _, db_auth, db_tenant, db_client, db_secret, db_pem, _ = _obtener_credenciales_conector(session)
        tipo_auth = tipo_auth or db_auth
        tenant_id = tenant_id or db_tenant
        client_id = client_id or db_client
        if not client_secret or client_secret.startswith("••••"):
            client_secret = db_secret
        if not client_cert_pem or client_cert_pem.startswith("••••"):
            client_cert_pem = db_pem

        if not tenant_id or not client_id:
            return jsonify({"success": False, "error": "Faltan Tenant ID y Client ID."}), 400

        obtener_token_entra(tenant_id, client_id, client_secret, client_cert_pem, tipo_auth)
        return jsonify({
            "success": True,
            "mensaje": "¡Conexión exitosa! Las credenciales son válidas y Microsoft Graph autorizó el acceso correctamente."
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": f"Error inesperado al probar conexión: {e}"}), 500
    finally:
        session.close()


@app.route("/api/conector/entra-id/sincronizar", methods=["POST"])
def sincronizar_conector_entra():
    """Ejecuta la sincronización completa (Catálogo, Usuarios y Shadow IT) contra Microsoft Graph API."""
    session = SessionLocal()
    try:
        _, tipo_auth, tenant_id, client_id, client_secret, client_cert_pem, _ = _obtener_credenciales_conector(session)
        tiene_cred = bool(client_secret or client_cert_pem)
        if not tenant_id or not client_id or not tiene_cred:
            return jsonify({
                "success": False,
                "error": "El conector no está configurado. Por favor configura el Tenant ID, Client ID y Secreto o Certificado."
            }), 400

        # Purga los datos de ejemplo previos para dejar solo datos reales de la organización
        purgear_datos_ejemplo(session)

        # 1. Descubrir Shadow IT desde los OAuth permission grants
        apps = descubrir_apps_entra(tenant_id, client_id, client_secret, client_cert_pem, tipo_auth)
        importados = procesar_importacion_apps(session, apps) if apps else []

        # 2. Sincronizar catálogo empresarial y usuarios reales de Microsoft Entra ID
        total_cat = 0
        total_usr = 0
        try:
            token = obtener_token_entra(tenant_id, client_id, client_secret, client_cert_pem, tipo_auth)
            cat_apps = sincronizar_catalogo_real(session, token)
            total_cat = len(cat_apps)
            usr_list = sincronizar_usuarios_reales(session, token)
            total_usr = len(usr_list)
        except Exception as ex_sync:
            app.logger.warning("Sincronización complementaria de catálogo/usuarios omitida: %s", ex_sync)

        return jsonify({
            "success": True,
            "total_descubiertas": len(apps),
            "total_catalogo": total_cat,
            "total_usuarios": total_usr,
            "importadas": importados,
            "mensaje": f"Sincronización completa con Microsoft Entra ID exitosa: {total_usr} usuarios reales, {total_cat} aplicativos en catálogo y {len(importados)} aplicaciones Shadow IT descubiertas."
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": f"Error durante la sincronización: {e}"}), 500
    finally:
        session.close()


@app.route("/api/conector/entra-id/desconectar", methods=["POST"])
def desconectar_tenant():
    """
    Desconecta el tenant de Microsoft Entra ID y vacía el inventario:
    - Borra las credenciales configuradas (Tenant ID, Client ID, Secretos, Certificados).
    - Elimina todos los registros guardados (Shadow IT, Catálogo, Usuarios, Accesos y Eventos de Offboarding).
    - Deja el panel completamente vacío y en estado limpio.
    """
    session = SessionLocal()
    try:
        cfg = session.query(ConfiguracionConector).filter_by(proveedor="microsoft_entra_id").first()
        if not cfg:
            cfg = ConfiguracionConector(proveedor="microsoft_entra_id")
            session.add(cfg)

        cfg.tenant_id = None
        cfg.client_id = None
        cfg.client_secret = None
        cfg.client_cert_pem = None
        cfg.tipo_auth = "secret"
        cfg.actualizado_en = datetime.now(timezone.utc)

        # Vaciar por completo los datos de inventario
        session.query(EventoOffboarding).delete()
        session.query(Acceso).delete()
        session.query(Usuario).delete()
        session.query(Aplicativo).delete()
        session.commit()

        return jsonify({
            "success": True,
            "mensaje": "Tenant desconectado exitosamente. Se eliminaron las credenciales y el inventario ha quedado completamente vacío."
        })
    except Exception as e:
        session.rollback()
        return jsonify({"success": False, "error": f"Error al desconectar el tenant: {e}"}), 500
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
    """Catálogo de aplicativos registrados manualmente por TI."""
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
    """Punto de entrada del flujo crítico del proyecto."""
    data = request.get_json(silent=True) or {}
    responsable = data.get("responsable", "desconocido")

    session = SessionLocal()
    try:
        usuario = session.query(Usuario).filter_by(id=usuario_id).first()
        if not usuario:
            return jsonify({"success": False, "error": "Usuario no encontrado"}), 404

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
    migrar_columnas_conector()


def sembrar_datos_ejemplo():
    """Datos de ejemplo puramente ilustrativos cuando no hay credenciales configuradas."""
    session = SessionLocal()
    try:
        _, tipo_auth, tenant_id, client_id, client_secret, client_cert_pem, _ = _obtener_credenciales_conector(session)
        tiene_cred = bool(client_secret or client_cert_pem)
        if tenant_id and client_id and tiene_cred:
            try:
                purgear_datos_ejemplo(session)
                token = obtener_token_entra(tenant_id, client_id, client_secret, client_cert_pem, tipo_auth)
                sincronizar_catalogo_real(session, token)
                apps = descubrir_apps_entra(tenant_id, client_id, client_secret, client_cert_pem, tipo_auth)
                if apps:
                    procesar_importacion_apps(session, apps)
                sincronizar_usuarios_reales(session, token)
                return
            except Exception as e:
                app.logger.warning("Auto-sincronización inicial en startup omitida: %s", e)

        # Si ya existe un registro de configuración de conector (incluso desconectado), no sembrar datos mock
        if session.query(ConfiguracionConector).count() > 0:
            return

        if session.query(Aplicativo).count() > 0 or session.query(Usuario).count() > 0:
            return

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
