function mostrarToast(mensaje) {
    const toast = document.getElementById("toast");
    toast.textContent = mensaje;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 3200);
}

function claseRiesgo(puntaje) {
    if (puntaje >= 70) return "alto";
    if (puntaje >= 40) return "medio";
    return "bajo";
}

function colorRiesgo(clase) {
    return { alto: "#C0392B", medio: "#C68A1A", bajo: "#1E8F5F" }[clase];
}

async function cargarUsuarios() {
    const res = await fetch("/api/usuarios");
    const usuarios = await res.json();
    const tbody = document.querySelector("#tabla-usuarios tbody");
    tbody.innerHTML = "";

    usuarios.forEach(u => {
        const fila = document.createElement("tr");
        const esOffboarding = u.estado === "offboarding";
        fila.innerHTML = `
            <td>${u.nombre}</td>
            <td>${u.correo}</td>
            <td><span class="badge ${esOffboarding ? 'badge-offboarding' : 'badge-activo'}">${esOffboarding ? 'Offboarding' : 'Activo'}</span></td>
            <td>${u.accesos_activos}</td>
            <td>
                <button class="btn-offboard" data-id="${u.id}" data-nombre="${u.nombre}" ${esOffboarding ? "disabled" : ""}>
                    ${esOffboarding ? "Ya procesado" : "Iniciar offboarding"}
                </button>
            </td>
        `;
        tbody.appendChild(fila);
    });

    document.querySelectorAll(".btn-offboard:not(:disabled)").forEach(btn => {
        btn.addEventListener("click", () => ejecutarOffboarding(btn.dataset.id, btn.dataset.nombre));
    });

    document.getElementById("kpi-usuarios").textContent =
        usuarios.filter(u => u.estado === "activo").length;
}

async function ejecutarOffboarding(usuarioId, nombre) {
    if (!confirm(`¿Revocar todos los accesos de ${nombre}, incluido cualquier Shadow IT detectado?`)) return;

    const res = await fetch(`/api/usuarios/${usuarioId}/offboarding`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ responsable: "Admin (panel de prueba)" }),
    });
    const data = await res.json();

    if (data.success) {
        const lista = data.aplicativos_revocados.length > 0 ? data.aplicativos_revocados.join(", ") : "ningún acceso activo";
        mostrarToast(`✅ Offboarding de ${nombre} completado. Revocado: ${lista}`);
        cargarUsuarios();
    } else {
        mostrarToast(`⚠ ${data.error || "No se pudo completar el offboarding."}`);
    }
}

async function cargarAplicativos() {
    const res = await fetch("/api/aplicativos");
    const apps = await res.json();
    const tbody = document.querySelector("#tabla-aplicativos tbody");
    tbody.innerHTML = "";

    let costoTotal = 0;
    apps.forEach(a => {
        costoTotal += a.costo_licencia_mensual || 0;
        const fila = document.createElement("tr");
        fila.innerHTML = `
            <td>${a.nombre}</td>
            <td><span class="badge badge-${a.tipo_soporte_sso}">${a.tipo_soporte_sso}</span></td>
            <td>$${a.costo_licencia_mensual.toLocaleString()}</td>
        `;
        tbody.appendChild(fila);
    });

    document.getElementById("kpi-apps").textContent = apps.length;
    document.getElementById("kpi-costo").textContent = "$" + costoTotal.toLocaleString();
}

async function cargarShadowIT() {
    const res = await fetch("/api/aplicativos/riesgo");
    const apps = await res.json();
    const grid = document.getElementById("shadow-grid");
    grid.innerHTML = "";

    if (apps.length === 0) {
        grid.innerHTML = `<p style="color:#6B7280; font-size:13px;">No se ha importado ningún hallazgo de Shadow IT todavía.</p>`;
    }

    let altoRiesgo = 0;
    apps.forEach(a => {
        const clase = claseRiesgo(a.puntaje_riesgo);
        if (clase === "alto") altoRiesgo++;
        const ultimoUso = a.fecha_ultimo_uso
            ? new Date(a.fecha_ultimo_uso).toLocaleDateString("es-CO", { year: "numeric", month: "short", day: "numeric" })
            : "Sin registro (token huérfano)";

        const card = document.createElement("div");
        card.className = "shadow-card";
        card.innerHTML = `
            <div class="risk-badge risk-${clase}">${Math.round(a.puntaje_riesgo)}</div>
            <div class="shadow-card-name">${a.nombre}</div>
            <div class="shadow-card-meta">
                ${a.alcance_oauth || "Alcance no especificado"}<br>
                Último uso: ${ultimoUso}
            </div>
            <div class="risk-bar-track">
                <div class="risk-bar-fill" style="width:${a.puntaje_riesgo}%; background:${colorRiesgo(clase)};"></div>
            </div>
        `;
        grid.appendChild(card);
    });

    document.getElementById("kpi-riesgo").textContent = altoRiesgo;
}

async function cargarTodo() {
    await Promise.all([cargarUsuarios(), cargarAplicativos(), cargarShadowIT()]);
}

document.addEventListener("DOMContentLoaded", cargarTodo);
