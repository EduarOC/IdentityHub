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

    if (!usuarios || usuarios.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="table-empty-msg">
                    No hay usuarios registrados en el sistema.<br>
                    <small>Configura un tenant en <strong>"Configurar Tenant Microsoft"</strong> y sincroniza desde Entra ID.</small>
                </td>
            </tr>
        `;
        document.getElementById("kpi-usuarios").textContent = 0;
        return;
    }

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

    if (!apps || apps.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="3" class="table-empty-msg">
                    No hay aplicativos en el catálogo de TI.<br>
                    <small>Conecta tu tenant de Entra ID para sincronizar las aplicaciones gestionadas.</small>
                </td>
            </tr>
        `;
        document.getElementById("kpi-apps").textContent = 0;
        document.getElementById("kpi-costo").textContent = "$0";
        return;
    }

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

function toggleModoAuth(modo) {
    const groupCert = document.getElementById("field-group-cert");
    const groupSecret = document.getElementById("field-group-secret");
    if (modo === "certificate") {
        groupCert.style.display = "flex";
        groupSecret.style.display = "none";
    } else {
        groupCert.style.display = "none";
        groupSecret.style.display = "flex";
    }
}

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

            const modo = data.tipo_auth || (data.tiene_certificado ? "certificate" : "secret");
            if (modo === "certificate") {
                document.getElementById("mode-cert").checked = true;
                toggleModoAuth("certificate");
            } else {
                document.getElementById("mode-secret").checked = true;
                toggleModoAuth("secret");
            }

            if (data.tiene_certificado) {
                document.getElementById("cfg-client-cert").value = "•••••••••••••••• (Certificado y Llave Privada configurados)";
                document.getElementById("hint-cert").innerHTML = "✅ Certificado configurado previamente. Carga uno nuevo solo si deseas reemplazarlo.";
            }

            if (data.tiene_secreto) {
                document.getElementById("cfg-client-secret").value = "••••••••••••••••";
                document.getElementById("hint-secret").innerHTML = "✅ Secreto configurado previamente. Escribe uno nuevo solo si deseas reemplazarlo.";
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
    const modo = document.getElementById("mode-cert").checked ? "certificate" : "secret";
    const certPem = document.getElementById("cfg-client-cert").value.trim();
    const secret = document.getElementById("cfg-client-secret").value.trim();

    const statusBox = document.getElementById("status-box");
    const spinner = document.getElementById("test-spinner");
    const btn = document.getElementById("btn-probar-conexion");

    statusBox.style.display = "block";
    statusBox.className = "status-box info";
    statusBox.textContent = "Conectando con Microsoft Entra ID...";
    btn.disabled = true;
    spinner.textContent = "⏳";

    try {
        const res = await fetch("/api/conector/entra-id/probar", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                tipo_auth: modo,
                tenant_id: tenantId,
                client_id: clientId,
                client_cert_pem: certPem,
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
    const modo = document.getElementById("mode-cert").checked ? "certificate" : "secret";
    const certPem = document.getElementById("cfg-client-cert").value.trim();
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
                tipo_auth: modo,
                tenant_id: tenantId,
                client_id: clientId,
                client_cert_pem: certPem,
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
    mostrarToast("🔄 Sincronizando directorio, catálogo y Shadow IT desde Microsoft Entra ID...");

    try {
        const res = await fetch("/api/conector/entra-id/sincronizar", {
            method: "POST"
        });
        const data = await res.json();

        if (res.ok && data.success) {
            mostrarToast(`✅ ${data.mensaje}`);
            await cargarTodo();
        } else {
            if (res.status === 400 && data.error && (data.error.includes("no está configurado") || data.error.includes("Se requiere"))) {
                abrirModalTenant();
                mostrarToast("⚠️ Por favor configura el Tenant y credenciales en el modal.");
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

async function desconectarTenant() {
    const confirmacion = confirm(
        "¿Estás seguro de que deseas desconectar el tenant de tu empresa y vaciar el módulo?\n\n" +
        "Esta acción eliminará las credenciales configuradas y vaciará completamente todos los datos del inventario (usuarios, aplicativos de catálogo y Shadow IT)."
    );
    if (!confirmacion) return;

    const btn = document.getElementById("btn-desconectar-tenant");
    if (btn) btn.disabled = true;
    const btnModal = document.getElementById("btn-modal-desconectar");
    if (btnModal) btnModal.disabled = true;

    mostrarToast("🔌 Desconectando tenant y vaciando inventario...");

    try {
        const res = await fetch("/api/conector/entra-id/desconectar", {
            method: "POST"
        });
        const data = await res.json();

        if (res.ok && data.success) {
            mostrarToast("✅ " + data.mensaje);

            // Limpiar inputs del modal
            document.getElementById("cfg-tenant-id").value = "";
            document.getElementById("cfg-client-id").value = "";
            document.getElementById("cfg-client-cert").value = "";
            document.getElementById("cfg-client-secret").value = "";
            const hintCert = document.getElementById("hint-cert");
            if (hintCert) hintCert.innerHTML = "Usa el archivo <code>IdentityHub_Completo.pem</code> generado en tu carpeta Descargas.";
            const hintSecret = document.getElementById("hint-secret");
            if (hintSecret) hintSecret.textContent = "Para organizaciones donde los secretos no están bloqueados por directiva.";

            cerrarModalTenant();
            await cargarTodo();
        } else {
            mostrarToast(`❌ ${data.error || "No se pudo desconectar el tenant."}`);
        }
    } catch (e) {
        mostrarToast(`❌ Error de comunicación: ${e.message}`);
    } finally {
        if (btn) btn.disabled = false;
        if (btnModal) btnModal.disabled = false;
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
    document.getElementById("btn-desconectar-tenant")?.addEventListener("click", desconectarTenant);
    document.getElementById("btn-modal-desconectar")?.addEventListener("click", desconectarTenant);

    // Conmutador de modo de autenticación (Certificado vs Secreto)
    document.getElementById("mode-cert")?.addEventListener("change", () => toggleModoAuth("certificate"));
    document.getElementById("mode-secret")?.addEventListener("change", () => toggleModoAuth("secret"));

    // Lector de archivo PEM
    const inputPem = document.getElementById("input-pem-file");
    inputPem?.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (evt) => {
            document.getElementById("cfg-client-cert").value = evt.target.result;
            mostrarToast(`📁 Archivo ${file.name} cargado correctamente.`);
        };
        reader.readAsText(file);
    });

    // Cerrar modal al hacer clic en el backdrop
    document.getElementById("modal-tenant")?.addEventListener("click", (e) => {
        if (e.target.id === "modal-tenant") cerrarModalTenant();
    });
});
