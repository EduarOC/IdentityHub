# Despliegue de IdentityHub en Render

Guía paso a paso para desplegar los 4 servicios y la base de datos desde `render.yaml`.
Contexto, límites del plan gratuito, DRP y BCP: documento IH-ARQ-01 (secciones 9 a 12).

## 1. Crear el Blueprint

1. Entrar a <https://dashboard.render.com> con la cuenta del equipo.
2. **New → Blueprint** → conectar GitHub → elegir `EduarOC/IdentityHub`, rama `main`.
3. Render lee `render.yaml` y muestra lo que va a crear:
   `identityhub-keycloak`, `identityhub-auth-proxy`, `identityhub-legacy`,
   `identityhub-inventory` y la base `identityhub-db`, todo en **Virginia**.
4. Render pide el valor de **`PROXY_CLIENT_SECRET`** (es la única variable manual).
   Poner el mismo valor del campo `"secret"` del cliente `auth-proxy` en
   `keycloak-realm/identityhub-realm.json`.
5. **Apply**. El primer despliegue tarda varios minutos; Keycloak es el más lento.

## 2. Verificar las URLs

Cada servicio queda en `https://<nombre>.onrender.com`. Si Render le agregó un sufijo a
algún nombre (porque ya existía), hay que actualizar:

| Si cambió la URL de… | Actualizar |
|---|---|
| Keycloak | `KC_HOSTNAME` (Keycloak) y `KEYCLOAK_URL` (proxy e inventario) |
| Auth Proxy | URL de retorno del cliente `auth-proxy` en la consola de Keycloak (Clients → auth-proxy → Valid redirect URIs) |
| Aplicativo legacy | `BACKEND_URL` (proxy) |

## 3. Probar

Abrir primero Keycloak y esperar a que cargue (arranque en frío), luego:

| Caso | Qué hacer | Resultado esperado |
|---|---|---|
| CP-U01 | Abrir `https://identityhub-auth-proxy.onrender.com` e iniciar sesión con `ana.torres` / `identityhub123` | Entra al aplicativo legacy |
| CP-U04 | Después del login, navegar en el aplicativo | Muestra el usuario real (`X-Forwarded-User`) |
| CP-U06 | Abrir `https://identityhub-inventory.onrender.com` | Panel con aplicativos, usuarios y Shadow IT de ejemplo |

Guardar capturas en `07_QA_y_UAT` del Drive.

## 4. Si algo falla

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Keycloak se reinicia o muestra *Out of memory* | 512 MB no alcanzan | Plan B (IH-ARQ-01, 12.6): Keycloak local y el resto en Render |
| *Invalid parameter: redirect_uri* en el login | La URL del proxy no está registrada en Keycloak | Revisar el paso 2 |
| *Invalid client credentials* | `PROXY_CLIENT_SECRET` no coincide con el realm | Corregir la variable en el panel del proxy |
| El inventario no conecta a la base | La base aún se está creando | Esperar a que la base esté *Available* y redesplegar |

## 5. Mantenimiento

- **Base gratuita:** expira 30 días después de creada y se borra 14 días más tarde. Antes
  de la sustentación, pasarla a *Basic* o recrearla (IH-ARQ-01, sección 11).
- **Contraseña de administrador de Keycloak:** Render la generó sola; está en
  `identityhub-keycloak → Environment → KEYCLOAK_ADMIN_PASSWORD`. Guardarla en el gestor
  de contraseñas del equipo.
- No usar servicios de "ping" para mantenerlos despiertos: se agotan las 750 horas gratuitas.
