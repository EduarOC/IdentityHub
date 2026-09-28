# IdentityHub — Plataforma de Gestión Unificada de Identidad e Inventario de Aplicativos

[![Pruebas y análisis de calidad](https://github.com/EduarOC/IdentityHub/actions/workflows/build.yml/badge.svg)](https://github.com/EduarOC/IdentityHub/actions/workflows/build.yml)
[![Quality Gate](https://sonarcloud.io/api/project_badges/measure?project=EduarOC_proyecto-de-grado&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=EduarOC_proyecto-de-grado)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=EduarOC_proyecto-de-grado&metric=coverage)](https://sonarcloud.io/summary/new_code?id=EduarOC_proyecto-de-grado)

Proyecto de Grado — Ingeniería de Sistemas
Fundación de Educación Superior Nueva América

**Equipo:** David Yused Pulido Pardo · Eduar de Jesús Ortiz Causil · Jhoan Steven Soto Daza

## El problema

Las empresas medianas administran decenas de aplicativos (correo, CRM, ERP, herramientas internas),
pero solo una minoría soporta Single Sign-On (SSO) de forma nativa. Implementar SSO comercial
(Okta, Azure AD Premium) cuesta desde 6 USD/usuario/mes solo por la plataforma de identidad —
sin contar que muchos proveedores de software cobran un cargo adicional ("SSO tax") por habilitar
SAML/OIDC en sus planes empresariales. El resultado: la mayoría de las PYMES vive con contraseñas
sueltas, sin inventario centralizado de quién tiene acceso a qué, y con un riesgo de seguridad
crítico y muy común — cuentas de exempleados que nadie revocó porque no había un solo lugar desde
donde hacerlo.

## La propuesta

IdentityHub no reinventa los protocolos de autenticación (eso sería un riesgo de seguridad
innecesario). Se construye **sobre Keycloak** (Identity Provider open source, estándar de la
industria) y aporta valor real en tres capas:

1. **Broker de identidad para aplicativos sin soporte nativo de SSO**: un proxy de autenticación
   (patrón `auth reverse proxy`, el mismo que usan herramientas como Pomerium o Datawiza) que se
   antepone a aplicaciones legacy o de plan básico, resolviendo la autenticación sin que la
   aplicación protegida necesite ningún cambio.
2. **Inventario y automatización de accesos**: catálogo de qué usuario tiene acceso a qué
   aplicativo, con el costo de licencia de cada uno, y — la funcionalidad de mayor impacto en
   seguridad real — **revocación centralizada en el offboarding**: cuando alguien sale de la
   empresa, se le retira el acceso a todos los aplicativos desde un solo lugar.
3. **Descubrimiento de Shadow IT (diferencial frente a la competencia)**: la mayoría de
   plataformas accesibles para PYMES solo gestionan lo que TI ya conoce. IdentityHub además
   descubre automáticamente aplicativos conectados por OAuth sin aprobación de TI (conector
   implementado para Microsoft Entra ID), les asigna un puntaje de riesgo explicable, y los incluye en el
   mismo flujo de offboarding — cerrando un punto ciego que ni los IdP baratos ni las
   plataformas de descubrimiento caras (GAT, DoControl) resuelven juntos. Ver
   `docs/ARQUITECTURA.md`, Decisión 4, para el detalle completo.

## Estado del proyecto

| Componente | Estado |
|---|---|
| Keycloak (IdP, OIDC) con realm auto-importado | Funciona en local |
| Auth Reverse Proxy para aplicativos legacy | Funciona en local |
| Servicio de inventario + panel de administración | Funciona en local |
| Offboarding con registro de auditoría | Funciona (solo en la base de IdentityHub) |
| Revocación en Keycloak y cierre de sesión en el proxy | **Pendiente** (RF-08, RF-09) |
| Conector de Shadow IT para Entra ID | Probado con datos simulados; falta el tenant real (Semana 15) |
| Despliegue en Render | Inventario y base definidos en `render.yaml`; el resto, pendiente |

## Calidad

- **59 pruebas automatizadas** (pytest) con **100 % de cobertura** del código Python.
- **SonarQube Cloud:** Quality Gate aprobado; seguridad, confiabilidad y mantenibilidad en A.
- Cada push a `main` y cada Pull Request corre las pruebas y el análisis en GitHub Actions
  (`.github/workflows/build.yml`). El análisis automático de SonarCloud debe permanecer apagado.
- Dependencias con versión exacta y hash verificado (`requirements.lock`); contenedores sin root.

## Stack técnico

- **Identity Provider:** [Keycloak](https://www.keycloak.org/) 25 (open source, OIDC/SAML)
- **Servicios:** Python 3.12 + Flask (inventario, auth proxy, aplicativo legacy de demostración)
- **Base de datos:** PostgreSQL 16 (compartida por el inventario y Keycloak)
- **Orquestación local:** Docker Compose · **Nube:** Render (plan gratuito)
- **Calidad:** pytest, pytest-cov, SonarQube Cloud, GitHub Actions

## Estructura del repositorio

```
auth-proxy/              Auth Reverse Proxy (Flask + Authlib) — protege aplicativos sin SSO
inventory-service/       Inventario, offboarding, Shadow IT y panel de administración
legacy-app-demo/         Aplicativo legacy de demostración (solo HTTP Basic)
discovery-connectors/    Conector de Shadow IT para Microsoft Entra ID (script)
keycloak-realm/          Realm "identityhub" que Keycloak importa al arrancar
*/tests/                 Pruebas automatizadas de cada componente
docs/                    ARQUITECTURA.md (incluye despliegue de Keycloak en Render)
.github/                 Workflow de CI, plantillas de Issues y Pull Requests
docker-compose.yml       Entorno local completo
render.yaml              Despliegue en Render (inventario + base de datos)
sonar-project.properties Configuración del análisis de SonarCloud
```

## Cómo levantar el entorno local

```bash
cp .env.example .env   # solo la primera vez: credenciales de desarrollo local
docker compose up -d
```

Las contraseñas no están en `docker-compose.yml`: se leen de `.env`, que no se sube al
repositorio. Si falta alguna, Docker Compose se detiene e indica cuál.

| Servicio | URL | Credenciales de prueba |
|---|---|---|
| Panel de administración (inventario) | http://localhost:5000 | — |
| Auth proxy → aplicativo legacy | http://localhost:9000 | `ana.torres` / `identityhub123` |
| Consola de Keycloak | http://localhost:8080 | las de `KEYCLOAK_ADMIN_PASSWORD` en `.env` |

Al abrir `http://localhost:9000`, el proxy redirige al login de Keycloak; tras iniciar sesión se
entra al aplicativo legacy sin ingresar ninguna credencial propia de esa app. El panel arranca con
datos de ejemplo ilustrativos.

**Shadow IT contra la empresa real:** ver `discovery-connectors/entra_id.py` para el registro de
la app en Entra ID, los permisos y el consentimiento de administrador. Solo se ejecuta contra el
tenant real con aprobación de Seguridad Informática.

## Cómo correr las pruebas

```bash
pip install --require-hashes -r auth-proxy/requirements.lock -r inventory-service/requirements.lock -r legacy-app-demo/requirements.lock
pip install --require-hashes -r requirements-dev.lock
python -m pytest --cov --cov-config=.coveragerc
```

## Flujo de trabajo

GitHub Flow, documentado en `CONTRIBUTING.md`: una rama por cambio (`feat/`, `fix/`, `docs/`,
`test/`, `chore/`), Pull Request hacia `main` revisado por otro integrante, y fusión solo con
las pruebas y el Quality Gate en verde.

**Importante para la trazabilidad:** configura git con el correo **vinculado a tu cuenta de
GitHub** (GitHub → Settings → Emails). Un correo que no esté ahí hace que los commits aparezcan
como anónimos en GitHub y en SonarCloud.

```bash
git config --global user.name "Tu Nombre"
git config --global user.email "el-correo-de-tu-cuenta-de-github@..."
```
