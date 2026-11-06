# Despliegue de IdentityHub en Render

Guía paso a paso para desplegar los 5 servicios y la base de datos desde `render.yaml`
en una cuenta propia de Render.

| Servicio | URL | Para qué |
|---|---|---|
| `identityhub-sso` | <https://identityhub-sso.onrender.com> | Keycloak (inicio de sesión) |
| `identityhub-panel` | <https://identityhub-panel.onrender.com> | Panel del inventario, solo rol `admin-ti` |
| `identityhub-gateway` | <https://identityhub-gateway.onrender.com> | Login delante del aplicativo legacy |
| `identityhub-inventario` | `https://identityhub-inventario.onrender.com` | API del inventario; responde `401` si no llega por el panel |
| `identityhub-legacy-app` | `https://identityhub-legacy-app.onrender.com` | Aplicativo legacy de demostración |
| `identityhub-datos` | — | PostgreSQL (Keycloak e inventario) |

## 1. Crear el Blueprint

1. Entrar a <https://dashboard.render.com> con la cuenta de GitHub dueña del repositorio.
2. **New → Blueprint** → elegir `EduarOC/IdentityHub`, rama `main`.
3. Render muestra los servicios de la tabla, todos en **Virginia**, y pide dos valores:
   - **`KEYCLOAK_ADMIN_PASSWORD`**: contraseña de la consola de Keycloak (usuario `admin`).
   - **`UAT_USER_PASSWORD`**: contraseña del usuario de prueba `ana.torres`, que tiene el
     rol `admin-ti` y por lo tanto entra al panel.

   Elegir contraseñas largas y guardarlas en el gestor de contraseñas antes de seguir.
4. **Apply**. El primer despliegue tarda varios minutos; Keycloak es el más lento.

Lo demás no se configura a mano:
- Render genera el secret del cliente OIDC (`identityhub-cliente-oidc`) y las dos cuentas de
  servicio. Keycloak toma el secret al importar el realm y los proxies lo leen del mismo grupo.
- El realm (`keycloak-realm/identityhub-realm.json`) ya trae el rol `admin-ti`, el usuario de
  prueba y las URL de retorno y de cierre de sesión de `identityhub-gateway` e
  `identityhub-panel`.

## 2. Verificar las URLs

Si Render le agregó un sufijo a algún nombre (porque ya existía), actualizar la URL en
`render.yaml` y en el realm, y como Keycloak ya importó el realm, también en la consola:

| Si cambió la URL de… | Actualizar |
|---|---|
| `identityhub-sso` | `KC_HOSTNAME`, `KEYCLOAK_URL` y `KEYCLOAK_EXTERNAL_URL` |
| `identityhub-gateway` o `identityhub-panel` | Consola de Keycloak → realm `identityhub` → Clients → `auth-proxy`: *Valid redirect URIs*, *Valid post logout redirect URIs* y *Web origins* |
| `identityhub-legacy-app` | `BACKEND_URL` de `identityhub-gateway` |
| `identityhub-inventario` | `BACKEND_URL` de `identityhub-panel` |

## 3. Probar

Abrir primero Keycloak y esperar a que cargue (arranque en frío), luego:

| Caso | Qué hacer | Resultado esperado |
|---|---|---|
| CP-U01 | Abrir `https://identityhub-gateway.onrender.com` e iniciar sesión con `ana.torres` | Entra al aplicativo legacy |
| CP-U04 | Después del login, navegar en el aplicativo | Muestra el usuario real (`X-Forwarded-User`) |
| CP-U06 | Abrir `https://identityhub-panel.onrender.com` e iniciar sesión con `ana.torres` | Panel con aplicativos, usuarios y Shadow IT; arriba, el usuario conectado y «Cerrar sesión» |
| — | Abrir directamente `https://identityhub-inventario.onrender.com` | `401`: el inventario solo responde al panel |
| — | Iniciar sesión en el panel con un usuario sin el rol `admin-ti` | «Acceso denegado» |

La skill `evidencias-uat-panel` corre estos casos con `--entorno render`.

## 4. Cómo funciona el acceso al panel

`identityhub-panel` es la misma imagen del gateway con `PROXY_REQUIRED_ROLE=admin-ti`: pide
iniciar sesión en Keycloak, deja pasar solo a quien tenga ese rol de realm y reenvía al
inventario con su cuenta de servicio (`identityhub-cuenta-inventario`). El inventario rechaza
con `401` cualquier petición sin esa cuenta, salvo `/salud`. El offboarding registra como
responsable el correo de quien inició sesión.

Para dar acceso a otra persona: consola de Keycloak → realm `identityhub` → **Users** →
crear o elegir el usuario → **Role mapping → Assign role** → `admin-ti`.

**Conectar el tenant:** desde el panel, en **Integraciones** (ver `docs/CONECTORES.md`). El
secreto se guarda cifrado con `CONECTORES_CLAVE`, que Render genera.

**Script de línea de comandos (opcional):** para importar al inventario desplegado, definir
`INVENTORY_URL=https://identityhub-inventario.onrender.com`,
`INVENTORY_SERVICE_USER=svc-inventario` e `INVENTORY_SERVICE_PASSWORD` con el valor generado
en `identityhub-cuenta-inventario` (Render → Env Groups).

## 5. Si algo falla

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Keycloak se reinicia o muestra *Out of memory* | 512 MB no alcanzan | Subir `identityhub-sso` a un plan pago (Starter) |
| *Invalid parameter: redirect_uri* en el login | La URL del proxy no está registrada en Keycloak | Revisar la sección 2 |
| *Invalid client credentials* | El secret de Keycloak y el de los proxies no coinciden | Los tres servicios deben usar el grupo `identityhub-cliente-oidc`; si se cambió el secret en la consola, copiarlo al grupo |
| El inventario no conecta a la base | La base aún se está creando | Esperar a que la base esté *Available* y redesplegar |
| «Acceso denegado» al entrar al panel | El usuario no tiene el rol `admin-ti` | Asignarlo (sección 4) y volver a iniciar sesión |
| *Invalid redirect uri* al cerrar sesión | Falta la URL de cierre de sesión en el cliente | Sección 2 |
| El panel responde `401` | Las cuentas de servicio no coinciden | `identityhub-panel` e `identityhub-inventario` deben usar el grupo `identityhub-cuenta-inventario` |

## 6. Mantenimiento

- **Base gratuita:** expira 30 días después de creada y se borra 14 días más tarde, sin
  respaldos. Para uso continuo, pasarla a un plan pago antes de esa fecha.
- **El realm se importa una sola vez.** Cambios posteriores en `identityhub-realm.json` no
  llegan a un Keycloak ya creado: hacerlos también en la consola.
- **Servicios gratuitos:** se duermen tras 15 minutos sin tráfico y tardan cerca de un
  minuto en despertar. No usar servicios de "ping" para mantenerlos despiertos: se agotan las
  750 horas gratuitas del mes.
