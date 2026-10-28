const RED = "#D7263D";
const RED_SOFT = "rgba(215, 38, 61, 0.15)";
const INK_SOFT = "#5B6168";

const els = {
  producto: document.getElementById("f-producto"),
  ciudad: document.getElementById("f-ciudad"),
  desde: document.getElementById("f-desde"),
  hasta: document.getElementById("f-hasta"),
  fuente: document.getElementById("f-fuente"),
  btnBuscar: document.getElementById("btn-buscar"),
  btnLimpiar: document.getElementById("btn-limpiar"),
  productosList: document.getElementById("productos-list"),
  ciudadesList: document.getElementById("ciudades-list"),
  status: document.getElementById("status-line"),
  lastUpdate: document.getElementById("last-update"),
  pageLoader: document.getElementById("page-loader"),
  chartsLoader: document.getElementById("charts-loader"),
};

function hidePageLoader() {
  els.pageLoader.classList.add("fade-out");
  setTimeout(() => { els.pageLoader.hidden = true; }, 300);
}

let charts = {};

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Error ${res.status} consultando ${url}`);
  }
  return res.json();
}

function currentFilters() {
  const params = new URLSearchParams();
  if (els.producto.value.trim()) params.set("producto", els.producto.value.trim());
  if (els.ciudad.value.trim()) params.set("ciudad", els.ciudad.value.trim());
  if (els.desde.value) params.set("desde", `${els.desde.value}-01`);
  if (els.hasta.value) params.set("hasta", `${els.hasta.value}-28`);
  if (els.fuente.value) params.set("fuente", els.fuente.value);
  return params;
}

function setStatus(msg, isError = false) {
  els.status.textContent = msg;
  els.status.style.color = isError ? RED : INK_SOFT;
}

function toggleNoData(key, isEmpty) {
  const el = document.getElementById(`no-data-${key}`);
  if (el) el.hidden = !isEmpty;
}

async function loadMeta() {
  const [productos, ciudades, fuentes] = await Promise.all([
    fetchJSON("/api/meta/productos"),
    fetchJSON("/api/meta/ciudades"),
    fetchJSON("/api/meta/fuentes"),
  ]);
  els.productosList.innerHTML = productos.map((p) => `<option value="${p}">`).join("");
  els.ciudadesList.innerHTML = ciudades.map((c) => `<option value="${c}">`).join("");
  els.fuente.innerHTML =
    `<option value="">Todas</option>` + fuentes.map((f) => `<option value="${f}">${f}</option>`).join("");
}

// Sin `params`: carga inicial (totales globales), también fija el rango
// de fechas seleccionable y el estado de la última corrida.
// Con `params`: los KPIs reaccionan a los filtros activos, igual que las
// tarjetas del dashboard de Power BI.
async function loadResumen(params) {
  const isInitial = params === undefined;
  const qs = params ? params.toString() : "";
  const r = await fetchJSON(`/api/resumen${qs ? `?${qs}` : ""}`);
  document.getElementById("kpi-observaciones").textContent = r.total_observaciones.toLocaleString("es-CO");
  document.getElementById("kpi-productos").textContent = r.total_productos.toLocaleString("es-CO");
  document.getElementById("kpi-ciudades").textContent = r.total_ciudades.toLocaleString("es-CO");

  if (isInitial) {
    // Solo se pueden elegir fechas dentro del rango real de datos cargados.
    if (r.fecha_minima && r.fecha_maxima) {
      const minMonth = r.fecha_minima.slice(0, 7);
      const maxMonth = r.fecha_maxima.slice(0, 7);
      els.desde.min = minMonth;
      els.desde.max = maxMonth;
      els.hasta.min = minMonth;
      els.hasta.max = maxMonth;
    }

    if (r.ultima_corrida) {
      const fecha = r.ultima_corrida.finished_at ? new Date(r.ultima_corrida.finished_at).toLocaleString("es-CO") : "—";
      els.lastUpdate.textContent = `Última carga: ${fecha} · ${r.ultima_corrida.source_system} (${r.ultima_corrida.status})`;
    } else {
      els.lastUpdate.textContent = "Sin corridas registradas";
    }
  }

  const precio = r.precio_promedio ? Number(r.precio_promedio).toLocaleString("es-CO", { maximumFractionDigits: 0 }) : "—";
  document.getElementById("kpi-precio").textContent = `$${precio}`;
}

function destroyChart(key) {
  if (charts[key]) charts[key].destroy();
}

async function loadEvolucion(params) {
  const data = await fetchJSON(`/api/precios/serie?${params.toString()}`);
  toggleNoData("evolucion", data.length === 0);
  if (data.length === 0) {
    destroyChart("evolucion");
    return;
  }
  // La API ya entrega un punto por mes (GROUP BY solo por mes), no hace
  // falta volver a agrupar en el cliente.
  const labels = data.map((row) => row.mes.slice(0, 10));
  const values = data.map((row) => Number(row.precio_promedio));

  destroyChart("evolucion");
  const ctx = document.getElementById("chart-evolucion");
  charts.evolucion = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Precio promedio",
          data: values,
          borderColor: RED,
          backgroundColor: RED_SOFT,
          fill: true,
          tension: 0.3,
          pointRadius: 2,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: "#F0F1F3" }, beginAtZero: false },
      },
    },
  });
}

async function loadPorCiudad(params) {
  const data = await fetchJSON(`/api/precios/por-ciudad?${params.toString()}`);
  toggleNoData("ciudad", data.length === 0);
  destroyChart("ciudad");
  if (data.length === 0) return;
  const ctx = document.getElementById("chart-ciudad");
  charts.ciudad = new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.map((d) => d.city),
      datasets: [
        {
          label: "Precio promedio",
          data: data.map((d) => Number(d.precio_promedio)),
          backgroundColor: RED,
          borderRadius: 4,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: "#F0F1F3" } },
        y: { grid: { display: false } },
      },
    },
  });
}

async function loadPorDepartamento(params) {
  const data = await fetchJSON(`/api/precios/por-departamento?${params.toString()}`);
  toggleNoData("departamento", data.length === 0);
  destroyChart("departamento");
  if (data.length === 0) return;
  const ctx = document.getElementById("chart-departamento");
  charts.departamento = new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.map((d) => d.department),
      datasets: [
        {
          label: "Precio promedio",
          data: data.map((d) => Number(d.precio_promedio)),
          backgroundColor: RED,
          borderRadius: 4,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: "#F0F1F3" } },
        y: { grid: { display: false } },
      },
    },
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

async function loadTabla(params) {
  const data = await fetchJSON(`/api/precios/tabla?${params.toString()}`);
  toggleNoData("tabla", data.length === 0);
  const tbody = document.getElementById("tabla-detalle-body");
  if (data.length === 0) {
    tbody.innerHTML = "";
    return;
  }
  tbody.innerHTML = data
    .map((row) => {
      const variacion = row.variacion_pct_promedio !== null ? Number(row.variacion_pct_promedio) : null;
      const cls = variacion === null ? "" : variacion >= 0 ? "up" : "down";
      const variacionTxt = variacion === null ? "—" : `${variacion > 0 ? "+" : ""}${variacion.toFixed(2)}%`;
      return `<tr>
        <td>${escapeHtml(row.product)}</td>
        <td>${row.market ? escapeHtml(row.market) : "—"}</td>
        <td class="num">$${Number(row.precio_promedio).toLocaleString("es-CO", { maximumFractionDigits: 0 })}</td>
        <td class="num ${cls}">${variacionTxt}</td>
        <td class="num">${row.num_observaciones.toLocaleString("es-CO")}</td>
      </tr>`;
    })
    .join("");
}

async function loadVolatiles() {
  const data = await fetchJSON("/api/precios/volatiles?limit=10");
  toggleNoData("volatiles", data.length === 0);
  destroyChart("volatiles");
  if (data.length === 0) return;
  const ctx = document.getElementById("chart-volatiles");
  charts.volatiles = new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.map((d) => d.product),
      datasets: [
        {
          label: "Volatilidad %",
          data: data.map((d) => Number(d.volatilidad_pct)),
          backgroundColor: RED,
          borderRadius: 4,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: "#F0F1F3" } },
        y: { grid: { display: false } },
      },
    },
  });
}

async function refreshAll() {
  const params = currentFilters();
  const dict = typeof I18N !== "undefined" ? I18N[currentLang] : null;
  setStatus(dict ? dict.status_cargando : "Cargando datos…");
  els.chartsLoader.hidden = false;
  els.btnBuscar.disabled = true;
  try {
    await Promise.all([
      loadEvolucion(params),
      loadPorCiudad(params),
      loadPorDepartamento(params),
      loadTabla(params),
      loadVolatiles(),
      loadResumen(params),
    ]);
    setStatus(params.toString() || "");
  } catch (err) {
    console.error(err);
    setStatus(`Error: ${err.message}`, true);
  } finally {
    els.chartsLoader.hidden = true;
    els.btnBuscar.disabled = false;
  }
}

els.btnBuscar.addEventListener("click", refreshAll);
els.btnLimpiar.addEventListener("click", () => {
  els.producto.value = "";
  els.ciudad.value = "";
  els.desde.value = "";
  els.hasta.value = "";
  els.fuente.value = "";
  refreshAll();
});

(async function init() {
  try {
    await Promise.all([loadMeta(), loadResumen()]);
    await refreshAll();
  } catch (err) {
    console.error(err);
    setStatus(`Error al iniciar: ${err.message}`, true);
  } finally {
    hidePageLoader();
  }
})();
