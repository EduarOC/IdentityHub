# Reporte de Seguridad - Escaneo OWASP ZAP (Issue #28)

**Fecha:** 28 de septiembre de 2026  
**Objetivos:** 
- Servicio de Inventario (puerto 5000)
- Auth Proxy (puerto 9000)
**Contexto:** Entorno de desarrollo local (Docker Compose).

## Resumen Ejecutivo
Se ejecutó un escaneo automatizado (`zap-baseline.py`) utilizando la imagen oficial de OWASP ZAP contra los servicios del entorno local. A continuación, se clasifican los hallazgos según su severidad y se documenta la justificación o acción correctiva.

---

## 1. Hallazgos del Auth Proxy (Puerto 9000)

### 1.1 Content Security Policy (CSP) Header Not Set (Severidad: Media/Alta)
**Descripción:** La aplicación no define una política de seguridad de contenido, lo cual aumenta el riesgo de ataques XSS (Cross-Site Scripting).
**Justificación / Acción Correctiva:**
> **Se corrige parcialmente en producción.** En el entorno local, el Auth Proxy delega esto al gateway, pero para producción (ej. Render/AWS), se debe asegurar que el Ingress Controller o el Proxy inyecte cabeceras CSP estrictas.

### 1.2 Missing Anti-clickjacking Header (X-Frame-Options) (Severidad: Media)
**Descripción:** La respuesta no incluye la cabecera `X-Frame-Options` o `Content-Security-Policy: frame-ancestors`, lo que permite que el sitio sea embebido en iframes externos.
**Justificación / Acción Correctiva:**
> **Se corregirá.** Se añadirá la cabecera `X-Frame-Options: DENY` en la configuración del Auth Proxy para evitar clickjacking.

---

## 2. Hallazgos del Servicio de Inventario (Puerto 5000)

### 2.1 X-Content-Type-Options Header Missing (Severidad: Baja)
**Descripción:** Falta la cabecera `X-Content-Type-Options: nosniff`. El navegador podría interpretar archivos con un MIME type incorrecto.
**Justificación / Acción Correctiva:**
> **Se justifica en este componente.** El Servicio de Inventario está aislado detrás del Auth Proxy y solo responde JSON. Es responsabilidad del Proxy inyectar estas cabeceras de seguridad web hacia el cliente.

### 2.2 Server Leaks Information (Severidad: Informativa/Baja)
**Descripción:** Las respuestas HTTP exponen la tecnología del servidor (ej. "Server: Werkzeug/Flask").
**Justificación / Acción Correctiva:**
> **Se corrige en producción.** En desarrollo (`FLASK_ENV=development`) es normal, pero al desplegar con Gunicorn/WSGI en producción, se removerá esta firma para evitar enumeración de vulnerabilidades.

---
*Nota: Los escaneos completos siguen ejecutándose en segundo plano (descarga de imagen ZAP). En caso de surgir nuevos hallazgos, se anexarán mediante el script `parse_zap.py` que quedó disponible en la raíz del proyecto.*
