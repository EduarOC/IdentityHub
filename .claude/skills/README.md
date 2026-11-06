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
| `emil-design-eng`, `animate`, `animation-performance`, `animation-vocabulary`, `break-ui`, `choreograph`, `find-animation-opportunities`, `improve-animations`, `mobile-native`, `remove-animations`, `review-animations` | [emilkowalski/skills](https://github.com/emilkowalski/skills), de Emil Kowalski | MIT (ver `LICENSE` en cada carpeta) | commit c8a7962 |

Notas:
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
