# Conectores de IdentityHub

Los conectores llenan el inventario con los datos reales del proveedor de identidad de la
empresa. Se configuran desde el panel, en la pestaña **Integraciones**. Solo pueden hacerlo
usuarios con el rol `admin-ti`.

| Conector | Estado | Qué trae |
|---|---|---|
| Microsoft Entra ID | Disponible | Usuarios, aplicaciones empresariales, asignaciones y permisos OAuth (Shadow IT) |
| Google Workspace | Próximamente | — |
| Keycloak | Próximamente | Deshabilitar la cuenta en el SSO al ejecutar un offboarding (RF-08) |

## Microsoft Entra ID

### 1. Registrar la app en el tenant

Lo hace un administrador de Entra ID con rol de *Administrador global* o de *Administrador de
aplicaciones*. Tarda unos 5 minutos.

1. En <https://entra.microsoft.com>, ve a **Applications → App registrations → New registration**.
   - Nombre: `IdentityHub`.
   - Tipo de cuenta: *Accounts in this organizational directory only*.
   - Sin URL de redirección.
2. En **API permissions**, ve a **Add a permission → Microsoft Graph → Application permissions**,
   agrega **`Directory.Read.All`** y pulsa **Grant admin consent for …**.
3. En **Certificates & secrets**, ve a **New client secret**, elige una vigencia (máximo 24 meses)
   y copia el **Value**. Solo se muestra una vez.
4. En **Overview**, copia el **Directory (tenant) ID** y el **Application (client) ID**.

`Directory.Read.All` es de solo lectura: IdentityHub no puede crear, cambiar ni borrar nada en
el tenant.

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
| *Faltan permisos: … Directory.Read.All* | Falta el permiso o el **Grant admin consent** (paso 2 del registro). |
| *La sincronización se interrumpió por un reinicio del servidor* | Render reinició el servicio a mitad de la sincronización. Pulsa **Sincronizar ahora**. |
| *No se pudo leer el secreto guardado* | Cambió `CONECTORES_CLAVE`. Vuelve a ingresar el secreto en **Configurar**. |

## Script de línea de comandos

`discovery-connectors/entra_id.py` sigue disponible para importar solo los permisos OAuth desde
una terminal. Para el uso normal, el conector del panel lo reemplaza.
