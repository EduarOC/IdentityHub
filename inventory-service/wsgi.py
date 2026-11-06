"""Punto de entrada de Gunicorn para el inventario: prepara la base (tablas, columnas nuevas y
limpieza de datos de ejemplo) antes de atender peticiones, como hacía app.py al correr directo."""
from app import app, preparar_base

preparar_base()

__all__ = ["app"]
