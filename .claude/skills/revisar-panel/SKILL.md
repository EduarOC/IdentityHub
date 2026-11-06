---
name: revisar-panel
description: Revisa y mejora el panel web del inventario de IdentityHub (inventory-service/templates/dashboard.html, static/style.css y static/dashboard.js) viéndolo de verdad en el navegador. Levanta el panel en local con datos de ejemplo, toma capturas de escritorio y móvil, audita diseño, accesibilidad, responsive, estados vacíos y datos extremos, aplica las mejoras y vuelve a capturar para comparar. Úsala siempre que se pida mejorar, pulir, rediseñar, revisar o "hacer ver mejor" el panel, la página, el dashboard o la interfaz de IdentityHub, o cuando se toque cualquier archivo de inventory-service/templates o inventory-service/static, aunque no se diga "revisar".
---

# Revisar y pulir el panel de IdentityHub

El panel es una herramienta de operación: lo usa un administrador de TI para ver el inventario, ejecutar un retiro de accesos (offboarding) y priorizar el Shadow IT. Su trabajo es que esas tres tareas sean claras, rápidas y difíciles de equivocar. Una mejora visual que haga más llamativa la pantalla pero más lenta o ambigua la tarea es un retroceso.

## Contexto del código

- `inventory-service/templates/dashboard.html`: estructura. Las secciones son indicadores (KPI), usuarios (`#tabla-usuarios`), catálogo (`#tabla-aplicativos`) y Shadow IT (`#shadow-grid`).
- `inventory-service/static/style.css`: los colores y medidas viven como variables en `:root` (`--navy`, `--orange`, `--red`, `--green`, `--ink`, `--ink-soft`…). Usa siempre esas variables; si hace falta un color nuevo, agrégalo ahí con nombre semántico.
- `inventory-service/static/dashboard.js`: pinta los datos de `/api/usuarios`, `/api/aplicativos` y `/api/aplicativos/riesgo`, y llama a `POST /api/usuarios/{id}/offboarding`. No cambies la forma de esas respuestas desde el panel: las pruebas de `inventory-service/tests` y el conector dependen de ellas.
- La identidad visual institucional (FESNA) es azul `#0A499C` y naranja `#FD531E`; el panel usa su propia paleta navy/naranja. Mantén la coherencia con la que ya existe salvo que el usuario pida otra.

## Flujo

1. **Levanta el panel y captura el estado actual.**
   ```bash
   bash .claude/skills/revisar-panel/scripts/levantar_panel.sh        # http://127.0.0.1:5055, SQLite temporal con datos de ejemplo
   python .claude/skills/revisar-panel/scripts/capturas.py antes        # escritorio 1440 px y móvil 390 px
   ```
   Las capturas quedan en `.claude/skills/revisar-panel/capturas/<etiqueta>/` (carpeta ignorada por git). Míralas antes de opinar: revisar el código sin ver la pantalla deja pasar la mitad de los problemas.

2. **Audita** con la lista de [references/checklist.md](references/checklist.md). Para ir más hondo puedes apoyarte en las skills instaladas en el repositorio:
   - `impeccable` (modo *audit*, *polish*, *clarify*, *layout*, *typeset*): el panel es una superficie de modo **Operate**, así que la ambición se traduce en precisión y contención, no en efectos.
   - `break-ui`: alimenta el panel con nombres larguísimos, correos sin espacios, listas vacías o 200 usuarios. El script `capturas.py --extremos` ya siembra un caso así.
   - `review-animations` / `emil-design-eng`: solo si vas a tocar transiciones (el toast, los hover). En una herramienta que se usa a diario, la mayoría de interacciones no deberían animarse.

3. **Presenta los hallazgos ordenados por impacto** antes de editar si el cambio es grande; si son ajustes pequeños y claros, aplícalos directamente.

4. **Aplica las mejoras** en los tres archivos, respetando las variables de `:root` y el contrato de la API.

5. **Verifica.**
   ```bash
   python .claude/skills/revisar-panel/scripts/capturas.py despues
   python -m pytest inventory-service/tests -q
   ```
   Compara `antes/` y `despues/` mirándolas, y comprueba que las pruebas siguen pasando. Al terminar, detén el servidor con `bash .claude/skills/revisar-panel/scripts/levantar_panel.sh stop`.

6. **Cierra con la skill `verificar-antes-del-pr`** para llevar el cambio a una rama y un PR. Nunca directo a `main`.

## Reglas que no se negocian

- **Contraste WCAG AA** (4,5:1 en texto normal, 3:1 en texto grande e íconos). SonarCloud ya marcó un contraste insuficiente una vez (`css:S7924`).
- **No insertes datos del servidor con `innerHTML` sin escapar.** Hoy `dashboard.js` arma filas con `innerHTML` y los nombres pueden venir de Microsoft Entra ID: un nombre con `<img onerror=…>` se ejecutaría. Si tocas esas funciones, usa `textContent` o una función de escape.
- **El botón de offboarding es destructivo:** confirmación explícita con el nombre de la persona, estado deshabilitado mientras se procesa y mensaje de resultado claro.
- **Nada de datos reales en capturas ni en el código:** las capturas usan los datos de ejemplo; si alguna vez capturas datos reales, oculta nombres y correos (Ley 1581).
- **Textos en español**, claros y cortos.
