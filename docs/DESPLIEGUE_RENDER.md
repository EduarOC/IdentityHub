# Despliegue de IdentityHub en Render

Guía paso a paso para desplegar los 4 servicios y la base de datos desde `render.yaml`.
Contexto, límites del plan gratuito, DRP y BCP: documento IH-ARQ-01 (secciones 9 a 12).

## 1. Crear el Blueprint

1. Entrar a <https://dashboard.render.com> con la cuenta del equipo.
2. **New → Blueprint** → conectar GitHub → elegir `EduarOC/IdentityHub`, rama `main`.
3. Render lee `render.yaml` y muestra lo que va a crear:
   `identityhub-keycloak`, `identityhub-auth-proxy`, `identityhub-legacy`,
   `identityhub-inventory`, `identityhub-inventory-proxy` y la base `identityhub-db`,
   todo en **Virginia**.
4. Render pide el valor de **`PROXY_CLIENT_SECRET`** para los dos proxies (es la única
   variable manual; el mismo valor en ambos).
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
| Inventario | `BACKEND_URL` (inventory-proxy) |
| Inventory Proxy | URL de retorno y de cierre de sesión del cliente `auth-proxy` en Keycloak |

## 3. Probar

Abrir primero Keycloak y esperar a que cargue (arranque en frío), luego:

| Caso | Qué hacer | Resultado esperado |
|---|---|---|
| CP-U01 | Abrir `https://identityhub-auth-proxy.onrender.com` e iniciar sesión con `ana.torres` / `identityhub123` | Entra al aplicativo legacy |
| CP-U04 | Después del login, navegar en el aplicativo | Muestra el usuario real (`X-Forwarded-User`) |
| CP-U06 | Abrir `https://identityhub-inventory-proxy.onrender.com` e iniciar sesión con un usuario que tenga el rol `admin-ti` | Panel con aplicativos, usuarios y Shadow IT; arriba, el usuario conectado y «Cerrar sesión» |
| — | Abrir directamente `https://identityhub-inventory-a46j.onrender.com` | `401`: el inventario solo responde al proxy |
| — | Iniciar sesión en el panel con un usuario sin el rol `admin-ti` | «Acceso denegado» |

Guardar capturas en `07_QA_y_UAT` del Drive.

## 4. Panel del inventario con inicio de sesión

El panel ya no se abre directamente: `identityhub-inventory-proxy` (la misma imagen del
auth-proxy) pide iniciar sesión en Keycloak, deja pasar solo a quien tenga el rol de realm
**`admin-ti`** y reenvía al inventario con una cuenta de servicio propia
(`identityhub-cuenta-inventario`). El inventario rechaza con `401` cualquier petición sin esa
cuenta, salvo `/salud`. El offboarding registra como responsable el correo de quien inició
sesión.

**Keycloak ya desplegado no vuelve a importar el realm** (`--import-realm` omite un realm que
ya existe). En la consola de administración (`/admin`, realm `identityhub`) hacer a mano:

1. **Realm roles → Create role** → `admin-ti`.
2. **Users →** cada administrador de TI **→ Role mapping → Assign role** → `admin-ti`.
3. **Clients → auth-proxy → Settings**:
   - *Valid redirect URIs*: agregar `https://identityhub-inventory-proxy.onrender.com/auth/callback`.
   - *Valid post logout redirect URIs*: `https://identityhub-auth-proxy.onrender.com/login` y
     `https://identityhub-inventory-proxy.onrender.com/login`.
   - *Web origins*: agregar `https://identityhub-inventory-proxy.onrender.com`.
4. Si Render le puso sufijo a `identityhub-inventory-proxy`, usar esa URL en el paso 3.

**Datos reales:** si la base ya tiene usuarios importados de un tenant real, quedaron
expuestos mientras el panel fue público. Revisar quién pudo verlos y, si no se necesitan,
borrarlos antes de seguir con pruebas (Ley 1581).

**Conector de Entra ID:** para importar al inventario desplegado, definir
`INVENTORY_URL`, `INVENTORY_SERVICE_USER=svc-inventario` e `INVENTORY_SERVICE_PASSWORD` con
el valor generado en `identityhub-cuenta-inventario` (Render → Env Groups).

## 5. Si algo falla

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Keycloak se reinicia o muestra *Out of memory* | 512 MB no alcanzan | Plan B (IH-ARQ-01, 12.6): Keycloak local y el resto en Render |
| *Invalid parameter: redirect_uri* en el login | La URL del proxy no está registrada en Keycloak | Revisar el paso 2 |
| *Invalid client credentials* | `PROXY_CLIENT_SECRET` no coincide con el realm | Corregir la variable en el panel del proxy |
| El inventario no conecta a la base | La base aún se está creando | Esperar a que la base esté *Available* y redesplegar |
| «Acceso denegado» al entrar al panel | El usuario no tiene el rol `admin-ti` | Asignarlo en Keycloak (sección 4) y volver a iniciar sesión |
| *Invalid redirect uri* al cerrar sesión | Falta la URL de cierre de sesión en el cliente | Sección 4, paso 3 |
| El panel responde `401` dentro del proxy | Las cuentas de servicio no coinciden | Los dos servicios deben usar el grupo `identityhub-cuenta-inventario` |

## 6. Mantenimiento

- **Base gratuita:** expira 30 días después de creada y se borra 14 días más tarde. Antes
  de la sustentación, pasarla a *Basic* o recrearla (IH-ARQ-01, sección 11).
- **Contraseña de administrador de Keycloak:** Render la generó sola; está en
  `identityhub-keycloak → Environment → KEYCLOAK_ADMIN_PASSWORD`. Guardarla en el gestor
  de contraseñas del equipo.
- No usar servicios de "ping" para mantenerlos despiertos: se agotan las 750 horas gratuitas.
