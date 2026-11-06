---
name: verificar-antes-del-pr
description: Verifica un cambio de IdentityHub antes de subirlo y abre la solicitud de cambios (PR) siguiendo GitHub Flow. Comprueba que no se esté trabajando sobre main, corre las pruebas con cobertura contra la meta del 80 %, busca secretos y patrones peligrosos en el diff, sube la rama, abre el PR con la plantilla del repositorio y revisa el resultado de CI y del Quality Gate de SonarCloud. Úsala siempre que se vaya a hacer commit, push, «subir los cambios», «abrir el PR» o «mandar a main» en este repositorio, aunque el pedido no mencione pruebas ni SonarCloud.
---

# Verificar antes del PR

`main` es lo que se despliega en Render y lo que ven el jurado y los auditores. Tres veces llegaron cambios directo a `main` sin PR y SonarCloud quedó en rojo (27/10, 05/11, 06/11). Esta skill hace que cada cambio pase por la misma revisión.

## Flujo

1. **Rama, nunca `main`.** Si estás en `main`, crea una rama con el prefijo del tipo de cambio (`feat/`, `fix/`, `docs/`, `test/`, `ci/`, `chore/`) y un nombre corto en español.

2. **Corre la verificación local:**
   ```bash
   bash .claude/skills/verificar-antes-del-pr/scripts/verificar.sh
   ```
   El script:
   - se niega a continuar si la rama actual es `main`;
   - corre `pytest` con la configuración de cobertura del repositorio y falla si la cobertura total baja de 80 %;
   - revisa el diff contra `origin/main` en busca de contraseñas o tokens escritos, llaves privadas, `verify=False`, `debug=True`, `innerHTML` nuevo y rutas nuevas (`@app.route`). No bloquea por las rutas, pero te las lista para pasarlas por la skill `ruta-segura-inventario`.

   Si algo falla, corrígelo antes de seguir; no lo silencies.

3. **Commit.** Sigue la sección 4 de CONTRIBUTING.md: `tipo(alcance opcional): descripción corta en presente`, con tipo `feat`, `fix`, `docs`, `refactor`, `test`, `chore` o `ci`, y un cuerpo que explique qué cambia y por qué. Commits pequeños y frecuentes, con el correo de tu cuenta de GitHub para que queden a tu nombre.

4. **Sube la rama y abre el PR** con la plantilla `.github/PULL_REQUEST_TEMPLATE.md`. Llena «Qué cambia», «Por qué», «Cómo se probó» (con el resultado real de las pruebas y la cobertura) y el checklist. Si toca seguridad, cita el control WSTG o ASVS.

5. **Espera CI y SonarCloud.** El check «Pruebas + SonarCloud» falla si el Quality Gate no se aprueba (`sonar.qualitygate.wait=true`). Para ver el estado del PR:
   ```bash
   bash .claude/skills/verificar-antes-del-pr/scripts/estado_pr.sh <número-del-PR>
   ```
   Si SonarCloud reporta hallazgos, corrígelos en la misma rama.

6. **Fusionar** es una decisión del equipo: pide la aprobación de un compañero o la confirmación explícita del usuario. No fusiones con CI en rojo.

## Datos útiles

- Proyecto de SonarCloud: `EduarOC_proyecto-de-grado`, organización `identityhub`. El análisis automático de SonarCloud debe seguir **apagado**: choca con el de GitHub Actions.
- Las dependencias se instalan con `--require-hashes --only-binary :all:` desde los `requirements.lock`. Si agregas una dependencia, fíjala con versión y hash en el `.lock` correspondiente; un `>=` en `requirements.txt` no basta.
