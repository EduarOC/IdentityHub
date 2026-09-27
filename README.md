# IdentityHub — Plataforma de Gestión Unificada de Identidad e Inventario de Aplicativos

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
   aplicativo, detección de licencias pagadas sin uso, y — la funcionalidad de mayor impacto en
   seguridad real — **revocación centralizada en el offboarding**: cuando alguien sale de la
   empresa, se le retira el acceso a todos los aplicativos desde un solo lugar.
3. **Descubrimiento de Shadow IT (diferencial frente a la competencia)**: la mayoría de
   plataformas accesibles para PYMES solo gestionan lo que TI ya conoce. IdentityHub además
   descubre automáticamente aplicativos conectados por OAuth sin aprobación de TI (vía Google
   Workspace / Microsoft 365), les asigna un puntaje de riesgo explicable, y los incluye en el
   mismo flujo de offboarding — cerrando un punto ciego que ni los IdP baratos ni las
   plataformas de descubrimiento caras (GAT, DoControl) resuelven juntos. Ver
   `docs/ARQUITECTURA.md`, Decisión 4, para el detalle completo.

## Estado del proyecto

Este repositorio contiene por ahora el **esqueleto técnico inicial** (arquitectura, Keycloak
levantado vía Docker, y el servicio de inventario en construcción). La investigación de mercado,
la justificación académica y las encuestas/entrevistas del primer corte **deben ser elaboradas por
el equipo** — ver `INVESTIGACION_PENDIENTE.md` para el checklist concreto de qué recopilar.

## Stack técnico

- **Identity Provider:** [Keycloak](https://www.keycloak.org/) (open source, protocolo OIDC/SAML)
- **Backend de inventario:** Python + Flask (mismo stack que el equipo ya domina)
- **Base de datos:** PostgreSQL
- **Orquestación local:** Docker Compose

## Estructura del repositorio

```
docker-compose.yml       Levanta Keycloak + PostgreSQL + el servicio de inventario en local
inventory-service/       Backend Flask: catálogo de apps, usuarios, licencias, offboarding
docs/
  ARQUITECTURA.md         Diagrama y explicación de los 2 componentes técnicos centrales
  INVESTIGACION_PENDIENTE.md   Checklist de investigación real que debe hacer el equipo
```

## Cómo levantar el entorno local

```bash
cp .env.example .env   # solo la primera vez: credenciales de desarrollo local
docker compose up -d
```

Las contraseñas ya no están escritas en `docker-compose.yml` (hallazgo de SonarCloud): se leen
del archivo `.env`, que no se sube al repositorio. Si falta alguna, Docker Compose se detiene y
indica cuál.

Esto levanta Keycloak en `http://localhost:8080` (admin/admin por defecto — cambiar antes de
cualquier uso real), el servicio de inventario en `http://localhost:5000`, y el auth reverse
proxy en `http://localhost:9000` (con un aplicativo legacy de demostración detrás, en el puerto
6000, protegido solo por HTTP Basic Auth — simula un aplicativo real sin soporte de SSO).

**Panel visual:** abrir `http://localhost:5000` en el navegador muestra el panel de
administración (catálogo de aplicativos, usuarios con botón de offboarding, y el panel de
Shadow IT ordenado por riesgo). Arranca con datos de ejemplo ilustrativos — ver
`docs/INVESTIGACION_PENDIENTE.md` para reemplazarlos por el catálogo real de la empresa.

**Probar el auth reverse proxy:** abrir `http://localhost:9000` redirige al login de Keycloak
(realm y usuario de prueba ya importados automáticamente — `ana.torres` / `identityhub123`).
Tras iniciar sesión, se accede al aplicativo legacy de demostración sin haber ingresado ninguna
credencial propia de esa app.

**Descubrimiento de Shadow IT contra la empresa real (Microsoft Entra ID):** ver
`discovery-connectors/entra_id.py` para las instrucciones completas de configuración (registro
de app en Entra ID, permisos, admin consent) y cómo ejecutarlo contra el tenant real.

## Flujo de trabajo

Este repositorio sigue [GitHub Flow](https://docs.github.com/es/get-started/using-github/github-flow),
documentado en `CONTRIBUTING.md`. Las plantillas de Issues y Pull Requests ya están configuradas
en `.github/` y aplican igual que en el proyecto anterior.
