# IdentityHub — Inventario de accesos, offboarding y Shadow IT sobre tu proveedor de identidad

[![Pruebas y análisis de calidad](https://github.com/EduarOC/IdentityHub/actions/workflows/build.yml/badge.svg)](https://github.com/EduarOC/IdentityHub/actions/workflows/build.yml)
[![Quality Gate](https://sonarcloud.io/api/project_badges/measure?project=EduarOC_proyecto-de-grado&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=EduarOC_proyecto-de-grado)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=EduarOC_proyecto-de-grado&metric=coverage)](https://sonarcloud.io/summary/new_code?id=EduarOC_proyecto-de-grado)

IdentityHub responde, para una empresa mediana, tres preguntas que hoy viven en hojas de cálculo:
**quién tiene acceso a qué**, **qué aplicaciones se conectaron sin permiso de TI** y **cómo
retirarle todo a alguien que se va, desde un solo lugar y con evidencia**.

## El problema

Las empresas medianas administran decenas de aplicativos (correo, CRM, ERP, herramientas
internas), pero solo una minoría soporta Single Sign-On (SSO) de forma nativa. El SSO comercial
cuesta desde 6 USD por usuario al mes, y muchos proveedores cobran aparte por habilitar SAML/OIDC
(el «SSO tax»). El resultado: contraseñas sueltas, ningún inventario centralizado de accesos y un
riesgo muy común, el de las cuentas de exempleados que nadie revocó porque no había un solo lugar
desde donde hacerlo.

## Qué hace

IdentityHub no reinventa los protocolos de autenticación: se apoya en **Keycloak** y en
**Microsoft Entra ID**, y suma tres capas.

1. **Inventario conectado al tenant.** Desde la pestaña **Integraciones** del panel se conecta
   Microsoft Entra ID con permisos de solo lectura. IdentityHub trae los usuarios, las
   aplicaciones empresariales y quién tiene asignada cada una. Nada se inventa ni se borra: lo
   que desaparece en Entra queda como revocado, con fecha.
2. **Offboarding en un solo paso.** Revoca todos los accesos en el inventario y, con el conector
   de Keycloak, **deshabilita la cuenta en el SSO y cierra sus sesiones**. Cada retiro queda
   registrado con responsable, fecha, aplicativos revocados y resultado en el SSO.
3. **Descubrimiento de Shadow IT.** Detecta las aplicaciones a las que los usuarios les dieron
   permisos OAuth sin pasar por TI y les asigna un puntaje de riesgo explicable (alcance de los
   permisos e inactividad), que reconoce los permisos reales de Microsoft Graph.

Y, para los aplicativos que no soportan SSO, un **auth reverse proxy** (el patrón de Pomerium o
Datawiza) que exige el login de Keycloak sin cambiar nada en la aplicación protegida.

## Estado

| Componente | Estado |
|---|---|
| Panel de administración con login de Keycloak (rol `admin-ti`) | En producción |
| Conector de Microsoft Entra ID (usuarios, aplicaciones, accesos y Shadow IT) | En producción; probado con Microsoft Graph simulado, falta un tenant real |
| Conector de Keycloak: deshabilitar la cuenta y cerrar sesiones en el offboarding | En producción |
| Auth reverse proxy para aplicativos legacy | En producción |
| Invalidar en el proxy una sesión ya abierta tras el offboarding | Pendiente |
| Inicio de sesión en el panel con Microsoft (SSO federado con Entra ID) | Pendiente |
| Conector de Google Workspace | Próximamente |

## Seguridad

- **Acceso al panel:** login de Keycloak a través del auth-proxy, rol `admin-ti` obligatorio. El
  inventario rechaza (`401`) cualquier petición que no llegue por el proxy con su cuenta de
  servicio.
- **Secretos de los conectores:** cifrados en la base (Fernet, clave `CONECTORES_CLAVE` generada
  por Render). La API nunca los devuelve.
- **Mínimo privilegio:** Entra ID con `User.Read.All`, `Application.Read.All` y
  `DelegatedPermissionGrant.Read.All` (solo lectura). Keycloak con un cliente que solo tiene
  `view-users` y `manage-users`.
- **Navegador:** cookie de sesión `SameSite=Lax` y `Secure`, verificación de origen contra CSRF,
  CSP estricta sin código en línea, `X-Frame-Options`, `nosniff`, HSTS y `Referrer-Policy`.
- **Auditoría:** el historial de accesos, los offboarding y las acciones sobre los conectores
  no se borran.
- **Cadena de entrega:** `main` protegida (solo por Pull Request, con pruebas y Quality Gate en
  verde), dependencias con versión exacta y hash verificado, contenedores sin root y Gunicorn
  como servidor de producción.

## Calidad

- **201 pruebas automatizadas** (pytest), **99 % de cobertura** del código Python.
- **SonarQube Cloud:** Quality Gate obligatorio en cada Pull Request. El análisis automático de
  SonarCloud debe permanecer apagado: el análisis lo hace GitHub Actions
  (`.github/workflows/build.yml`).

## Arquitectura

```
                 ┌────────────── Keycloak (identityhub-sso) ──────────────┐
                 │  login OIDC · rol admin-ti · API de administración     │
                 └───────▲──────────────────────────────────────▲─────────┘
                         │ login                                │ deshabilitar cuenta
 Navegador ──► identityhub-panel (auth-proxy) ──► identityhub-inventario ──► Microsoft Graph
                                                   │  (Flask + Gunicorn)       (solo lectura)
 Navegador ──► identityhub-gateway (auth-proxy) ──► aplicativo legacy        PostgreSQL
```

| Servicio (Render) | Qué es |
|---|---|
| `identityhub-sso` | Keycloak 25 (realm `identityhub`) |
| `identityhub-panel` | Auth-proxy delante del inventario; exige el rol `admin-ti`. **Es la URL del panel.** |
| `identityhub-inventario` | API, panel web, conectores y offboarding. No se abre directamente. |
| `identityhub-gateway` | Auth-proxy delante del aplicativo legacy |
| `identityhub-legacy-app` | Aplicativo de demostración que solo entiende HTTP Basic |
| `identityhub-datos` | PostgreSQL 16 |

## Stack técnico

- **Identidad:** [Keycloak](https://www.keycloak.org/) 25 (OIDC/SAML) y Microsoft Entra ID (Graph API)
- **Servicios:** Python 3.12, Flask, Gunicorn, SQLAlchemy, Authlib, cryptography
- **Base de datos:** PostgreSQL 16
- **Despliegue:** Docker; Render con Blueprint (`render.yaml`); Docker Compose en local
- **Calidad:** pytest, pytest-cov, SonarQube Cloud, GitHub Actions

## Estructura del repositorio

```
auth-proxy/              Auth reverse proxy (Flask + Authlib): login, rol, CSRF y cabeceras
inventory-service/       Inventario, conectores (conectores.py), offboarding y panel web
legacy-app-demo/         Aplicativo legacy de demostración (solo HTTP Basic)
discovery-connectors/    Script de línea de comandos para importar permisos OAuth de Entra ID
keycloak-realm/          Imagen de Keycloak y realm "identityhub" que se importa al arrancar
*/tests/                 Pruebas automatizadas de cada componente
docs/                    CONECTORES.md, DESPLIEGUE_RENDER.md y ARQUITECTURA.md
.claude/skills/          Skills de Claude Code del proyecto (revisión del panel, rutas seguras,
                         verificación antes del PR, evidencias UAT)
.github/                 Workflow de CI y plantillas de Issues y Pull Requests
docker-compose.yml       Entorno local completo
render.yaml              Blueprint de Render (5 servicios, base de datos y grupos de secretos)
```

## Cómo empezar

### Conectar tu tenant

1. Entra al panel, inicia sesión con un usuario que tenga el rol `admin-ti` y abre
   **Integraciones**.
2. **Microsoft Entra ID:** registra la app con los tres permisos de solo lectura y pega el Tenant
   ID, el Client ID y el secreto.
3. **Keycloak:** crea el cliente `identityhub-inventario` con `view-users` y `manage-users` y
   pega su secreto.

Los pasos detallados, lo que se sincroniza y los errores frecuentes están en
[`docs/CONECTORES.md`](docs/CONECTORES.md).

### Desplegar tu propia instancia

Con un Blueprint de Render a partir de `render.yaml`. Solo pide dos contraseñas
(`KEYCLOAK_ADMIN_PASSWORD` y `UAT_USER_PASSWORD`); el resto de secretos los genera Render. Ver
[`docs/DESPLIEGUE_RENDER.md`](docs/DESPLIEGUE_RENDER.md).

### Entorno local

```bash
cp .env.example .env   # solo la primera vez: credenciales de desarrollo local
docker compose up -d
```

Las contraseñas no están en `docker-compose.yml`: se leen de `.env`, que no se sube al
repositorio. Si falta alguna, Docker Compose se detiene e indica cuál.

| Servicio | URL | Credenciales de prueba |
|---|---|---|
| Panel de administración | http://localhost:9100 | `ana.torres` / `UAT_USER_PASSWORD` de `.env` (rol `admin-ti`) |
| Auth proxy → aplicativo legacy | http://localhost:9000 | las mismas |
| Consola de Keycloak | http://localhost:8080 | `admin` / `KEYCLOAK_ADMIN_PASSWORD` de `.env` |

El panel arranca vacío y se llena conectando un tenant en **Integraciones**. Para revisar la
interfaz con datos ilustrativos, arranca el inventario con `SEMBRAR_DATOS_EJEMPLO=1`.

### Pruebas

```bash
pip install --require-hashes -r auth-proxy/requirements.lock -r inventory-service/requirements.lock -r legacy-app-demo/requirements.lock
pip install --require-hashes -r requirements-dev.lock
python -m pytest --cov --cov-config=.coveragerc
```

## Flujo de trabajo

GitHub Flow, documentado en `CONTRIBUTING.md`:
- una rama por cambio (`feat/`, `fix/`, `docs/`, `test/`, `chore/`);
- Pull Request hacia `main`;
- fusión solo con las pruebas y el Quality Gate en verde.

La rama `main` está protegida: no admite cambios directos, *force push* ni borrado. Todo lo que
llega a `main` se despliega en Render.

Configura git con un correo **vinculado a tu cuenta de GitHub** (GitHub → Settings → Emails).
Si no, los commits aparecen como anónimos en GitHub y en SonarCloud.

```bash
git config --global user.name "Tu Nombre"
git config --global user.email "el-correo-de-tu-cuenta-de-github@..."
```

## Origen

IdentityHub nació como proyecto de grado de Ingeniería de Sistemas en la Fundación de Educación
Superior Nueva América (2026), desarrollado por David Yused Pulido Pardo, Eduar de Jesús Ortiz
Causil y Jhoan Steven Soto Daza. Desde noviembre de 2026 lo continúa y mantiene Eduar de Jesús
Ortiz Causil como producto. Los documentos de diseño de esa etapa siguen en `docs/ARQUITECTURA.md`
y `docs/INVESTIGACION_PENDIENTE.md`.

## Licencia

IdentityHub se distribuye bajo la [licencia Apache 2.0](LICENSE).
Copyright 2026 Eduar de Jesús Ortiz Causil, Jhoan Steven Soto Daza y David Yused Pulido Pardo.
