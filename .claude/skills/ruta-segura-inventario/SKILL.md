---
name: ruta-segura-inventario
description: Lista de control obligatoria para agregar o cambiar rutas de la API o acciones del panel en los servicios de IdentityHub (inventory-service, auth-proxy, legacy-app-demo), sobre todo las que crean, modifican o borran datos, reciben credenciales o llaman a Microsoft Graph o a Keycloak. Cubre control de acceso, conservación de la auditoría, validación de entrada, manejo de secretos, salida segura en el panel y pruebas. Úsala siempre que se escriba o revise un @app.route nuevo, un endpoint, un botón que llame a la API, un conector o cualquier cambio en app.py de estos servicios, aunque el pedido sea solo «agrega un botón» o «haz que sincronice».
---

# Ruta segura en el inventario

Los servicios de IdentityHub están publicados en internet (Render). Tres incidentes salieron de rutas agregadas sin esta revisión:

| Fecha | Commit | Qué pasó |
|---|---|---|
| 27/10/2026 | d47afee | Ruta pública que cambiaba la contraseña de administración de Keycloak, con la contraseña escrita en el código (BUG-007). |
| 05/11/2026 | e4001a5…a71c5a6 | Rutas del conector de Entra ID sin autenticación; secreto del cliente y clave privada del certificado guardados en texto plano (BUG-008). |
| 06/11/2026 | 89900d8 | `POST /api/conector/entra-id/desconectar` sin autenticación: borraba todo el inventario y los eventos de auditoría con una petición anónima. |

Todos llegaron directo a `main` y SonarCloud los detectó después. Esta skill existe para detectarlos antes.

## Antes de escribir la ruta

Responde estas preguntas. Si alguna no tiene respuesta, detente y plantéala al usuario en vez de improvisar:

1. **¿Quién puede llamarla?** El inventario no tiene autenticación propia todavía. Una ruta de solo lectura con datos de demostración es aceptable; **una ruta que crea, modifica o borra datos, o que maneja credenciales, no se publica sin control de acceso.** Opciones, de mejor a peor:
   - Poner el panel detrás del `auth-proxy` (Keycloak) y exigir un rol de administrador que llegue en un encabezado firmado o validado por el proxy.
   - Un token de servicio en variable de entorno (`render.yaml` con `generateValue: true`), comparado con `hmac.compare_digest`.
   - Si nada de eso existe aún, la ruta no se hace. Se documenta como requisito pendiente.
2. **¿Toca datos de auditoría?** `accesos` y `eventos_offboarding` son la evidencia que exige ISO/IEC 27001 y que promete el documento de grado (RNF-11). **No se borran ni se editan.** Un «reinicio» o «desconectar» marca estados o fechas; no hace `delete()` sobre esas tablas.
3. **¿Maneja secretos?** Nada de secretos en el código, en `render.yaml` ni en respuestas de la API. Van en variables de entorno (`sync: false` o `generateValue`). Si hay que guardarlos en la base, se cifran con una clave que viene del entorno, y la API solo informa si existen (`tiene_secreto: true`), nunca su valor.
4. **¿Es destructiva o irreversible?** Exige confirmación explícita en el panel y deja un evento de auditoría con responsable y fecha.

## Al escribirla

- `methods=[...]` explícito (regla `python:S6965`).
- Entrada con `request.get_json(silent=True) or {}`; valida tipos y longitudes, y responde 400 con JSON (lección de BUG-001).
- IDs como `<int:...>`; consulta con el ORM, nunca SQL armado con texto del usuario.
- Errores sin detalles internos: nada de `str(e)` hacia el cliente; regístralo con `app.logger`.
- Llamadas externas (Graph, Keycloak) con `timeout=` y sin desactivar la verificación TLS.
- En el panel, los datos que vienen de la API se pintan con `textContent` o escapados, no con `innerHTML` (los nombres pueden venir de Entra ID).
- Si la ruta usa SHA-1, MD5 u otra primitiva débil porque un estándar lo exige (por ejemplo, la huella `x5t` de un certificado), déjalo comentado con la referencia, para justificar el hotspot en SonarCloud.

## Pruebas obligatorias

En `inventory-service/tests/` (usa los fixtures `client`, `inv` y `con_datos` de `conftest.py`). Cubre como mínimo:

- el camino feliz;
- la petición **sin autorización** → 401 o 403, y que no cambió nada en la base;
- entrada inválida o vacía → 400 en JSON;
- el recurso que no existe → 404;
- para acciones destructivas: que la auditoría sigue intacta después.

La cobertura del código nuevo debe quedar en 80 % o más (RNF-09 y Quality Gate). Comprueba con:

```bash
python -m pytest --cov --cov-config=.coveragerc -q
```

## Al terminar

Usa la skill `verificar-antes-del-pr`. El cambio va en una rama con PR; el CI corre las pruebas y SonarCloud, y el flujo falla si no se aprueba el Quality Gate.
