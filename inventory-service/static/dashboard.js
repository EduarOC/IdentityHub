// Panel del inventario de IdentityHub.
// Los datos vienen de la API y pueden venir de Microsoft Entra ID (nombres de usuarios y de
// aplicaciones), así que nunca se insertan como HTML: todo se arma con nodos y textContent.

const formatoMoneda = new Intl.NumberFormat("es-CO", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const formatoFecha = { year: "numeric", month: "short", day: "numeric" };
const NIVEL_RIESGO = { alto: "Riesgo alto", medio: "Riesgo medio", bajo: "Riesgo bajo" };

function el(etiqueta, opciones = {}, hijos = []) {
    const nodo = document.createElement(etiqueta);
    if (opciones.clase) nodo.className = opciones.clase;
    if (opciones.texto !== undefined) nodo.textContent = opciones.texto;
    if (opciones.atributos) {
        Object.entries(opciones.atributos).forEach(([k, v]) => nodo.setAttribute(k, v));
    }
    hijos.forEach(h => nodo.appendChild(h));
    return nodo;
}

function celda(texto, clase) {
    return el("td", { texto, clase });
}

let temporizadorToast;
function mostrarToast(mensaje, tipo = "ok") {
    const toast = document.getElementById("toast");
    toast.textContent = mensaje;
    toast.dataset.tipo = tipo;
    toast.classList.add("show");
    clearTimeout(temporizadorToast);
    temporizadorToast = setTimeout(() => toast.classList.remove("show"), 4200);
}

function claseRiesgo(puntaje) {
    if (puntaje >= 70) return "alto";
    if (puntaje >= 40) return "medio";
    return "bajo";
}

async function pedirJSON(url, opciones) {
    const res = await fetch(url, opciones);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

function filaMensaje(tbody, columnas, mensaje, clase = "estado-vacio") {
    tbody.replaceChildren(el("tr", {}, [el("td", { texto: mensaje, clase, atributos: { colspan: String(columnas) } })]));
}

// ------------------------------------------------------------------ usuarios
async function cargarUsuarios() {
    const tbody = document.querySelector("#tabla-usuarios tbody");
    let usuarios;
    try {
        usuarios = await pedirJSON("/api/usuarios");
    } catch {
        filaMensaje(tbody, 5, "No se pudieron cargar los usuarios. Recarga la página en unos segundos.", "estado-error");
        document.getElementById("kpi-usuarios").textContent = "—";
        return;
    }

    if (usuarios.length === 0) {
        filaMensaje(tbody, 5, "Todavía no hay usuarios registrados.");
    } else {
        tbody.replaceChildren(...usuarios.map(filaUsuario));
    }
    document.getElementById("kpi-usuarios").textContent =
        usuarios.filter(u => u.estado === "activo").length;
}

function filaUsuario(u) {
    const retirado = u.estado === "offboarding";
    const boton = el("button", {
        clase: "btn-offboard",
        texto: retirado ? "Ya procesado" : "Iniciar offboarding",
        atributos: { type: "button", "aria-label": retirado ? `${u.nombre}: offboarding ya procesado` : `Iniciar offboarding de ${u.nombre}` },
    });
    if (retirado) boton.disabled = true;
    else boton.addEventListener("click", () => ejecutarOffboarding(u.id, u.nombre, boton));

    return el("tr", {}, [
        celda(u.nombre, "col-nombre"),
        celda(u.correo, "col-correo"),
        el("td", { clase: "col-estado" }, [el("span", { clase: `badge ${retirado ? "badge-offboarding" : "badge-activo"}`, texto: retirado ? "Offboarding" : "Activo" })]),
        el("td", { clase: "num col-accesos", texto: String(u.accesos_activos), atributos: { "data-etiqueta": "Accesos activos" } }),
        el("td", { clase: "col-accion" }, [boton]),
    ]);
}

async function ejecutarOffboarding(usuarioId, nombre, boton) {
    if (!confirm(`¿Revocar todos los accesos de ${nombre}, incluido cualquier Shadow IT detectado?\n\nEsta acción no se puede deshacer desde el panel.`)) return;

    boton.disabled = true;
    boton.textContent = "Procesando…";
    try {
        const data = await pedirJSON(`/api/usuarios/${encodeURIComponent(usuarioId)}/offboarding`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ responsable: "Admin (panel de prueba)" }),
        });
        if (!data.success) throw new Error(data.error || "respuesta sin éxito");
        const lista = data.aplicativos_revocados.length > 0 ? data.aplicativos_revocados.join(", ") : "ningún acceso activo";
        mostrarToast(`Offboarding de ${nombre} completado. Revocado: ${lista}`);
        await cargarUsuarios();
    } catch (error) {
        console.error("Offboarding fallido:", error);
        boton.disabled = false;
        boton.textContent = "Iniciar offboarding";
        mostrarToast(`No se pudo completar el offboarding de ${nombre}. Intenta de nuevo.`, "error");
    }
}

// ------------------------------------------------------------------ catálogo
async function cargarAplicativos() {
    const tbody = document.querySelector("#tabla-aplicativos tbody");
    let apps;
    try {
        apps = await pedirJSON("/api/aplicativos");
    } catch {
        filaMensaje(tbody, 3, "No se pudo cargar el catálogo.", "estado-error");
        return;
    }

    if (apps.length === 0) {
        filaMensaje(tbody, 3, "Todavía no hay aplicativos en el catálogo.");
    } else {
        tbody.replaceChildren(...apps.map(a => el("tr", {}, [
            celda(a.nombre),
            el("td", {}, [el("span", { clase: `badge badge-${a.tipo_soporte_sso}`, texto: a.tipo_soporte_sso })]),
            celda(formatoMoneda.format(a.costo_licencia_mensual || 0), "num"),
        ])));
    }

    const costoTotal = apps.reduce((suma, a) => suma + (a.costo_licencia_mensual || 0), 0);
    document.getElementById("kpi-apps").textContent = apps.length;
    document.getElementById("kpi-costo").textContent = formatoMoneda.format(costoTotal);
}

// ------------------------------------------------------------------ Shadow IT
async function cargarShadowIT() {
    const grid = document.getElementById("shadow-grid");
    let apps;
    try {
        apps = await pedirJSON("/api/aplicativos/riesgo");
    } catch {
        grid.replaceChildren(el("p", { clase: "estado-error", texto: "No se pudieron cargar los hallazgos de Shadow IT." }));
        return;
    }

    if (apps.length === 0) {
        grid.replaceChildren(el("p", { clase: "estado-vacio", texto: "No se ha importado ningún hallazgo de Shadow IT todavía." }));
    } else {
        grid.replaceChildren(...apps.map(tarjetaShadowIT));
    }
    document.getElementById("kpi-riesgo").textContent =
        apps.filter(a => claseRiesgo(a.puntaje_riesgo) === "alto").length;
}

function tarjetaShadowIT(a) {
    const clase = claseRiesgo(a.puntaje_riesgo);
    const puntaje = Math.round(a.puntaje_riesgo);
    const ultimoUso = a.fecha_ultimo_uso
        ? new Date(a.fecha_ultimo_uso).toLocaleDateString("es-CO", formatoFecha)
        : "Sin registro (token huérfano)";

    const barra = el("div", { clase: "risk-bar-fill" });
    barra.style.width = `${Math.min(100, Math.max(0, a.puntaje_riesgo))}%`;

    return el("article", { clase: `shadow-card risk-card-${clase}` }, [
        el("div", { clase: `risk-badge risk-${clase}`, texto: String(puntaje), atributos: { "aria-label": `${NIVEL_RIESGO[clase]}: ${puntaje} de 100` } }),
        el("h3", { clase: "shadow-card-name", texto: a.nombre }),
        el("p", { clase: `risk-level risk-text-${clase}`, texto: NIVEL_RIESGO[clase] }),
        el("p", { clase: "shadow-card-meta", texto: a.alcance_oauth || "Alcance no especificado" }),
        el("p", { clase: "shadow-card-meta", texto: `Último uso: ${ultimoUso}` }),
        el("div", { clase: "risk-bar-track", atributos: { "aria-hidden": "true" } }, [barra]),
    ]);
}

async function cargarTodo() {
    await Promise.all([cargarUsuarios(), cargarAplicativos(), cargarShadowIT()]);
}

document.addEventListener("DOMContentLoaded", () => {
    cargarTodo().catch(() => mostrarToast("No se pudo cargar el panel. Recarga la página.", "error"));
});
