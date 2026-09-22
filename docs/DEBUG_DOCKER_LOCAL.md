# Registro de Problemas y Soluciones - Despliegue Local (Docker)

Durante la validación del flujo de "Login completo en Docker real", se encontraron y solucionaron los siguientes impedimentos técnicos en el entorno local de Windows:

## 1. Keycloak: `OutOfMemoryError: Metaspace`
* **Síntoma:** El contenedor de `auth-proxy` devolvía un error de DNS `Name or service not known` al intentar localizar a `keycloak`.
* **Causa raíz:** El contenedor de Keycloak colapsaba (exit code 1) durante el `--import-realm`. Los logs indicaban `Terminating due to java.lang.OutOfMemoryError: Metaspace`. El parámetro de la JVM `-XX:MaxMetaspaceSize=100m` definido en el `docker-compose.yml` era muy agresivo para el footprint de Keycloak 25.
* **Solución:** Se editó el `docker-compose.yml` modificando `JAVA_OPTS_APPEND`. Se incrementó el Metaspace a `150m` y se redujo el Heap (`-Xmx`) a `250m` para mantener el límite global de RAM sin romper la barrera de los 512MB (simulación de Render).

## 2. Auth-Proxy: Error de DNS en el navegador (ERR_CONNECTION_REFUSED)
* **Síntoma:** Al entrar a `localhost:9000/login`, el proxy redirigía el navegador del usuario hacia `http://keycloak:8080/...`. Como "keycloak" es un hostname interno de la red de Docker, el navegador en Windows no podía resolverlo.
* **Causa raíz:** `authlib` consumía el `.well-known/openid-configuration` a través de la red interna de Docker, por lo que Keycloak devolvía todos sus endpoints configurados bajo el dominio `keycloak:8080`.
* **Solución:** Se intervino `app.py`. Se modificó la lectura de la metadata para que, de forma dinámica, reemplace el host interno (`keycloak`) por el host externo (`localhost`) en las URIs expuestas al cliente (`authorization_endpoint` e `issuer`).

## 3. Authlib: Falla en la validación del Issuer (`invalid_claim: iss`)
* **Síntoma:** Tras iniciar sesión exitosamente en Keycloak, al ser redirigido de vuelta al proxy (`/auth/callback`), ocurría un HTTP 500. Los logs indicaban `Invalid claim "iss"`.
* **Causa raíz:** Al autorizar, Keycloak firmaba el token declarando que el emisor era `localhost:8080` (ya que fue accedido así por el cliente). Sin embargo, el proxy internamente esperaba que el emisor fuera `keycloak:8080` (su endpoint de descubrimiento).
* **Solución:** En `app.py`, se removió la dependencia del `server_metadata_url` automático en la función `oauth.register` y se inyectó la metadata manualmente tras pre-procesarla, forzando a la librería a validar el *issuer* externo en lugar del interno.
