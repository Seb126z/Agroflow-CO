const I18N = {
  es: {
    loader_text: "Cargando AgroFlow CO…",
    brand_tag: "Precios mayoristas SIPSA-DANE",
    info_btn: "Info",
    kpi_observaciones: "Observaciones",
    kpi_productos: "Productos",
    kpi_ciudades: "Ciudades",
    kpi_precio: "Precio promedio",
    label_producto: "Producto",
    label_ciudad: "Ciudad",
    label_desde: "Desde",
    label_hasta: "Hasta",
    label_fuente: "Fuente",
    opt_todas: "Todas",
    btn_buscar: "Buscar",
    btn_limpiar: "Limpiar",
    chart_evolucion: "Evolución del precio promedio",
    chart_departamento: "Precio promedio por departamento",
    chart_ciudad: "Precio promedio por ciudad",
    chart_volatiles: "Productos más volátiles",
    table_title: "Detalle por producto y mercado",
    table_producto: "Producto",
    table_mercado: "Mercado",
    table_precio: "Precio promedio",
    table_variacion: "Variación % promedio",
    table_observaciones: "Observaciones",
    footer_text: "Datos: SIPSA-DANE · Pipeline AgroFlow-CO (Python) → PostgreSQL → esta vista web de solo lectura.",
    placeholder_producto: "Ej: Papa, Tomate, Cebolla...",
    placeholder_ciudad: "Ej: Bogotá, Medellín...",
    status_cargando: "Cargando datos…",
    status_sin_datos: "Sin datos para estos filtros",
    info_title: "¿Qué es AgroFlow CO?",
    info_body: `
      <p>AgroFlow CO es un pipeline de datos que automatiza la obtención, limpieza y
      análisis de precios mayoristas agrícolas colombianos, publicados por el
      <strong>SIPSA (Sistema de Información de Precios y Abastecimiento del Sector
      Agropecuario)</strong> del DANE.</p>
      <p><strong>Cómo funciona:</strong></p>
      <ol>
        <li>Un pipeline en Python consulta en vivo el servicio web (SOAP) oficial de SIPSA-DANE.</li>
        <li>Los datos crudos se guardan sin modificar, luego se normalizan y validan (fechas, precios).</li>
        <li>Se cargan en una base de datos PostgreSQL, evitando duplicados.</li>
        <li>Esta página (y también un dashboard en Power BI) consulta esa base en <em>solo lectura</em> para mostrar las gráficas y filtros.</li>
      </ol>
      <p>Ningún dato mostrado aquí es inventado o simulado: todo proviene de consultas reales al servicio oficial de DANE.</p>
    `,
  },
  en: {
    loader_text: "Loading AgroFlow CO…",
    brand_tag: "SIPSA-DANE wholesale prices",
    info_btn: "Info",
    kpi_observaciones: "Observations",
    kpi_productos: "Products",
    kpi_ciudades: "Cities",
    kpi_precio: "Average price",
    label_producto: "Product",
    label_ciudad: "City",
    label_desde: "From",
    label_hasta: "To",
    label_fuente: "Source",
    opt_todas: "All",
    btn_buscar: "Search",
    btn_limpiar: "Clear",
    chart_evolucion: "Average price trend",
    chart_departamento: "Average price by department",
    chart_ciudad: "Average price by city",
    chart_volatiles: "Most volatile products",
    table_title: "Detail by product and market",
    table_producto: "Product",
    table_mercado: "Market",
    table_precio: "Average price",
    table_variacion: "Avg. % change",
    table_observaciones: "Observations",
    footer_text: "Data: SIPSA-DANE · AgroFlow-CO pipeline (Python) → PostgreSQL → this read-only web view.",
    placeholder_producto: "E.g: Potato, Tomato, Onion...",
    placeholder_ciudad: "E.g: Bogotá, Medellín...",
    status_cargando: "Loading data…",
    status_sin_datos: "No data for these filters",
    info_title: "What is AgroFlow CO?",
    info_body: `
      <p>AgroFlow CO is a data pipeline that automates fetching, cleaning and
      analyzing Colombian agricultural wholesale prices, published by
      <strong>SIPSA (the Colombian national agency DANE's Price and Supply
      Information System)</strong>.</p>
      <p><strong>How it works:</strong></p>
      <ol>
        <li>A Python pipeline queries SIPSA-DANE's official SOAP web service live.</li>
        <li>Raw data is saved unmodified, then normalized and validated (dates, prices).</li>
        <li>It's loaded into a PostgreSQL database, avoiding duplicates.</li>
        <li>This page (and also a Power BI dashboard) queries that database <em>read-only</em> to render the charts and filters.</li>
      </ol>
      <p>Nothing shown here is invented or simulated: everything comes from real queries against DANE's official service.</p>
    `,
  },
};

let currentLang = "es";

function applyLang(lang) {
  currentLang = lang;
  document.documentElement.lang = lang;
  const dict = I18N[lang];

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (dict[key] !== undefined) el.innerHTML = dict[key];
  });

  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (dict[key] !== undefined) el.setAttribute("placeholder", dict[key]);
  });

  const langBtn = document.getElementById("btn-lang");
  if (langBtn) langBtn.textContent = lang === "es" ? "EN" : "ES";
}

document.addEventListener("DOMContentLoaded", () => {
  applyLang("es");

  document.getElementById("btn-lang").addEventListener("click", () => {
    applyLang(currentLang === "es" ? "en" : "es");
  });

  document.getElementById("btn-info").addEventListener("click", () => {
    document.getElementById("info-overlay").hidden = false;
  });
  document.getElementById("btn-info-close").addEventListener("click", () => {
    document.getElementById("info-overlay").hidden = true;
  });
  document.getElementById("info-overlay").addEventListener("click", (e) => {
    if (e.target.id === "info-overlay") document.getElementById("info-overlay").hidden = true;
  });
});
