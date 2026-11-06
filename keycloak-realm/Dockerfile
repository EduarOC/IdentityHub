# Imagen de Keycloak para Render (modo producción).
# Etapa 1: "kc.sh build" precompila Keycloak para PostgreSQL. Así el arranque en Render
# usa "--optimized" y no recompila al iniciar, lo que ahorra tiempo y memoria (512 MB).
FROM quay.io/keycloak/keycloak:25.0 AS builder
ENV KC_DB=postgres
ENV KC_HEALTH_ENABLED=true
# Un solo servidor: caché local en vez de clúster (JGroups/Infinispan distribuido), que en
# Render buscaba otros nodos por la red y consumía memoria y hilos sin necesidad.
ENV KC_CACHE=local
RUN /opt/keycloak/bin/kc.sh build

# Etapa 2: imagen final con el realm de IdentityHub, que se importa al arrancar.
FROM quay.io/keycloak/keycloak:25.0
COPY --from=builder /opt/keycloak/ /opt/keycloak/
COPY identityhub-realm.json /opt/keycloak/data/import/identityhub-realm.json
USER 1000
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
CMD ["start", "--optimized", "--import-realm"]
