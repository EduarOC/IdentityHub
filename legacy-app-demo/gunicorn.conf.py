"""Configuración de Gunicorn, el servidor WSGI de producción (reemplaza al servidor de desarrollo
de Flask, que no está hecho para tráfico real). Gunicorn la lee sola al arrancar en esta carpeta."""
import os

# Render asigna el puerto en la variable PORT.
bind = f"0.0.0.0:{os.environ.get('PORT', '6000')}"

# Un solo proceso con varios hilos: cabe en los 512 MB del plan gratuito de Render y, en el
# inventario, mantiene en un mismo proceso el bloqueo y el hilo de la sincronización de conectores.
workers = 1
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "4"))

# Las llamadas a Microsoft Graph o a Keycloak pueden tardar; Render corta a los 100 s.
timeout = 90
graceful_timeout = 20

# Registros a la salida estándar, que Render muestra en Logs.
accesslog = "-"
errorlog = "-"
