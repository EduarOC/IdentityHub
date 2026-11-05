function mostrarToast(mensaje) {
    const toast = document.getElementById("toast");
    toast.textContent = mensaje;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 3800);
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
        grid.innerHTML = `
            <div class="empty-state">
                <p>No hay aplicativos descubiertos por OAuth registrados aún.</p>
                <small>Usa el botón <strong>"Sincronizar desde Entra ID"</strong> para importar las aplicaciones autorizadas en tu organización.</small>
            </div>
        `;
        document.getElementById("kpi-riesgo").textContent = 0;
        return;
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

// -------------------------------------------------------------
// Funcionalidades de Configuración y Sincronización con Entra ID
// -------------------------------------------------------------

async function abrirModalTenant() {
    const modal = document.getElementById("modal-tenant");
    const statusBox = document.getElementById("status-box");
    statusBox.style.display = "none";
    statusBox.className = "status-box";

    try {
        const res = await fetch("/api/conector/entra-id");
        if (res.ok) {
            const data = await res.json();
            document.getElementById("cfg-tenant-id").value = data.tenant_id || "";
            document.getElementById("cfg-client-id").value = data.client_id || "";
            if (data.tiene_secreto) {
                document.getElementById("cfg-client-secret").value = "••••••••••••••••";
                document.getElementById("hint-secret").innerHTML =
                    "✅ Secreto configurado previamente. Déjalo así para conservarlo o escribe uno nuevo para actualizarlo.";
            } else {
                document.getElementById("cfg-client-secret").value = "";
                document.getElementById("hint-secret").innerHTML =
                    "Requiere permiso de aplicación <code>Directory.Read.All</code> con consentimiento de administrador.";
            }
        }
    } catch (e) {
        console.error("Error al cargar configuración de tenant", e);
    }

    modal.style.display = "flex";
}

function cerrarModalTenant() {
    document.getElementById("modal-tenant").style.display = "none";
}

async function probarConexionTenant() {
    const tenantId = document.getElementById("cfg-tenant-id").value.trim();
    const clientId = document.getElementById("cfg-client-id").value.trim();
    const secret = document.getElementById("cfg-client-secret").value.trim();
    const statusBox = document.getElementById("status-box");
    const spinner = document.getElementById("test-spinner");
    const btn = document.getElementById("btn-probar-conexion");

    statusBox.style.display = "block";
    statusBox.className = "status-box info";
    statusBox.textContent = "Conectando con login.microsoftonline.com...";
    btn.disabled = true;
    spinner.textContent = "⏳";

    try {
        const res = await fetch("/api/conector/entra-id/probar", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                tenant_id: tenantId,
                client_id: clientId,
                client_secret: secret
            })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            statusBox.className = "status-box success";
            statusBox.innerHTML = `<strong>Éxito:</strong> ${data.mensaje}`;
        } else {
            statusBox.className = "status-box error";
            statusBox.innerHTML = `<strong>Error de conexión:</strong> ${data.error || "No se pudo validar el tenant."}`;
        }
    } catch (e) {
        statusBox.className = "status-box error";
        statusBox.innerHTML = `<strong>Error:</strong> No hubo respuesta del servidor (${e.message})`;
    } finally {
        btn.disabled = false;
        spinner.textContent = "🔍";
    }
}

async function guardarConfigTenant() {
    const tenantId = document.getElementById("cfg-tenant-id").value.trim();
    const clientId = document.getElementById("cfg-client-id").value.trim();
    const secret = document.getElementById("cfg-client-secret").value.trim();
    const btn = document.getElementById("btn-guardar-tenant");

    if (!tenantId || !clientId) {
        alert("Por favor ingresa el Tenant ID y el Client ID.");
        return;
    }

    btn.disabled = true;
    try {
        const res = await fetch("/api/conector/entra-id", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                tenant_id: tenantId,
                client_id: clientId,
                client_secret: secret
            })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            mostrarToast("✅ Configuración de Microsoft Entra ID guardada.");
            cerrarModalTenant();
        } else {
            alert(`Error al guardar: ${data.error || "Intente nuevamente"}`);
        }
    } catch (e) {
        alert(`Error al guardar configuración: ${e.message}`);
    } finally {
        btn.disabled = false;
    }
}

async function sincronizarEntraID() {
    const btn = document.getElementById("btn-sincronizar-entra");
    const spinner = document.getElementById("sync-spinner");

    btn.disabled = true;
    spinner.textContent = "⏳";
    mostrarToast("🔄 Conectando a Microsoft Graph API y analizando permisos OAuth...");

    try {
        const res = await fetch("/api/conector/entra-id/sincronizar", {
            method: "POST"
        });
        const data = await res.json();

        if (res.ok && data.success) {
            mostrarToast(`✅ ${data.mensaje}`);
            await cargarShadowIT();
            await cargarAplicativos();
        } else {
            if (res.status === 400 && data.error && data.error.includes("no está configurado")) {
                abrirModalTenant();
                mostrarToast("⚠️ Por favor configura el Tenant ID y credenciales primero.");
            } else {
                mostrarToast(`❌ ${data.error || "Fallo en la sincronización con Microsoft Graph."}`);
            }
        }
    } catch (e) {
        mostrarToast(`❌ Error al sincronizar: ${e.message}`);
    } finally {
        btn.disabled = false;
        spinner.textContent = "🔄";
    }
}

async function cargarTodo() {
    await Promise.all([cargarUsuarios(), cargarAplicativos(), cargarShadowIT()]);
}

document.addEventListener("DOMContentLoaded", () => {
    cargarTodo();

    // Eventos del conector Microsoft Entra ID
    document.getElementById("btn-abrir-modal-tenant")?.addEventListener("click", abrirModalTenant);
    document.getElementById("btn-cerrar-modal")?.addEventListener("click", cerrarModalTenant);
    document.getElementById("btn-probar-conexion")?.addEventListener("click", probarConexionTenant);
    document.getElementById("btn-guardar-tenant")?.addEventListener("click", guardarConfigTenant);
    document.getElementById("btn-sincronizar-entra")?.addEventListener("click", sincronizarEntraID);

    // Cerrar modal al hacer clic en el backdrop
    document.getElementById("modal-tenant")?.addEventListener("click", (e) => {
        if (e.target.id === "modal-tenant") cerrarModalTenant();
    });
});
