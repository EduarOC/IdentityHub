# Conectores de IdentityHub

Los conectores llenan el inventario con los datos reales del proveedor de identidad de la
empresa. Se configuran desde el panel, en la pestaña **Integraciones**. Solo pueden hacerlo
usuarios con el rol `admin-ti`.

| Conector | Estado | Qué trae |
|---|---|---|
| Microsoft Entra ID | Disponible | Usuarios, aplicaciones empresariales, asignaciones y permisos OAuth (Shadow IT) |
| Google Workspace | Próximamente | — |
| Keycloak | Disponible | Al ejecutar un offboarding, deshabilita la cuenta en el SSO y cierra sus sesiones (RF-08) |

## Microsoft Entra ID

### 1. Registrar la app en el tenant

Lo hace un administrador de Entra ID con rol de *Administrador global* o de *Administrador de
aplicaciones*. Tarda unos 5 minutos.

1. En <https://entra.microsoft.com>, ve a **Applications → App registrations → New registration**.
   - Nombre: `IdentityHub`.
   - Tipo de cuenta: *Accounts in this organizational directory only*.
   - Sin URL de redirección.
2. En **API permissions**, ve a **Add a permission → Microsoft Graph → Application permissions**,
   agrega estos tres permisos y pulsa **Grant admin consent for …**:

   | Permiso | Para qué lo usa IdentityHub |
   |---|---|
   | `User.Read.All` | Leer los usuarios y si su cuenta está habilitada |
   | `Application.Read.All` | Leer las aplicaciones empresariales y a quién están asignadas |
   | `DelegatedPermissionGrant.Read.All` | Leer los permisos OAuth concedidos (Shadow IT) |

   Si ya aparece `User.Read` (delegado), puedes quitarlo: el conector no lo usa.
3. En **Certificates & secrets**, ve a **New client secret**, elige una vigencia (máximo 24 meses)
   y copia el **Value**. Solo se muestra una vez.
4. En **Overview**, copia el **Directory (tenant) ID** y el **Application (client) ID**.

Los tres son de solo lectura: IdentityHub no puede crear, cambiar ni borrar nada en el tenant.
Son los mínimos para lo que consulta. No se pide `Directory.Read.All`, que además leería grupos,
dispositivos, roles y el resto del directorio. Si el tenant ya se conectó con `Directory.Read.All`,
el conector sigue funcionando; para reducir el alcance, agrega los tres permisos, vuelve a
conceder el consentimiento y quita `Directory.Read.All`.

Sin `Organization.Read.All`, la tarjeta muestra el ID del tenant en lugar de su nombre. Es
opcional y no hace falta para nada más.

### 2. Conectar desde el panel

1. Abre **Integraciones → Microsoft Entra ID → Conectar**.
2. Pega los tres valores y pulsa **Guardar y conectar**.
3. El panel prueba la conexión (muestra el nombre del tenant) y empieza la primera
   sincronización. Cuando termina, avisa cuántos usuarios y aplicaciones trajo.

Después, usa **Sincronizar ahora** cada vez que quieras actualizar el inventario.

### Qué se sincroniza

| En Entra ID | En IdentityHub |
|---|---|
| Usuarios (`/users`) | Usuarios. Una cuenta deshabilitada queda *Inactivo*. |
| Aplicaciones empresariales (service principals con la etiqueta `WindowsAzureActiveDirectoryIntegratedApp`) | Catálogo de aplicativos, con el tipo de SSO configurado. |
| Asignaciones de usuarios a esas aplicaciones (`appRoleAssignedTo`) | Accesos del usuario. |
| Permisos OAuth delegados (`oauth2PermissionGrants`) | Shadow IT, con el puntaje de riesgo según los permisos concedidos. Si el consentimiento fue de un usuario, también queda como acceso de ese usuario. |

**Reglas que protegen la auditoría (RNF-11):**
- Nada se borra. Si un acceso deja de existir en Entra ID, se marca como revocado con la fecha
  de la sincronización.
- Un usuario que desaparece del tenant pasa a *Inactivo*.
- Un usuario en *Offboarding* conserva ese estado aunque siga habilitado en Entra ID. Si allá le
  vuelven a asignar una aplicación, el acceso aparece como vigente: es justo la señal de que el
  retiro quedó incompleto.
- **Desconectar** borra las credenciales y conserva todo lo sincronizado. Cada acción
  (configurar, probar, sincronizar, desconectar) queda en la tabla `eventos_conector` con su
  responsable.

**Limitaciones conocidas:**
- Las asignaciones hechas a grupos no se expanden a sus miembros.
- Entra ID no informa el costo de las licencias ni la fecha de último uso de los permisos OAuth.
  El costo aparece como «—», y el riesgo trata la falta de fecha como inactividad desconocida
  (+15).

### Seguridad del secreto

- El *client secret* se cifra con Fernet (AES-128 + HMAC) antes de guardarse en la base. La
  clave sale de la variable `CONECTORES_CLAVE`, que Render genera (`generateValue`).
- La API nunca devuelve el secreto: solo informa si existe (`tiene_secreto`).
- Si `CONECTORES_CLAVE` cambia, el secreto guardado deja de poder leerse y el panel pide
  ingresarlo de nuevo.
- Antes de que venza el secreto en Entra ID, crea uno nuevo y pégalo en **Configurar**. Si dejas
  el campo vacío, se conserva el anterior.

### Errores frecuentes

| Mensaje en la tarjeta | Qué hacer |
|---|---|
| *Microsoft rechazó las credenciales* | Revisa el Tenant ID y el Client ID. Comprueba que pegaste el **Value** del secreto (no el *Secret ID*) y que no haya expirado. |
| *Faltan permisos: la app necesita el permiso de aplicación …* | Falta el permiso que nombra el mensaje, o el **Grant admin consent** (paso 2 del registro). La prueba de conexión revisa los tres permisos uno por uno. |
| *La sincronización se interrumpió por un reinicio del servidor* | Render reinició el servicio a mitad de la sincronización. Pulsa **Sincronizar ahora**. |
| *No se pudo leer el secreto guardado* | Cambió `CONECTORES_CLAVE`. Vuelve a ingresar el secreto en **Configurar**. |

## Keycloak

Con este conector, el offboarding ya no se queda en el inventario: deshabilita la cuenta del
usuario en Keycloak y cierra todas sus sesiones abiertas (RF-08).

### 1. Crear el cliente en Keycloak

En la consola de administración (`KEYCLOAK_URL/admin`), dentro del realm de tus usuarios:

1. **Clients → Create client**, con Client ID `identityhub-inventario`. En el siguiente paso
   activa **Client authentication** y **Service accounts roles**, y desactiva **Standard flow**.
2. En la pestaña **Service accounts roles**, ve a **Assign role → Filter by clients** y asigna
   **`view-users`** y **`manage-users`** de `realm-management`. No le des más roles: son los
   mínimos para buscar y deshabilitar usuarios.
3. En la pestaña **Credentials**, copia el **Client secret**.

### 2. Conectar desde el panel

**Integraciones → Keycloak → Conectar**. Escribe el realm (por defecto `identityhub`), el
Client ID y el secreto, y pulsa **Guardar y conectar**. El panel comprueba que puede leer
usuarios.

La dirección del servidor no se escribe en el formulario: sale de la variable `KEYCLOAK_URL`
del inventario. Así nadie puede usar el conector para que el inventario haga peticiones a otro
servidor.

### Qué pasa en un offboarding

1. Se revocan los accesos en el inventario, como siempre.
2. Si Keycloak está **conectado**, se busca la cuenta por correo exacto (y, si no aparece, por
   nombre de usuario igual al correo). Se deshabilita y se cierran sus sesiones.
3. El resultado queda en `eventos_offboarding.resultado_sso` y se muestra en el panel:

| Resultado | Significado |
|---|---|
| `deshabilitado` | Cuenta deshabilitada y sesiones cerradas. |
| `no_encontrado` | El usuario no tiene cuenta en Keycloak. |
| `error` | Keycloak no respondió o faltan permisos. El retiro en el inventario se registró igual. Repite el offboarding para reintentar, o deshabilita la cuenta a mano. |
| `sin_conector` | El conector no está conectado: la cuenta en el SSO sigue activa. |

El panel no deja que un administrador ejecute su propio offboarding, para que no se quede sin
acceso.

**Pendiente (RF-09):** las sesiones ya abiertas en el auth-proxy duran hasta que vence su cookie.
Keycloak ya no renueva el acceso, pero el proxy todavía no consulta a Keycloak en cada petición.

## Script de línea de comandos

`discovery-connectors/entra_id.py` sigue disponible para importar solo los permisos OAuth desde
una terminal. Para el uso normal, el conector del panel lo reemplaza.
