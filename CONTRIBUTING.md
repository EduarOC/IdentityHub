# Cómo contribuir a IdentityHub

Esta guía explica cómo se trabaja en el repositorio: configuración inicial, ramas, commits, Pull
Requests y lo que se revisa antes de fusionar. IdentityHub maneja identidades y accesos de
empresas, así que cada cambio pasa por pruebas, análisis de seguridad y un Pull Request.

## 1. Configuración inicial

1. Clona el repositorio:
   ```bash
   git clone https://github.com/EduarOC/IdentityHub.git
   cd IdentityHub
   ```
2. Configura tu identidad con un correo **vinculado a tu cuenta de GitHub**. Si no, los commits
   aparecen como anónimos en GitHub y en SonarCloud:
   ```bash
   git config user.name "Tu Nombre"
   git config user.email "el-correo-de-tu-cuenta-de-github@..."
   ```
3. Levanta el entorno local y corre las pruebas: pasos en el `README.md` (secciones *Entorno
   local* y *Pruebas*).

Si no tienes acceso de escritura, trabaja desde un *fork* y abre el Pull Request desde ahí.

## 2. Flujo de trabajo (GitHub Flow)

`main` está protegida: no admite cambios directos, *force push* ni borrado, y todo lo que llega
a ella se despliega en Render. Para cada tarea:

1. Actualiza tu copia de `main` y crea una rama:
   ```bash
   git checkout main && git pull origin main
   git checkout -b feat/nombre-corto-de-la-tarea
   ```
2. Haz commits pequeños y descriptivos.
3. Antes de subir, corre la verificación local (pruebas con cobertura, búsqueda de secretos y de
   patrones peligrosos): `bash .claude/skills/verificar-antes-del-pr/scripts/verificar.sh`.
4. Sube la rama y abre un **Pull Request** hacia `main` con la plantilla del repositorio.
5. Se fusiona solo con **las pruebas y el Quality Gate de SonarCloud en verde**. GitHub lo exige.
6. Borra la rama después de fusionar.

## 3. Nombres de rama

| Prefijo | Uso | Ejemplo |
|---|---|---|
| `feat/` | Funcionalidad nueva | `feat/conector-google-workspace` |
| `fix/` | Corrección de un error | `fix/proxy-static` |
| `docs/` | Documentación | `docs/readme-producto` |
| `test/` | Solo pruebas | `test/offboarding-keycloak` |
| `chore/` | Mantenimiento, dependencias, despliegue | `chore/despliegue-propio-render` |

## 4. Mensajes de commit

Formato: `tipo(alcance opcional): descripción corta en presente`, seguido de un cuerpo que
explica **qué** cambia y **por qué**.

Tipos: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

```
fix(proxy): reenviar /static al aplicativo protegido

Flask registra por defecto una ruta /static/<archivo> en el proxy, que
respondía 404 a los estilos y al JavaScript del panel del inventario.
```

Evita mensajes genéricos como «cambios» o «update».

## 5. Pull Requests

La plantilla (`.github/PULL_REQUEST_TEMPLATE.md`) pide:

- **Qué cambia** y **por qué**.
- **Cómo se probó**: comandos, casos verificados y lo que no se pudo probar.
- **Referencia de seguridad**: si el cambio toca seguridad, el control de OWASP ASVS o WSTG
  correspondiente.
- Si resuelve un Issue, `Closes #N`.

Un PR = un tema. Los PR que mezclan cambios no relacionados se dividen.

## 6. Reglas que no se negocian

- **Ningún secreto en el código ni en `render.yaml`:** van en variables de entorno
  (`sync: false` o `generateValue`). Los secretos que se guardan en la base van cifrados.
- **Toda ruta nueva de la API** pasa por la lista de control de la skill
  `ruta-segura-inventario`: control de acceso, validación de entrada, errores sin detalles
  internos y pruebas sin autorización.
- **La auditoría no se borra:** `accesos`, `eventos_offboarding` y `eventos_conector` solo se
  marcan (fechas, estados); nunca se eliminan filas.
- **Los datos que vienen del tenant se pintan con `textContent`,** nunca como HTML.
- **Cobertura mínima del 80 %** en el código nuevo (Quality Gate).
- **El análisis automático de SonarCloud permanece apagado:** el análisis lo corre GitHub
  Actions.
- **Dependencias con versión exacta y hash** (`requirements.lock`), alineadas entre servicios
  porque el CI las instala juntas.

## 7. Issues

Los pendientes técnicos viven en
[Issues de GitHub](https://github.com/EduarOC/IdentityHub/issues). Usa las plantillas
(*Reporte de bug* o *Historia de usuario*) que aparecen al pulsar «New issue».

Si encuentras una vulnerabilidad, **no abras un Issue público**: escribe directamente al
mantenedor.
