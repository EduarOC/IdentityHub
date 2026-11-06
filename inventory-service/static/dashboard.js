// Panel del inventario de IdentityHub.
// Los datos vienen de la API y pueden venir de Microsoft Entra ID (nombres de usuarios y de
// aplicaciones), así que nunca se insertan como HTML: todo se arma con nodos y textContent.

const formatoMoneda = new Intl.NumberFormat("es-CO", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const formatoFecha = { year: "numeric", month: "short", day: "numeric" };
const NIVEL_RIESGO = { alto: "Riesgo alto", medio: "Riesgo medio", bajo: "Riesgo bajo" };

// Catálogo y Shadow IT indexados por id, para enriquecer el detalle de cada usuario.
const catalogo = new Map();
const shadowIT = new Map();
let usuarioEnDetalle = null;

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
    if (!res.ok) {
        // La API responde {"error": "..."} con un mensaje apto para mostrar al administrador.
        const cuerpo = await res.json().catch(() => ({}));
        const error = new Error(cuerpo.error || `HTTP ${res.status}`);
        error.mensaje = cuerpo.error;
        throw error;
    }
    return res.json();
}

function enviarJSON(url, metodo, datos) {
    return pedirJSON(url, {
        method: metodo,
        headers: { "Content-Type": "application/json" },
        body: datos === undefined ? undefined : JSON.stringify(datos),
    });
}

// Mensaje vacío con un enlace a Integraciones, para los estados sin datos.
function vacioConEnlace(mensaje) {
    return [el("span", { texto: `${mensaje} ` }), el("a", { texto: "Conecta un proveedor", atributos: { href: "#integraciones" } })];
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
        filaMensaje(tbody, 5, "");
        tbody.querySelector("td").replaceChildren(...vacioConEnlace("Todavía no hay usuarios."));
    } else {
        tbody.replaceChildren(...usuarios.map(filaUsuario));
    }
    document.getElementById("kpi-usuarios").textContent =
        usuarios.filter(u => u.estado === "activo").length;
}

const ESTADO_USUARIO = {
    activo: { texto: "Activo", clase: "badge-activo" },
    inactivo: { texto: "Inactivo", clase: "badge-inactivo" },
    offboarding: { texto: "Offboarding", clase: "badge-offboarding" },
};

function badgeEstado(estado) {
    const info = ESTADO_USUARIO[estado] || ESTADO_USUARIO.activo;
    return el("span", { clase: `badge ${info.clase}`, texto: info.texto });
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

    const enlace = el("button", {
        clase: "link-usuario",
        texto: u.nombre,
        atributos: { type: "button", "aria-haspopup": "dialog", "aria-label": `Ver aplicativos de ${u.nombre}` },
    });
    enlace.addEventListener("click", () => abrirDetalle(u));

    return el("tr", {}, [
        el("td", { clase: "col-nombre" }, [enlace]),
        celda(u.correo, "col-correo"),
        el("td", { clase: "col-estado" }, [badgeEstado(u.estado)]),
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
            // El responsable lo pone el servidor con el usuario que inició sesión en el proxy.
            body: JSON.stringify({}),
        });
        if (!data.success) throw new Error(data.error || "respuesta sin éxito");
        const lista = data.aplicativos_revocados.length > 0 ? data.aplicativos_revocados.join(", ") : "ningún acceso activo";
        mostrarToast(`Offboarding de ${nombre} completado. Revocado: ${lista}`);
        await cargarUsuarios();
        await refrescarDetalle(usuarioId);
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

    catalogo.clear();
    apps.forEach(a => catalogo.set(a.id, a));
    if (apps.length === 0) {
        filaMensaje(tbody, 3, "");
        tbody.querySelector("td").replaceChildren(...vacioConEnlace("Todavía no hay aplicativos."));
    } else {
        tbody.replaceChildren(...apps.map(a => el("tr", {}, [
            celda(a.nombre),
            el("td", {}, [el("span", { clase: `badge badge-${a.tipo_soporte_sso}`, texto: a.tipo_soporte_sso })]),
            // Entra ID no informa el costo de las licencias: sin dato se muestra un guion, no US$ 0.
            celda(a.costo_licencia_mensual ? formatoMoneda.format(a.costo_licencia_mensual) : "—", "num"),
        ])));
    }

    const costoTotal = apps.reduce((suma, a) => suma + (a.costo_licencia_mensual || 0), 0);
    document.getElementById("kpi-apps").textContent = apps.length;
    document.getElementById("kpi-costo").textContent = costoTotal ? formatoMoneda.format(costoTotal) : "—";
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

    shadowIT.clear();
    apps.forEach(a => shadowIT.set(a.id, a));
    if (apps.length === 0) {
        grid.replaceChildren(el("p", { clase: "estado-vacio" }, vacioConEnlace("Sin hallazgos de Shadow IT por ahora.")));
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
        : "sin dato";

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

// ------------------------------------------------------------------ detalle de un usuario
function fecha(iso) {
    return iso ? new Date(iso).toLocaleDateString("es-CO", formatoFecha) : "—";
}

function filaAcceso(acceso) {
    const app = catalogo.get(acceso.aplicativo_id);
    const descubierto = shadowIT.get(acceso.aplicativo_id);
    const revocado = Boolean(acceso.fecha_revocado);

    let etiqueta;
    if (descubierto) {
        const clase = claseRiesgo(descubierto.puntaje_riesgo);
        etiqueta = el("span", { clase: `badge risk-${clase}`, texto: `Shadow IT · ${Math.round(descubierto.puntaje_riesgo)}` });
    } else if (app) {
        etiqueta = el("span", { clase: `badge badge-${app.tipo_soporte_sso}`, texto: `SSO ${app.tipo_soporte_sso}` });
    } else {
        etiqueta = el("span", { clase: "badge badge-offboarding", texto: "Sin catálogo" });
    }

    const fechas = revocado
        ? `Otorgado ${fecha(acceso.fecha_otorgado)} · Revocado ${fecha(acceso.fecha_revocado)}`
        : `Otorgado ${fecha(acceso.fecha_otorgado)}`;

    return el("li", { clase: `acceso${revocado ? " acceso-revocado" : ""}` }, [
        el("div", { clase: "acceso-principal" }, [
            el("span", { clase: "acceso-nombre", texto: acceso.aplicativo }),
            etiqueta,
        ]),
        el("div", { clase: "acceso-meta" }, [
            el("span", { texto: fechas }),
            app ? el("span", { clase: "num", texto: `${formatoMoneda.format(app.costo_licencia_mensual || 0)}/mes` }) : el("span"),
        ]),
    ]);
}

function seccionAccesos(titulo, accesos, vacio) {
    const encabezado = el("h3", { clase: "detalle-seccion", texto: `${titulo} (${accesos.length})` });
    const contenido = accesos.length
        ? el("ul", { clase: "lista-accesos" }, accesos.map(filaAcceso))
        : el("p", { clase: "estado-vacio", texto: vacio });
    return [encabezado, contenido];
}

async function abrirDetalle(usuario) {
    usuarioEnDetalle = usuario;
    const dialogo = document.getElementById("detalle-usuario");
    const retirado = usuario.estado === "offboarding";

    document.getElementById("detalle-nombre").textContent = usuario.nombre;
    document.getElementById("detalle-correo").textContent = usuario.correo;
    const estado = document.getElementById("detalle-estado");
    const info = ESTADO_USUARIO[usuario.estado] || ESTADO_USUARIO.activo;
    estado.className = `badge ${info.clase}`;
    estado.textContent = info.texto;

    const cuerpo = document.getElementById("detalle-cuerpo");
    cuerpo.replaceChildren(el("p", { clase: "estado-vacio", texto: "Cargando aplicativos…" }));
    document.getElementById("detalle-resumen").textContent = "";

    const boton = document.getElementById("detalle-offboard");
    boton.hidden = retirado;
    boton.disabled = false;
    boton.textContent = "Iniciar offboarding";
    boton.onclick = () => ejecutarOffboarding(usuario.id, usuario.nombre, boton);

    if (!dialogo.open) dialogo.showModal();

    let accesos;
    try {
        accesos = await pedirJSON(`/api/usuarios/${encodeURIComponent(usuario.id)}/accesos?historial=1`);
    } catch (error) {
        console.error("No se pudieron cargar los accesos:", error);
        cuerpo.replaceChildren(el("p", { clase: "estado-error", texto: "No se pudieron cargar los aplicativos de este usuario." }));
        return;
    }
    if (usuarioEnDetalle !== usuario) return;  // se abrió otro usuario mientras cargaba

    const vigentes = accesos.filter(a => !a.fecha_revocado);
    const revocados = accesos.filter(a => a.fecha_revocado);
    const costo = vigentes.reduce((suma, a) => suma + (catalogo.get(a.aplicativo_id)?.costo_licencia_mensual || 0), 0);
    const conShadow = vigentes.filter(a => shadowIT.has(a.aplicativo_id)).length;

    document.getElementById("detalle-resumen").textContent =
        `${vigentes.length} ${vigentes.length === 1 ? "aplicativo vigente" : "aplicativos vigentes"} · ` +
        `${formatoMoneda.format(costo)} al mes en licencias` +
        (conShadow ? ` · ${conShadow} de Shadow IT` : "");

    cuerpo.replaceChildren(
        ...seccionAccesos("Accesos vigentes", vigentes, retirado ? "Sin accesos vigentes: el retiro ya se ejecutó." : "Este usuario no tiene accesos vigentes."),
        ...(revocados.length ? seccionAccesos("Historial de accesos revocados", revocados, "") : []),
    );
}

async function refrescarDetalle(usuarioId) {
    const dialogo = document.getElementById("detalle-usuario");
    if (!dialogo.open || !usuarioEnDetalle || usuarioEnDetalle.id !== usuarioId) return;
    const usuarios = await pedirJSON("/api/usuarios");
    const actualizado = usuarios.find(u => u.id === usuarioId);
    if (actualizado) await abrirDetalle(actualizado);
}

function prepararDetalle() {
    const dialogo = document.getElementById("detalle-usuario");
    document.getElementById("detalle-cerrar").addEventListener("click", () => dialogo.close());
    // Clic en el fondo oscuro (fuera de la tarjeta) cierra el detalle.
    dialogo.addEventListener("click", evento => {
        if (evento.target === dialogo) dialogo.close();
    });
    dialogo.addEventListener("close", () => { usuarioEnDetalle = null; });
}

// ------------------------------------------------------------------ integraciones
const ESTADO_CONECTOR = {
    desconectado: { texto: "No conectado", clase: "badge-offboarding" },
    pendiente: { texto: "Sin probar", clase: "badge-proxy" },
    conectado: { texto: "Conectado", clase: "badge-activo" },
    sincronizando: { texto: "Sincronizando…", clase: "badge-sincronizando" },
    error: { texto: "Requiere atención", clase: "badge-ninguno" },
};
const SIGLAS = { entra_id: "EN", google_workspace: "GW", keycloak: "KC" };
let conectores = [];
let sondeo = null;

function fechaHora(iso) {
    return new Date(iso).toLocaleString("es-CO", { ...formatoFecha, hour: "2-digit", minute: "2-digit" });
}

function textoResumen(r) {
    return `${r.usuarios} usuarios · ${r.aplicativos} aplicaciones · ${r.shadow_it} con permisos OAuth`;
}

function boton(texto, clase, accion, etiqueta) {
    const b = el("button", { clase, texto, atributos: { type: "button", ...(etiqueta ? { "aria-label": etiqueta } : {}) } });
    b.addEventListener("click", () => accion(b));
    return b;
}

function detallesConector(c) {
    const detalles = [];
    if (c.nombre_tenant) detalles.push(el("p", { clase: "conector-meta", texto: `Tenant: ${c.nombre_tenant}` }));
    if (c.ultima_sincronizacion) {
        detalles.push(el("p", { clase: "conector-meta", texto: `Última sincronización: ${fechaHora(c.ultima_sincronizacion)}` }));
    }
    if (c.resumen) detalles.push(el("p", { clase: "conector-meta", texto: textoResumen(c.resumen) }));
    if (c.ultimo_error) detalles.push(el("p", { clase: "conector-error", texto: c.ultimo_error, atributos: { role: "status" } }));
    return detalles;
}

function accionesConector(c) {
    if (!c.disponible) return [];  // la tarjeta solo anuncia lo que viene
    if (c.estado === "desconectado") {
        return [boton("Conectar", "btn-primario", () => abrirConfiguracion(c), `Conectar ${c.nombre}`)];
    }
    const sincronizando = c.estado === "sincronizando";
    let principal;
    if (c.estado === "pendiente") {
        principal = boton("Probar conexión", "btn-primario", b => probarYSincronizar(c, b));
    } else {
        principal = boton(sincronizando ? "Sincronizando…" : "Sincronizar ahora", "btn-primario", b => sincronizarConector(c, b));
        principal.disabled = sincronizando;
    }
    const configurar = boton("Configurar", "btn-secundario", () => abrirConfiguracion(c), `Configurar ${c.nombre}`);
    const desconectar = boton("Desconectar", "btn-enlace", b => desconectarConector(c, b), `Desconectar ${c.nombre}`);
    configurar.disabled = sincronizando;
    desconectar.disabled = sincronizando;
    return [principal, configurar, desconectar];
}

function tarjetaConector(c) {
    const estado = c.disponible ? (ESTADO_CONECTOR[c.estado] || ESTADO_CONECTOR.desconectado) : { texto: "Próximamente", clase: "badge-offboarding" };
    const cabecera = el("div", { clase: "conector-cabecera" }, [
        el("span", { clase: `conector-logo conector-logo-${c.tipo}`, texto: SIGLAS[c.tipo] || "··", atributos: { "aria-hidden": "true" } }),
        el("div", { clase: "conector-titulo" }, [
            el("h2", { texto: c.nombre }),
            el("span", { clase: `badge ${estado.clase}`, texto: estado.texto }),
        ]),
    ]);
    const acciones = accionesConector(c);
    return el("article", { clase: `conector${c.disponible ? "" : " conector-proximo"}` }, [
        cabecera,
        el("p", { clase: "conector-descripcion", texto: c.descripcion }),
        ...detallesConector(c),
        acciones.length ? el("div", { clase: "conector-acciones" }, acciones) : el("span"),
    ]);
}

async function cargarConectores() {
    const grid = document.getElementById("conectores-grid");
    try {
        conectores = await pedirJSON("/api/conectores");
    } catch (error) {
        console.error("No se pudieron cargar las integraciones:", error);
        grid.replaceChildren(el("p", { clase: "estado-error", texto: "No se pudieron cargar las integraciones." }));
        return;
    }
    grid.replaceChildren(...conectores.map(tarjetaConector));
    const algunoConectado = conectores.some(c => c.estado !== "desconectado");
    document.getElementById("bienvenida").hidden = algunoConectado;
    vigilarSincronizacion();
}

async function revisarSincronizacion() {
    const antes = new Map(conectores.map(c => [c.tipo, c.estado]));
    await cargarConectores();
    const terminados = conectores.filter(c => antes.get(c.tipo) === "sincronizando" && c.estado !== "sincronizando");
    terminados.forEach(c => {
        if (c.estado === "conectado") mostrarToast(`${c.nombre} sincronizado: ${textoResumen(c.resumen)}.`);
        else mostrarToast(`La sincronización de ${c.nombre} falló. Revisa el mensaje en la tarjeta.`, "error");
    });
    if (terminados.some(c => c.estado === "conectado")) await cargarTodo();
}

function vigilarSincronizacion() {
    const enCurso = conectores.some(c => c.estado === "sincronizando");
    if (enCurso && !sondeo) {
        sondeo = setInterval(() => {
            revisarSincronizacion().catch(error => console.error("No se pudo revisar la sincronización:", error));
        }, 3000);
    } else if (!enCurso && sondeo) {
        clearInterval(sondeo);
        sondeo = null;
    }
}

let conectorEnEdicion = null;

function abrirConfiguracion(c) {
    conectorEnEdicion = c;
    document.getElementById("config-titulo").textContent = `${c.estado === "desconectado" ? "Conectar" : "Configurar"} ${c.nombre}`;
    document.getElementById("config-tenant").value = c.tenant_id || "";
    document.getElementById("config-cliente").value = c.client_id || "";
    const secreto = document.getElementById("config-secreto");
    secreto.value = "";
    secreto.placeholder = c.tiene_secreto ? "Guardado · déjalo vacío para conservarlo" : "";
    document.getElementById("config-secreto-ayuda").textContent = c.tiene_secreto
        ? "Hay un secreto guardado. Escribe uno nuevo solo si lo rotaste en Entra ID."
        : "Se guarda cifrado y nunca se vuelve a mostrar.";
    document.getElementById("config-error").textContent = "";
    document.getElementById("config-conector").showModal();
    document.getElementById("config-tenant").focus();
}

async function guardarConfiguracion(evento) {
    evento.preventDefault();
    const c = conectorEnEdicion;
    const error = document.getElementById("config-error");
    const guardar = document.getElementById("config-guardar");
    error.textContent = "";
    guardar.disabled = true;
    guardar.textContent = "Guardando…";
    try {
        await enviarJSON(`/api/conectores/${encodeURIComponent(c.tipo)}`, "PUT", {
            tenant_id: document.getElementById("config-tenant").value,
            client_id: document.getElementById("config-cliente").value,
            client_secret: document.getElementById("config-secreto").value,
        });
        guardar.textContent = "Probando conexión…";
        const prueba = await enviarJSON(`/api/conectores/${encodeURIComponent(c.tipo)}/probar`, "POST");
        document.getElementById("config-conector").close();
        mostrarToast(`Conectado a ${prueba.nombre_tenant} · iniciando la primera sincronización…`);
        await enviarJSON(`/api/conectores/${encodeURIComponent(c.tipo)}/sincronizar`, "POST");
    } catch (error_) {
        console.error("No se pudo conectar:", error_);
        if (document.getElementById("config-conector").open) {
            error.textContent = error_.mensaje || "No se pudo guardar la configuración. Intenta de nuevo.";
        } else {
            mostrarToast(error_.mensaje || "No se pudo iniciar la sincronización.", "error");
        }
    } finally {
        guardar.disabled = false;
        guardar.textContent = "Guardar y conectar";
        await cargarConectores();
    }
}

async function probarYSincronizar(c, b) {
    b.disabled = true;
    b.textContent = "Probando…";
    try {
        const prueba = await enviarJSON(`/api/conectores/${encodeURIComponent(c.tipo)}/probar`, "POST");
        mostrarToast(`Conectado a ${prueba.nombre_tenant}`);
    } catch (error_) {
        mostrarToast(error_.mensaje || "La prueba de conexión falló.", "error");
    }
    await cargarConectores();
}

async function sincronizarConector(c, b) {
    b.disabled = true;
    b.textContent = "Sincronizando…";
    try {
        await enviarJSON(`/api/conectores/${encodeURIComponent(c.tipo)}/sincronizar`, "POST");
    } catch (error_) {
        mostrarToast(error_.mensaje || "No se pudo iniciar la sincronización.", "error");
    }
    await cargarConectores();
}

async function desconectarConector(c, b) {
    if (!confirm(`¿Desconectar ${c.nombre}?\n\nSe borran las credenciales guardadas y se deja de sincronizar. ` +
                 "Los usuarios, aplicativos y el historial de accesos se conservan.")) return;
    b.disabled = true;
    try {
        await enviarJSON(`/api/conectores/${encodeURIComponent(c.tipo)}`, "DELETE");
        mostrarToast(`${c.nombre} desconectado. El inventario se conserva.`);
    } catch (error_) {
        mostrarToast(error_.mensaje || "No se pudo desconectar.", "error");
    }
    await cargarConectores();
}

function prepararConfiguracion() {
    const dialogo = document.getElementById("config-conector");
    document.getElementById("config-formulario").addEventListener("submit", guardarConfiguracion);
    document.getElementById("config-cancelar").addEventListener("click", () => dialogo.close());
    dialogo.addEventListener("click", evento => {
        if (evento.target === dialogo) dialogo.close();
    });
}

// ------------------------------------------------------------------ vistas
function mostrarVista() {
    const vista = location.hash === "#integraciones" ? "integraciones" : "inventario";
    document.getElementById("vista-inventario").hidden = vista !== "inventario";
    document.getElementById("vista-integraciones").hidden = vista !== "integraciones";
    document.querySelectorAll(".pestana").forEach(p => {
        if (p.dataset.vista === vista) p.setAttribute("aria-current", "page");
        else p.removeAttribute("aria-current");
    });
}

// ------------------------------------------------------------------ sesión
async function cargarSesion() {
    // Detrás del proxy el servidor sabe quién inició sesión; en desarrollo devuelve null
    // y la barra no muestra el bloque de sesión.
    const { usuario } = await pedirJSON("/api/sesion");
    if (!usuario) return;
    document.getElementById("sesion-usuario").textContent = usuario;
    document.getElementById("sesion").hidden = false;
}

async function cargarTodo() {
    await Promise.all([cargarUsuarios(), cargarAplicativos(), cargarShadowIT()]);
}

document.addEventListener("DOMContentLoaded", () => {
    prepararDetalle();
    prepararConfiguracion();
    mostrarVista();
    window.addEventListener("hashchange", mostrarVista);
    cargarConectores().catch(error => console.error("No se pudieron cargar las integraciones:", error));
    cargarSesion().catch(error => console.error("No se pudo leer la sesión:", error));
    cargarTodo().catch(() => mostrarToast("No se pudo cargar el panel. Recarga la página.", "error"));
});
