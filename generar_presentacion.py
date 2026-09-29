import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

prs = Presentation()

# Colores de la paleta basada en el PDF original
DARK_BLUE = RGBColor(36, 46, 94)
ORANGE = RGBColor(230, 108, 23)
WHITE = RGBColor(255, 255, 255)
DARK_GRAY = RGBColor(60, 60, 60)
LIGHT_GRAY = RGBColor(245, 245, 245)

def apply_text_style(text_frame, color, font_size, bold=False, font_name='Arial'):
    for paragraph in text_frame.paragraphs:
        for run in paragraph.runs:
            run.font.color.rgb = color
            run.font.size = font_size
            run.font.bold = bold
            run.font.name = font_name

def add_slide(prs, title, content_lines):
    slide_layout = prs.slide_layouts[1] # 1 is Title and Content
    slide = prs.slides.add_slide(slide_layout)
    
    # Fondo claro
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = LIGHT_GRAY

    title_shape = slide.shapes.title
    body_shape = slide.placeholders[1]
    
    # Estilo del Título
    title_shape.text = title
    title_shape.text_frame.paragraphs[0].font.color.rgb = DARK_BLUE
    title_shape.text_frame.paragraphs[0].font.bold = True
    title_shape.text_frame.paragraphs[0].font.name = 'Arial'
    
    # Línea decorativa naranja debajo del título
    left = Inches(0.5)
    top = Inches(1.2)
    width = Inches(8)
    height = Inches(0.05)
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    line.fill.solid()
    line.fill.fore_color.rgb = ORANGE
    line.line.color.rgb = ORANGE

    # Contenido
    tf = body_shape.text_frame
    tf.clear()
    
    for i, line_text in enumerate(content_lines):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        
        # Manejo de viñetas
        if line_text.startswith("    "):
            p.level = 1
            p.text = line_text.strip()
            p.font.size = Pt(18)
        elif line_text.startswith("        "):
            p.level = 2
            p.text = line_text.strip()
            p.font.size = Pt(16)
        else:
            p.level = 0
            p.text = line_text.strip()
            p.font.size = Pt(22)
            p.font.bold = True
            
        p.font.color.rgb = DARK_GRAY
        p.font.name = 'Arial'

# Slide: Portada
title_slide_layout = prs.slide_layouts[0]
slide = prs.slides.add_slide(title_slide_layout)

# Fondo oscuro para la portada
background = slide.background
fill = background.fill
fill.solid()
fill.fore_color.rgb = DARK_BLUE

title = slide.shapes.title
subtitle = slide.placeholders[1]

title.text = "IdentityHub"
subtitle.text = "Gestión Centralizada de Identidad e Inventario de Aplicativos\n\nDavid Yused Pulido Pardo, Eduar de Jesús Ortiz Causil, Jhoan Steven Soto Daza\nProyecto de Grado — Ingeniería de Sistemas"

# Estilizar título de portada
title.text_frame.paragraphs[0].font.color.rgb = WHITE
title.text_frame.paragraphs[0].font.bold = True
title.text_frame.paragraphs[0].font.size = Pt(54)
title.text_frame.paragraphs[0].font.name = 'Arial'

# Estilizar subtítulo de portada
for p in subtitle.text_frame.paragraphs:
    p.font.color.rgb = ORANGE
    p.font.size = Pt(20)
    p.font.name = 'Arial'


# SECCIÓN 1: INVESTIGACIÓN

add_slide(prs, "Investigación: Introducción", [
    "Proyecto: IdentityHub",
    "    Plataforma de gestión centralizada de identidad y descubrimiento de Shadow IT.",
    "Público Dirigido:",
    "    Pequeñas y medianas empresas (PYMES).",
    "Propósito:",
    "    Ofrecer control administrativo y reducción de riesgos sin los altos costos de soluciones Enterprise.",
    "Fundamento:",
    "    No reinventar protocolos de seguridad; construir sobre Keycloak (Identity Provider Open Source)."
])

add_slide(prs, "Investigación: El Problema", [
    "Identidad fragmentada en las PYMES:",
    "    La mayoría de aplicativos empresariales no soportan Single Sign-On (SSO) nativo.",
    "    Cobros adicionales (\"SSO tax\") por habilitar SAML/OIDC en planes básicos.",
    "Costos inasumibles:",
    "    Soluciones como Okta cobran desde $6 USD por usuario/mes.",
    "Riesgos de Seguridad Críticos:",
    "    Cuentas de exempleados sin revocar a tiempo debido a la descentralización.",
    "    Shadow IT (aplicaciones no autorizadas) sin visibilidad ni control."
])

add_slide(prs, "Investigación: Justificación", [
    "Existe un vacío real entre lo caro y lo inexistente en el mercado.",
    "Oferta actual desalineada:",
    "    Okta, Azure AD, Zylo y BetterCloud están dirigidas y valoradas para grandes empresas.",
    "Necesidad de las PYMES:",
    "    Enfrentan los mismos riesgos de seguridad, pero sin el presupuesto para costear estas plataformas.",
    "La Solución:",
    "    Ofrecer una capa de gestión accesible sobre código abierto (Keycloak), para el segmento desatendido."
])

add_slide(prs, "Investigación: Estado del Arte", [
    "Lo que ya existe en el mercado:",
    "    Okta / Entra ID: SSO comercial estándar (Costoso, asume soporte nativo OIDC/SAML).",
    "    Entra ID Governance: Offboarding automatizado (Premium add-on).",
    "    Zluri: SaaS management y gobierno (Cerrado y de pago).",
    "    SpendHound: Visibilidad de gasto (No hace identidad ni offboarding).",
    "Conclusión:",
    "    Ninguna solución actual, accesible para PYMES y de código abierto, unifica SSO para apps legacy, inventario, offboarding y descubrimiento de Shadow IT."
])

add_slide(prs, "Fuentes, Encuestas y Análisis", [
    "Fuentes y Diagnóstico Directo:",
    "    Investigación basada en necesidades reales de empresas medianas con decenas de aplicativos.",
    "Encuestas e Investigación Primaria (En curso):",
    "    Evaluación de necesidades y vulnerabilidades en PYMES mediante diagnóstico directo.",
    "Análisis y Conclusiones Parciales:",
    "    El proceso manual y fragmentado de gestión de accesos genera vulnerabilidades comprobables.",
    "    Proyección global de SSO a 2.2 billones de dólares para 2027.",
    "    El Auth Reverse Proxy resuelve el SSO en apps Legacy sin cambiar su código."
])


# SECCIÓN 2: OBJETIVOS Y ALCANCE

add_slide(prs, "Objetivos y Alcance: Objetivo General", [
    "Objetivo General:",
    "    Desarrollar una plataforma integral de gestión centralizada de identidades y accesos (IdentityHub) que ofrezca a las PYMES un control administrativo optimizado y una reducción de los riesgos de seguridad derivados de credenciales descentralizadas, previniendo el uso de aplicaciones no autorizadas (Shadow IT) mediante la integración de un proveedor de identidad de código abierto (Keycloak), un proxy de autenticación y un servicio de inventario automatizado."
])

add_slide(prs, "Objetivos Corregidos", [
    "    1. Centralizar la administración de identidades y el inicio de sesión único (SSO) en aplicaciones corporativas, proporcionando a las empresas un control administrativo y optimizado sobre sus recursos tecnológicos.",
    "    2. Asegurar la reducción de riesgos de seguridad eliminando las vulnerabilidades de cuentas huérfanas y aplicaciones no autorizadas (Shadow IT), a través de la automatización del proceso de altas y bajas de usuarios en tiempo real.",
    "    3. Ejecutar el ciclo de desarrollo del sistema a través de cuatro fases clave: evaluar y diseñar la arquitectura basada en las necesidades actuales; implementar el núcleo de identidad con Keycloak; automatizar la gestión de accesos; y validar y cerrar el proyecto asegurando la calidad del código, las pruebas y la documentación técnica."
])

add_slide(prs, "Alcance y Restricciones", [
    "Alcance (Incluye):",
    "    Broker de identidad sobre Keycloak.",
    "    Auth Reverse Proxy para aplicaciones legacy.",
    "    Inventario de aplicativos y offboarding centralizado con auditoría.",
    "    Descubrimiento de Shadow IT vía OAuth con puntaje de riesgo.",
    "Restricciones (No incluye por ahora):",
    "    Aprovisionamiento automático de cuentas nuevas (onboarding completo).",
    "    Integración directa con sistemas de nómina / RRHH.",
    "    Soporte multi-tenant para múltiples organizaciones simultáneas.",
    "    Panel de analítica de licencias predictivo."
])


# SECCIÓN 3: METODOLOGÍA

add_slide(prs, "Metodología: Investigación y Desarrollo", [
    "Metodología de Investigación (Aplicada y Diagnóstica):",
    "    Enfoque en resolver un problema práctico de seguridad y gestión en TI.",
    "    Evaluación de mercado (Estado del Arte) y levantamiento de requerimientos vía encuestas en PYMES reales.",
    "Metodología de Desarrollo Seleccionada:",
    "    Marco de Trabajo Ágil: Scrum.",
    "Justificación del Desarrollo:",
    "    Permite iteración rápida y entregas modulares (Keycloak -> Proxy -> Inventario -> Shadow IT).",
    "    Sprints de 1 a 2 semanas con reuniones de Planning, Review y Retrospective."
])

add_slide(prs, "Herramientas y Trazabilidad", [
    "Trazabilidad y Control de Versiones (GitHub Flow):",
    "    Desarrollo estructurado mediante ramas por funcionalidad.",
    "    Integración mediante Pull Requests (PR) y revisión por pares.",
    "    Plantillas de Issues pre-configuradas para asegurar la calidad.",
    "Roles Scrum:",
    "    Scrum Master: Jhoan Steven Soto Daza.",
    "    Product Owner / Developers: Los tres integrantes del equipo.",
    "    Commits individuales para garantizar la trazabilidad real de cada participante."
])

# Slide de Cierre
slide = prs.slides.add_slide(title_slide_layout)
background = slide.background
fill = background.fill
fill.solid()
fill.fore_color.rgb = DARK_BLUE

title = slide.shapes.title
subtitle = slide.placeholders[1]
title.text = "¡Gracias!"
subtitle.text = "¿Preguntas?"
title.text_frame.paragraphs[0].font.color.rgb = WHITE
title.text_frame.paragraphs[0].font.bold = True
subtitle.text_frame.paragraphs[0].font.color.rgb = ORANGE

prs.save("Presentacion_Proyecto.pptx")
print("Presentación creada exitosamente en Presentacion_Proyecto.pptx")
