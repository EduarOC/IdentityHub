# Lista de revisión del panel

Revisa cada punto mirando las capturas, no solo el código. Anota el hallazgo con la sección del panel, el problema concreto y la corrección propuesta.

## 1. Tareas principales
- ¿Se entiende en cinco segundos cuántos aplicativos, usuarios, Shadow IT de alto riesgo y costo mensual hay?
- ¿El retiro de accesos se encuentra rápido y es imposible ejecutarlo por accidente (confirmación con el nombre, botón deshabilitado durante la petición, mensaje de resultado)?
- ¿El Shadow IT se lee de mayor a menor riesgo sin tener que interpretar colores (el puntaje y el nivel también están en texto)?

## 2. Jerarquía y lectura
- Un solo foco por sección; títulos, cifras y textos de ayuda con tamaños claramente distintos.
- Las cifras usan números tabulares (`font-variant-numeric: tabular-nums`) para que las columnas se alineen.
- Los costos llevan su moneda y formato colombiano o el que use el panel de forma consistente.

## 3. Accesibilidad
- Contraste AA en todo el texto, incluidos los textos de ayuda grises y las insignias de color.
- El color nunca es la única señal (riesgo, estado activo/offboarding).
- Se puede usar con teclado: foco visible en botones y enlaces; orden de tabulación lógico.
- Las tablas tienen encabezados `<th>` con `scope`; los botones tienen texto o `aria-label` que diga qué hacen y a quién.
- El toast se anuncia a lectores de pantalla (`role="status"` o `aria-live="polite"`).

## 4. Estados
- Cargando: algo distinto de un «—» eterno si la API tarda (el plan gratuito de Render tarda hasta un minuto en despertar).
- Vacío: tablas sin filas y Shadow IT sin hallazgos tienen un mensaje útil.
- Error: si una llamada falla, el panel lo dice en vez de quedarse en blanco.

## 5. Datos extremos (`capturas.py --extremos`)
- Nombres y correos muy largos no rompen la tabla (ajuste o recorte con `title`).
- Muchos usuarios: la tabla se puede recorrer sin que la página se vuelva inmanejable.
- Caracteres especiales y acentos se ven bien; ningún dato se interpreta como HTML.

## 6. Responsive
- A 390 px de ancho no hay desplazamiento horizontal de la página; las tablas anchas se desplazan dentro de su contenedor.
- Los botones miden al menos 44 × 44 px en táctil.

## 7. Movimiento
- Solo lo que comunica algo se anima (el toast al aparecer, el cambio de estado tras el retiro).
- Respeta `prefers-reduced-motion`.
- Duraciones cortas (150–250 ms) y sin rebotes en una herramienta de trabajo diario.

## 8. Seguridad visible
- Ningún dato del servidor se inserta con `innerHTML` sin escapar.
- No se muestran secretos, tokens ni configuraciones del conector en la página.
