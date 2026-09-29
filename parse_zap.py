import json
import os

def parse_report(filepath, service_name):
    if not os.path.exists(filepath):
        return f"## Hallazgos de {service_name}\n\n*No se encontró el reporte o el escaneo falló.*\n\n"
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return f"## Hallazgos de {service_name}\n\n*Error al leer el reporte: {str(e)}*\n\n"
        
    alerts = data.get('site', [])
    if alerts:
        alerts = alerts[0].get('alerts', [])
    else:
        alerts = []
    
    if not alerts:
        return f"## Hallazgos de {service_name}\n\n*No se encontraron vulnerabilidades.*\n\n"
        
    output = f"## Hallazgos de {service_name}\n\n"
    
    # Sort by risk
    risk_order = {"High": 1, "Medium": 2, "Low": 3, "Informational": 4}
    alerts.sort(key=lambda x: risk_order.get(x.get('riskdesc', '').split(' ')[0], 5))
    
    for alert in alerts:
        risk = alert.get('riskdesc', 'Unknown')
        name = alert.get('name', 'Sin nombre')
        desc = alert.get('desc', '').strip()
        # Remove basic HTML
        desc = desc.replace('<p>', '').replace('</p>', '\n').replace('<strong>', '**').replace('</strong>', '**')
        
        output += f"### {name} (Severidad: {risk})\n"
        output += f"**Descripción:** {desc}\n\n"
        
        # Proposed automatic justifications based on common ZAP findings in local docker:
        justification = ""
        if "X-Content-Type-Options" in name or "Anti-clickjacking" in name or "Content Security Policy" in name:
            justification = "Se asume que estas cabeceras de seguridad deben configurarse a nivel del Auth Proxy o en el Ingress/Gateway de producción. En el entorno de desarrollo local puede justificarse su ausencia si el componente está protegido por el proxy, pero se recomienda implementarlas."
        elif "Cookie" in name or "HttpOnly" in name or "Secure" in name:
            justification = "En el entorno local sin HTTPS, el flag Secure no puede validarse adecuadamente. Se debe verificar que en producción (Render/AWS) el proxy o balanceador inserte Secure y HttpOnly."
        elif "Cross-Domain" in name or "CORS" in name:
            justification = "El servicio de inventario y el proxy pueden tener reglas CORS permisivas en desarrollo, pero deben restringirse a los dominios autorizados en producción."
        elif "Error" in name or "Information Disclosure" in name:
            justification = "Los mensajes de error detallados (modo debug) son esperables en desarrollo local, pero deben desactivarse (`FLASK_ENV=production` o similar) en entornos productivos."
        else:
            justification = "*A completar: Evaluar si requiere corrección en el código o si es un falso positivo.*"
            
        output += f"**Justificación / Acción Correctiva:**\n> {justification}\n\n"
        
    return output

def main():
    report_md = "# Reporte de Escaneo Automatizado (OWASP ZAP)\n\n"
    report_md += "**Fecha:** 28 de septiembre de 2026\n"
    report_md += "**Contexto:** Ejecución de ZAP Baseline Scan contra el entorno local Docker (Issue #28).\n\n"
    
    report_md += parse_report('report_inventory.json', 'Servicio de Inventario (puerto 5000)')
    report_md += parse_report('report_proxy.json', 'Auth Proxy (puerto 9000)')
    
    os.makedirs('08_Seguridad', exist_ok=True)
    with open('08_Seguridad/Reporte_OWASP_ZAP.md', 'w', encoding='utf-8') as f:
        f.write(report_md)
        
    print("Reporte generado en 08_Seguridad/Reporte_OWASP_ZAP.md")

if __name__ == '__main__':
    main()
