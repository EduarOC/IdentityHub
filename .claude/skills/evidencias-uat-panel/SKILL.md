---
name: evidencias-uat-panel
description: Ejecuta los casos de prueba de aceptación (UAT) de IdentityHub, CP-U01 a CP-U11, con Playwright sobre el entorno local o sobre Render, y deja capturas con nombres y correos ocultos (Ley 1581) más un registro con el resultado de cada caso, listos para la carpeta 07_QA_y_UAT del Drive y para el plan de pruebas IH-QA-01. Úsala siempre que se pidan evidencias, capturas, pruebas de aceptación, UAT, «probar el login», «probar el offboarding» o preparar una demostración o una auditoría del sistema.
---

# Evidencias UAT del panel

Las pruebas de aceptación demuestran, desde la interfaz, que cada historia de usuario cumple sus criterios. Hasta ahora se ejecutaban a mano y las capturas no llegaron al Drive; el documento de grado las cita como evidencia. Esta skill las hace repetibles.

## Casos

| ID | Historia | Qué comprueba | Automatizado |
|---|---|---|---|
| CP-U01 | HU-01 | Inicio de sesión con credenciales válidas en Keycloak | Sí |
| CP-U02 | HU-01 | Contraseña incorrecta: Keycloak rechaza y no hay sesión | Sí |
| CP-U03 | HU-02 | Legacy sin sesión → redirige a Keycloak | Sí |
| CP-U04 | HU-02 | Legacy con sesión → entra sin otra credencial y muestra el usuario real | Sí |
| CP-U05 | HU-03 | Cierre de sesión → vuelve a pedir autenticación | Sí |
| CP-U06 | HU-04 | Panel muestra aplicativos con SSO y costo, y usuarios con accesos | Sí |
| CP-U07 | HU-06 | Offboarding desde el panel revoca todos los accesos | Sí, **solo en local** |
| CP-U08 | HU-06 / RNF-10 | Offboarding en máximo 3 clics sin capacitación | Manual (una persona real) |
| CP-U09 | HU-08 | El retiro queda registrado con responsable, fecha y aplicativos | Sí, **solo en local** (vía API) |
| CP-U10 | HU-10 | Shadow IT ordenado de mayor a menor riesgo | Sí |
| CP-U11 | HU-07 | Bloqueo en Keycloak tras el retiro | Sí, **solo en local** y con el conector de Keycloak conectado; se lee del mismo offboarding de CP-U07 |

## Cómo ejecutarlo

Credenciales por variables de entorno, nunca en el código ni en el comando visible en capturas:

```bash
export UAT_USUARIO=ana.torres
export UAT_CLAVE='…'                      # contraseña del usuario de prueba
python .claude/skills/evidencias-uat-panel/scripts/uat.py --entorno local    # proxy :9000, panel por inventory-proxy :9100 (docker compose up -d)
python .claude/skills/evidencias-uat-panel/scripts/uat.py --entorno render   # URLs públicas de Render
```

El panel (CP-U06, CP-U07, CP-U09, CP-U10) también pide iniciar sesión: el usuario de prueba necesita el rol `admin-ti` en Keycloak.

Opciones útiles: `--casos CP-U01,CP-U06`, `--salida <carpeta>`. En Render el plan gratuito tarda hasta un minuto en despertar: el script espera, pero conviene abrir las URL antes.

Salida en `evidencias-uat/<fecha>-<entorno>/` (ignorada por git):
- `CP-Uxx.png`: una captura por caso, con nombres y correos de las tablas difuminados antes de capturar.
- `registro.md`: tabla con caso, resultado (Aprobado, Fallido, Fallo esperado, Manual u Omitido), detalle y archivo de evidencia, lista para pegar en IH-QA-01.

## Reglas

- **CP-U07 y CP-U09 modifican datos** (revocan los accesos de un usuario). El script los omite en Render; ejecútalos solo en local o con el permiso explícito del equipo.
- **Datos personales:** si el entorno tiene datos reales (un tenant real), revisa cada captura antes de subirla. El difuminado cubre las columnas de nombre y correo de la tabla de usuarios, no textos que aparezcan en otros lugares.
- **No inventes resultados.** Un caso que no se pudo ejecutar queda como «Omitido» con el motivo; CP-U11 queda «Omitido» si el conector de Keycloak no está conectado.
- Al terminar, sube la carpeta a `07_QA_y_UAT` del Drive y actualiza la tabla de casos UAT del plan de pruebas.
