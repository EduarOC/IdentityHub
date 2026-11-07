# Skills de Claude Code para IdentityHub

Claude Code carga automáticamente las skills de esta carpeta cuando se trabaja en el repositorio. Cada skill es un conjunto de instrucciones (y a veces scripts) que Claude sigue cuando la tarea coincide con su descripción. También se pueden invocar por nombre: `/revisar-panel`, `/impeccable audit`, etc.

## Skills propias del proyecto

| Skill | Para qué |
|---|---|
| `revisar-panel` | Levanta el panel del inventario en local, lo captura en escritorio y móvil, lo audita (diseño, accesibilidad, responsive, estados, datos extremos) y aplica mejoras verificándolas con capturas de antes y después. |
| `ruta-segura-inventario` | Lista de control para cualquier ruta nueva o modificada de la API o del panel: control de acceso, auditoría que no se borra, validación, secretos, salida segura y pruebas. Nace de los incidentes del 27/10, 05/11 y 06/11/2026. |
| `verificar-antes-del-pr` | Verificación local (rama, pruebas, cobertura ≥ 80 %, secretos y patrones peligrosos en el diff) y apertura del PR con la plantilla; revisa CI y el Quality Gate de SonarCloud. |
| `evidencias-uat-panel` | Ejecuta los casos de aceptación CP-U01 a CP-U11 con Playwright (local o Render) y deja capturas con datos personales ocultos y un registro listo para 07_QA_y_UAT. |

Requisitos para sus scripts: Python 3.12 con las dependencias de `inventory-service` y `playwright` (`pip install playwright && playwright install chromium`).

## Skills de terceros incluidas

Copiadas sin modificaciones desde sus repositorios oficiales; cada carpeta conserva su licencia.

| Skill | Origen | Licencia | Versión |
|---|---|---|---|
| `impeccable` | [pbakaus/impeccable](https://github.com/pbakaus/impeccable), de Paul Bakaus | Apache 2.0 (ver `impeccable/LICENSE` y `impeccable/NOTICE.md`) | commit c3bb418 (skill 4.8.0) |
| 25 skills de ingeniería: `using-agent-skills` (la que enruta a las demás), `spec-driven-development`, `planning-and-task-breakdown`, `incremental-implementation`, `test-driven-development`, `code-review-and-quality`, `code-simplification`, `security-and-hardening`, `debugging-and-error-recovery`, `api-and-interface-design`, `documentation-and-adrs`, `git-workflow-and-versioning`, `ci-cd-and-automation`, `shipping-and-launch`, `observability-and-instrumentation`, `performance-optimization`, `deprecation-and-migration`, `frontend-ui-engineering`, `browser-testing-with-devtools`, `source-driven-development`, `context-engineering`, `constraint-driven-development`, `doubt-driven-development`, `idea-refine`, `interview-me` | [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills), de Addy Osmani | MIT (ver `LICENSE` en cada carpeta) | commit 301b02b |
| Listas de verificación que usan esas skills (seguridad, rendimiento, accesibilidad, observabilidad, definición de terminado, pruebas, orquestación) | mismo repositorio, carpeta `references/`; copiadas en `.claude/references/` para que los enlaces `../../references/…` funcionen | MIT (`.claude/references/LICENSE`) | commit 301b02b |
| `ponytail`, `ponytail-review`, `ponytail-audit`, `ponytail-debt`, `ponytail-help` | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail), de Dietrich Gebert | MIT (ver `LICENSE` en cada carpeta) | commit 96608e0 |
| `graphify` (con sus `references/` para Claude Code) | [safishamsi/graphify](https://github.com/safishamsi/graphify), de Safi Shamsi | Apache 2.0 (ver `graphify/LICENSE` y `graphify/NOTICE`; el repositorio también ofrece MIT en `LICENSE-MIT`) | commit 16218bf (graphifyy 0.9.103) |
| `emil-design-eng`, `animate`, `animation-performance`, `animation-vocabulary`, `break-ui`, `choreograph`, `find-animation-opportunities`, `improve-animations`, `mobile-native`, `remove-animations`, `review-animations` | [emilkowalski/skills](https://github.com/emilkowalski/skills), de Emil Kowalski | MIT (ver `LICENSE` en cada carpeta) | commit c8a7962 |

Notas:
- **Cuál usar cuando hay dos parecidas.** En este repositorio mandan las skills propias:
  `ruta-segura-inventario` antes que `security-and-hardening` para rutas de la API (la segunda
  sirve como lista general y para dependencias); `verificar-antes-del-pr` para subir cambios
  (las de Addy sobre git y CI son guía, no reemplazan el script del proyecto). Para revisar un
  cambio, `ponytail-review` o `code-review-and-quality`; para buscar código que sobra, `ponytail`
  y `ponytail-audit`.
- **Addy Osmani.** `using-agent-skills` es la meta-skill que decide qué skill aplica.
  `browser-testing-with-devtools` necesita el servidor MCP de Chrome DevTools; sin él, usa
  Playwright como en `revisar-panel`. `idea-refine` puede crear la carpeta `docs/ideas/` con su
  script `scripts/idea-refine.sh` (solo hace `mkdir`). No se copiaron sus comandos (`/spec`,
  `/plan`…), agentes ni *hooks*: solo las skills y sus listas de referencia.
- **Ponytail.** Se excluyó `ponytail-gain`, que solo muestra los resultados de los *benchmarks*
  del autor y depende de archivos que no están aquí. Sus comentarios `shortcut:` en el código
  marcan deuda técnica a propósito; `ponytail-debt` los lista.
- **Graphify** necesita su programa de línea de comandos. Instálalo fijando la versión, para que
  la skill no instale la última por su cuenta:

  ```bash
  uv tool install graphifyy==0.9.103
  ```

  Luego `/graphify .` crea `graphify-out/` (ignorada por git) con el grafo, un informe y una
  visualización. Para extraer documentos, imágenes o videos usa un modelo de lenguaje: con
  Claude Code usa la propia sesión; fuera de ella pide una clave de API. **No se ejecutó
  `graphify install`**: ese comando agregaría *hooks* que corren el programa antes de cada
  búsqueda de archivos y editaría `CLAUDE.md`. Si alguien los quiere, que los active solo en su
  equipo, no en el repositorio.
- Las descripciones de todas las skills suman unos 19.000 caracteres (≈ 4.800 tokens) que Claude Code
  carga al iniciar cada sesión; el contenido completo de cada una solo se lee cuando se usa.
- **Impeccable** usa un programa auxiliar (`impeccable/scripts/impeccable`) que, la primera vez, descarga su motor desde los *releases* de GitHub de pbakaus/impeccable y verifica su SHA-256 contra `engine-checksums.txt` antes de ejecutarlo. Si la descarga no es posible, la skill sigue funcionando leyendo sus guías. Su hook de detección de diseño es opcional y solo se activa con `/impeccable hooks on`.
- Para el panel, Impeccable lo trata como una superficie de modo **Operate**: precisión y contención, no efectos llamativos.
- De Emil Kowalski se excluyeron las skills de React Native, Swift y bibliotecas de React (`animate-expo`, `write-swift`, `ask-sonner`, `pick-ui-library`), y `apple-design` y `prototype`, que no aplican a un panel en HTML, CSS y JavaScript sin frameworks.

### Taste (no incluida)

[Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) (MIT) está pensada para sitios web de empresas y páginas de aterrizaje: fotos, escenas y efectos de *shader*. Además, depende de unos 38 MB de recursos. No encaja con un panel de administración y engordaría el repositorio, así que no se copió. Si el equipo hace una página pública del producto (por ejemplo, para el plan de negocio), se puede instalar solo en el equipo de quien la necesite:

```bash
npx -y skills add leonxlnx/taste-skill --skill design-taste-frontend --agent claude-code
```

## Actualizar las skills de terceros

Vuelve a copiar la carpeta desde el repositorio original, revisa el diff (sobre todo los scripts) y actualiza la columna «Versión» de esta tabla.
