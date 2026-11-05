/* =====================================================================
   Analisis Espectral TIFF — aplicacion estatica para GitHub Pages
   Todo se ejecuta en el navegador (sin servidor).
   ===================================================================== */

const app = (() => {
  // ---------- estado ----------
  const S = {
    width: 0,
    height: 0,
    bands: {},      // nombre -> Float32Array
    bandNames: [],
    assignments: {},// rol -> nombre de banda (red, green, nir, swir, blue)
    resolutionM: null,
    results: {},    // nombreIndice -> {array, stats, classes, title}
    coverage: null, // Int8Array (0=otro,1=agua,2=vegetacion,3=suelo)
    histChart: null,
  };

  const geotiff = window.geotiff || window.GeoTIFF || null;

  // ---------- utilidades ----------
  const $ = (id) => {
    const el = document.getElementById(id);
    if (!el) console.error("Elemento no encontrado: #" + id);
    return el;
  };
  const escapeHtml = (t) => String(t).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  const showError = (msg) => { console.error(msg); alert("Error: " + msg); };

  function safeDiv(num, den) {
    const n = num.length, out = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const d = den[i];
      out[i] = Math.abs(d) > 1e-12 ? (num[i] - den[i]) / (num[i] + den[i]) : NaN;
    }
    return out;
  }

  function stats(arr) {
    let n = 0, sum = 0, min = Infinity, max = -Infinity;
    for (let i = 0; i < arr.length; i++) {
      const v = arr[i];
      if (!isFinite(v)) continue;
      n++; sum += v; if (v < min) min = v; if (v > max) max = v;
    }
    if (!n) return {mean:NaN,std:NaN,min:NaN,max:NaN,median:NaN,count:0};
    const mean = sum / n;
    let ss = 0;
    for (let i = 0; i < arr.length; i++) { const v = arr[i]; if (isFinite(v)) ss += (v - mean) ** 2; }
    const std = Math.sqrt(ss / n);
    const sorted = [];
    for (let i = 0; i < arr.length; i++) { const v = arr[i]; if (isFinite(v)) sorted.push(v); }
    sorted.sort((a,b) => a - b);
    const median = sorted.length % 2 ? sorted[(sorted.length - 1) / 2] : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;
    return {mean, std, min, max, median, count: n};
  }

  function haFromPx(resM, count) {
    if (!resM) return null;
    return (count * resM * resM) / 10000;
  }

  // ---------- colormaps ----------
  function interpColor(t, stops) {
    t = Math.max(0, Math.min(1, t));
    for (let i = 0; i < stops.length - 1; i++) {
      if (t >= stops[i][0] && t <= stops[i + 1][0]) {
        const local = (t - stops[i][0]) / (stops[i + 1][0] - stops[i][0]);
        return stops[i].slice(1).map((c, j) => Math.round(c + (stops[i + 1][1 + j] - c) * local));
      }
    }
    return stops[stops.length - 1].slice(1);
  }
  const CMAPS = {
    RdYlGn: [
      [0, 165, 0, 38], [0.125, 215, 48, 39], [0.25, 244, 109, 67],
      [0.375, 253, 174, 97], [0.5, 254, 224, 139], [0.625, 217, 239, 139],
      [0.75, 166, 217, 106], [0.875, 102, 189, 99], [1, 26, 152, 80]
    ],
    Blues: [
      [0, 247, 251, 255], [0.25, 222, 235, 247], [0.5, 198, 219, 239],
      [0.75, 158, 202, 225], [1, 8, 81, 156]
    ],
    YlOrBr: [
      [0, 255, 255, 204], [0.25, 255, 237, 160], [0.5, 254, 217, 118],
      [0.75, 254, 178, 76], [1, 153, 51, 0]
    ]
  };

  function applyColormap(arr, cmapName, vmin, vmax) {
    const stops = CMAPS[cmapName];
    const n = arr.length;
    const data = new Uint8ClampedArray(n * 4);
    const range = vmax - vmin || 1;
    for (let i = 0; i < n; i++) {
      const v = arr[i];
      const base = i * 4;
      if (!isFinite(v)) { data[base] = 210; data[base+1] = 210; data[base+2] = 210; data[base+3] = 0; continue; }
      let t = (v - vmin) / range;
      const c = interpColor(t, stops);
      data[base] = c[0]; data[base+1] = c[1]; data[base+2] = c[2]; data[base+3] = 255;
    }
    return data;
  }

  function normalizeDisplay(arr, plow = 2, phigh = 98) {
    const n = arr.length;
    const finite = [];
    for (let i = 0; i < n; i++) { const v = arr[i]; if (isFinite(v)) finite.push(v); }
    if (!finite.length) return new Float32Array(n).fill(0);
    finite.sort((a,b) => a - b);
    const lo = finite[Math.floor((plow / 100) * (finite.length - 1))];
    const hi = finite[Math.floor((phigh / 100) * (finite.length - 1))];
    const out = new Float32Array(n);
    const rng = hi - lo || 1;
    for (let i = 0; i < n; i++) out[i] = Math.min(1, Math.max(0, (arr[i] - lo) / rng));
    return out;
  }

  // ---------- carga de TIFF ----------
  async function loadFile(file) {
    if (!geotiff) {
      showError("geotiff.js no cargo. Verifica tu conexion a internet (se requiere cargar librerias externas).");
      return;
    }
    try {
      const ab = await file.arrayBuffer();
      const tiff = await geotiff.fromArrayBuffer(ab);
      const image = await tiff.getImage();
      S.width = image.getWidth();
      S.height = image.getHeight();
      const rasters = await image.readRasters();
      // readRasters puede devolver un array o un objeto { banda: ArrayBuffer }
      let rasterList;
      if (Array.isArray(rasters)) {
        rasterList = rasters;
      } else if (rasters && typeof rasters === "object") {
        rasterList = Object.keys(rasters).sort((a,b) => parseInt(a)-parseInt(b)).map(k => rasters[k]);
      } else {
        throw new Error("Formato de rasteres no reconocido al leer el TIFF.");
      }
      S.bands = {}; S.bandNames = [];
      for (let i = 0; i < rasterList.length; i++) {
        const name = "Banda " + (i + 1);
        const arr = rasterList[i];
        S.bands[name] = arr instanceof Float64Array ? Float32Array.from(arr) : Float32Array.from(arr);
        S.bandNames.push(name);
      }
      S.assignments = {};
      S.results = {}; S.coverage = null;
      const fi = $("fileInfo");
      if (fi) { fi.textContent = `Cargado: ${escapeHtml(file.name)}  |  ${S.width} x ${S.height}  |  ${S.bandNames.length} banda(s)`; fi.className = ""; }
      renderBandSelects();
      renderMeta();
      renderBandStats();
      switchPage("visor");
    } catch (err) {
      showError("No se pudo leer el TIFF: " + (err && err.message ? err.message : String(err)));
    }
  }

  function loadDemo() {
    try {
      const w = 240, h = 180;
      const rng = () => (Math.random() - 0.5) * 0.04;
      const red = new Float32Array(w * h);
      const green = new Float32Array(w * h);
      const nir = new Float32Array(w * h);
      for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
          const i = y * w + x;
          let r, g, n;
          if (y < 60) { r = 0.45; g = 0.30; n = 0.35; }      // suelo
          else if (y < 120) { r = 0.12; g = 0.35; n = 0.75; } // vegetacion
          else { r = 0.05; g = 0.08; n = 0.02; }              // agua
          red[i] = Math.min(1, Math.max(0, r + rng()));
          green[i] = Math.min(1, Math.max(0, g + rng()));
          nir[i] = Math.min(1, Math.max(0, n + rng()));
        }
      }
      S.width = w; S.height = h;
      S.bands = { "Banda 1": red, "Banda 2": green, "Banda 3": nir };
      S.bandNames = ["Banda 1", "Banda 2", "Banda 3"];
      S.assignments = {}; S.results = {}; S.coverage = null;
      const fi = $("fileInfo");
      if (fi) { fi.textContent = "Imagen de demostracion  |  " + w + " x " + h + "  |  3 banda(s)"; fi.className = ""; }
      renderBandSelects();
      renderMeta();
      renderBandStats();
      switchPage("visor");
    } catch (err) {
      showError("No se pudo cargar la demostracion: " + (err && err.message ? err.message : String(err)));
    }
  }

  function renderBandSelects() {
    const container = $("bandSelects");
    if (!container) return;
    container.innerHTML = "";
    const roles = [
      { key: "red", label: "Rojo (Red)" },
      { key: "green", label: "Verde (Green)" },
      { key: "nir", label: "NIR (infrarrojo cercano)" },
      { key: "swir", label: "SWIR (infrarrojo onda corta)" },
      { key: "blue", label: "Azul (Blue)" },
    ];
    roles.forEach(({ key, label }) => {
      const wrap = document.createElement("div");
      wrap.style.marginBottom = ".6rem";
      const lab = document.createElement("label");
      lab.textContent = label;
      lab.style.display = "block";
      lab.style.fontSize = ".82rem";
      lab.style.fontWeight = "600";
      lab.style.color = "var(--green-dark)";
      const sel = document.createElement("select");
      sel.id = "sel_" + key;
      sel.style.width = "100%";
      sel.style.padding = ".45rem .6rem";
      sel.style.border = "1px solid var(--border)";
      sel.style.borderRadius = ".4rem";
      sel.style.background = "#fff";
      const empty = document.createElement("option");
      empty.value = ""; empty.textContent = "(sin asignar)";
      sel.appendChild(empty);
      S.bandNames.forEach((bn) => {
        const o = document.createElement("option");
        o.value = bn; o.textContent = bn;
        sel.appendChild(o);
      });
      sel.onchange = () => {
        if (sel.value) S.assignments[key] = sel.value;
        else delete S.assignments[key];
      };
      wrap.appendChild(lab);
      wrap.appendChild(sel);
      container.appendChild(wrap);
    });
    updateRGBSselects();
  }

  function updateRGBSselects() {
    ["R", "G", "B"].forEach((ch) => {
      const sel = $("rgb" + ch);
      if (!sel) return;
      while (sel.options.length > 0) sel.remove(0);
      S.bandNames.forEach((bn) => {
        const o = document.createElement("option");
        o.value = bn; o.textContent = bn;
        sel.appendChild(o);
      });
    });
  }

  function renderMeta() {
    const t = $("metaTable");
    if (!t) return;
    t.innerHTML = `
      <tr><td>Forma (alto x ancho)</td><td>${S.height} x ${S.width}</td></tr>
      <tr><td>Numero de bandas</td><td>${S.bandNames.length}</td></tr>
      <tr><td>Bandas</td><td>${S.bandNames.join(", ")}</td></tr>
      <tr><td>Resolucion espacial</td><td>${S.resolutionM ? S.resolutionM + " m/pixel" : "no especificada"}</td></tr>
    `;
  }

  function renderBandStats() {
    const box = $("bandStats");
    if (!box) return;
    box.innerHTML = "";
    S.bandNames.forEach((bn) => {
      const st = stats(S.bands[bn]);
      const el = document.createElement("div");
      el.style.fontSize = ".82rem";
      el.innerHTML = `<strong>${escapeHtml(bn)}:</strong> medio ${st.mean.toFixed(3)} | min ${st.min.toFixed(3)} | max ${st.max.toFixed(3)} | std ${st.std.toFixed(3)}`;
      box.appendChild(el);
    });
  }

  // ---------- renderizacion ----------
  function drawArrayToCanvas(canvas, arr, cmapName, vmin, vmax) {
    const w = S.width, h = S.height;
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext("2d");
    const imgd = ctx.createImageData(w, h);
    const data = applyColormap(arr, cmapName, vmin, vmax);
    imgd.data.set(data);
    ctx.putImageData(imgd, 0, 0);
  }

  function drawRGB() {
    const rSel = $("rgbR"), gSel = $("rgbG"), bSel = $("rgbB");
    if (!rSel || !gSel || !bSel) return;
    const rName = rSel.value, gName = gSel.value, bName = bSel.value;
    if (!rName || !gName || !bName) {
      const cv = $("viewer");
      if (cv) cv.innerHTML = "Selecciona las tres bandas RGB.";
      return;
    }
    const r = normalizeDisplay(S.bands[rName]);
    const g = normalizeDisplay(S.bands[gName]);
    const b = normalizeDisplay(S.bands[bName]);
    const w = S.width, h = S.height;
    const canvas = $("viewer");
    if (!canvas) return;
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext("2d");
    const imgd = ctx.createImageData(w, h);
    const d = imgd.data;
    for (let i = 0; i < w * h; i++) {
      const base = i * 4;
      d[base] = Math.round(r[i] * 255);
      d[base + 1] = Math.round(g[i] * 255);
      d[base + 2] = Math.round(b[i] * 255);
      d[base + 3] = 255;
    }
    ctx.putImageData(imgd, 0, 0);
  }

  // ---------- indices ----------
  function getBand(role) {
    const name = S.assignments[role];
    return name ? S.bands[name] : null;
  }

  function calcIndex(kind) {
    try {
      const need = {
        NDVI: ["nir", "red"], SAVI: ["nir", "red"], EVI: ["nir", "red", "blue"],
        NDWI: ["green", "nir"], MNDWI: ["green", "swir"], NDBI: ["swir", "nir"],
      }[kind];
      const falta = need.filter((r) => !getBand(r));
      if (falta.length) {
        alert("Falta asignar la(s) banda(s): " + falta.join(", "));
        return;
      }
      const red = getBand("red"), green = getBand("green"), nir = getBand("nir"), swir = getBand("swir"), blue = getBand("blue");
      let arr;
      switch (kind) {
        case "NDVI": arr = (() => { const out = new Float32Array(nir.length); for (let i = 0; i < nir.length; i++) { const d = nir[i] + red[i]; out[i] = Math.abs(d) > 1e-12 ? (nir[i] - red[i]) / d : NaN; } return out; })(); break;
        case "SAVI": arr = (() => { const L = 0.5; const out = new Float32Array(nir.length); for (let i = 0; i < nir.length; i++) { const d = nir[i] + red[i] + L; out[i] = Math.abs(d) > 1e-12 ? ((nir[i] - red[i]) / d) * (1 + L) : NaN; } return out; })(); break;
        case "EVI": arr = (() => { const G = 2.5, C1 = 6, C2 = 7.5, L = 1; const out = new Float32Array(nir.length); for (let i = 0; i < nir.length; i++) { const den = nir[i] + C1 * red[i] - C2 * blue[i] + L; out[i] = Math.abs(den) > 1e-12 ? G * (nir[i] - red[i]) / den : NaN; } return out; })(); break;
        case "NDWI": arr = (() => { const out = new Float32Array(green.length); for (let i = 0; i < green.length; i++) { const d = green[i] + nir[i]; out[i] = Math.abs(d) > 1e-12 ? (green[i] - nir[i]) / d : NaN; } return out; })(); break;
        case "MNDWI": arr = (() => { const out = new Float32Array(green.length); for (let i = 0; i < green.length; i++) { const d = green[i] + swir[i]; out[i] = Math.abs(d) > 1e-12 ? (green[i] - swir[i]) / d : NaN; } return out; })(); break;
        case "NDBI": arr = (() => { const out = new Float32Array(swir.length); for (let i = 0; i < swir.length; i++) { const d = swir[i] + nir[i]; out[i] = Math.abs(d) > 1e-12 ? (swir[i] - nir[i]) / d : NaN; } return out; })(); break;
        default: throw new Error("Indice no soportado: " + kind);
      }
      const st = stats(arr);
      let classes;
      const title = {
        NDVI: "Vegetacion (NDVI)", SAVI: "Vegetacion (SAVI)", EVI: "Vegetacion (EVI)",
        NDWI: "Fuentes hidricas (NDWI)", MNDWI: "Fuentes hidricas (MNDWI)", NDBI: "Suelos / construido (NDBI)",
      }[kind];
      if (kind === "NDVI" || kind === "SAVI" || kind === "EVI") classes = classifyNDVI(arr);
      else if (kind === "NDWI" || kind === "MNDWI") classes = classifyNDWI(arr);
      else classes = classifyNDBI(arr);
      S.results[kind] = { array: arr, stats: st, classes, title };
      refreshIndexSelect();
      $("indexSelect").value = kind;
      showIndex(kind);
    } catch (err) {
      showError("No se pudo calcular " + kind + ": " + (err && err.message ? err.message : String(err)));
    }
  }

  function refreshIndexSelect() {
    const sel = $("indexSelect");
    if (!sel) return;
    const cur = sel.value;
    while (sel.options.length > 0) sel.remove(0);
    Object.keys(S.results).forEach((k) => {
      const o = document.createElement("option");
      o.value = k; o.textContent = S.results[k].title;
      sel.appendChild(o);
    });
    if (S.results[cur]) sel.value = cur;
  }

  function showIndex(kind) {
    try {
      const res = S.results[kind];
      if (!res) return;
      const vmin = -1, vmax = 1;
      const cmap = kind === "NDBI" ? "YlOrBr" : (kind === "NDWI" || kind === "MNDWI") ? "Blues" : "RdYlGn";
      drawArrayToCanvas($("indexCanvas"), res.array, cmap, vmin, vmax);
      const rv = $("rangeVal");
      if (rv) rv.textContent = vmin + " a " + vmax;
      const st = res.stats;
      const isEl = $("indexStats");
      if (isEl) isEl.innerHTML = `
        <div><strong>Pixeles validos:</strong> ${st.count.toLocaleString()}</div>
        <div><strong>Medio:</strong> ${st.mean.toFixed(3)}</div>
        <div><strong>Min:</strong> ${st.min.toFixed(3)}</div>
        <div><strong>Max:</strong> ${st.max.toFixed(3)}</div>
        <div><strong>Desv. est.:</strong> ${st.std.toFixed(3)}</div>
        <div><strong>Mediana:</strong> ${st.median.toFixed(3)}</div>
      `;
      drawHist(res.array, kind);
      renderClassesTable(kind, res.classes, st.count);
    } catch (err) {
      showError("No se pudo mostrar el indice: " + (err && err.message ? err.message : String(err)));
    }
  }

  function drawHist(arr, name) {
    try {
      const finite = [];
      for (let i = 0; i < arr.length; i++) { const v = arr[i]; if (isFinite(v)) finite.push(v); }
      const counts = new Array(40).fill(0);
      const min = -1, max = 1, rng = max - min;
      finite.forEach((v) => { const bi = Math.min(39, Math.floor(((v - min) / rng) * 40)); counts[bi]++; });
      const maxc = Math.max(...counts);
      const labels = counts.map((_, i) => (min + (i + 0.5) * rng / 40).toFixed(2));
      const cv = $("indexHist");
      if (!cv) return;
      const ctx = cv.getContext("2d");
      if (S.histChart) S.histChart.destroy();
      S.histChart = new Chart(ctx, {
        type: "bar",
        data: { labels, datasets: [{ label: name, data: counts, backgroundColor: "#4a90e2" }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, max: maxc, ticks: { stepSize: Math.ceil(maxc / 5) } } } },
      });
    } catch (err) {
      console.error("Error en histograma:", err);
    }
  }

  // ---------- clasificaciones ----------
  function classifyNDVI(arr) {
    const total = stats(arr).count;
    const rules = [
      ["Agua / Sin vegetacion", "< 0.00", (v) => v < 0],
      ["Suelo desnudo / muy baja", "0.00 - 0.20", (v) => v >= 0 && v < 0.2],
      ["Vegetacion baja / estres", "0.20 - 0.40", (v) => v >= 0.2 && v < 0.4],
      ["Vegetacion moderada", "0.40 - 0.60", (v) => v >= 0.4 && v < 0.6],
      ["Vegetacion densa / sana", ">= 0.60", (v) => v >= 0.6],
    ];
    return buildClasses(arr, rules, total);
  }
  function classifyNDWI(arr) {
    const total = stats(arr).count;
    const rules = [
      ["Sin agua / suelo seco", "< 0.00", (v) => v < 0],
      ["Humedad moderada", "0.00 - 0.20", (v) => v >= 0 && v < 0.2],
      ["Cuerpo hidrico / agua", ">= 0.20", (v) => v >= 0.2],
    ];
    return buildClasses(arr, rules, total);
  }
  function classifyNDBI(arr) {
    const total = stats(arr).count;
    const rules = [
      ["Suelo vegetado / agua", "< 0.00", (v) => v < 0],
      ["Suelo desnudo mixto", "0.00 - 0.10", (v) => v >= 0 && v < 0.1],
      ["Area expuesta / construida", ">= 0.10", (v) => v >= 0.1],
    ];
    return buildClasses(arr, rules, total);
  }
  function buildClasses(arr, rules, total) {
    return rules.map(([name, rango, fn]) => {
      let cnt = 0;
      for (let i = 0; i < arr.length; i++) { const v = arr[i]; if (isFinite(v) && fn(v)) cnt++; }
      return { clase: name, rango, pixeles: cnt, porcentaje: total ? (cnt / total * 100) : 0 };
    });
  }

  function renderClassesTable(kind, classes, total) {
    const idMap = { NDVI: "areaNDVI", NDWI: "areaAGUA", MNDWI: "areaAGUA", NDBI: "areaNDBI" };
    const target = $(idMap[kind]);
    if (!target) return;
    let html = "<table style='width:100%;border-collapse:collapse;font-size:.82rem'><tr><th style='text-align:left'>Clase</th><th style='text-align:left'>Rango</th><th style='text-align:right'>Pixeles</th><th style='text-align:right'>% Area</th></tr>";
    classes.forEach((c) => {
      html += `<tr><td>${escapeHtml(c.clase)}</td><td>${escapeHtml(c.rango)}</td><td style='text-align:right'>${c.pixeles.toLocaleString()}</td><td style='text-align:right'>${c.porcentaje.toFixed(2)}%</td></tr>`;
    });
    html += "</table>";
    target.innerHTML = html;
  }

  function updateResolution() {
    try {
      const v = parseFloat($("resInput").value);
      S.resolutionM = isNaN(v) || v <= 0 ? null : v;
      const note = $("haNote");
      if (note) note.textContent = S.resolutionM ? `Cada pixel representa ${((S.resolutionM ** 2) / 10000).toFixed(4)} ha.` : "Resolucion no definida: solo pixeles y porcentajes.";
      renderMeta();
      if (S.coverage) renderCoverage();
    } catch (err) {
      console.error("Error actualizando resolucion:", err);
    }
  }

  // ---------- cobertura combinada ----------
  function buildCoverage() {
    try {
      const ndvi = S.results.NDVI ? S.results.NDVI.array : null;
      const ndwiKey = S.results.MNDWI ? "MNDWI" : (S.results.NDWI ? "NDWI" : null);
      const ndwi = ndwiKey ? S.results[ndwiKey].array : null;
      const ndbi = S.results.NDBI ? S.results.NDBI.array : null;
      if (!ndvi || (!ndwi && !ndbi)) {
        $("areaCover").innerHTML = "Calcula NDVI y (NDWI/MNDWI o NDBI) para ver la cobertura combinada.";
        return;
      }
      const n = ndvi.length;
      const cov = new Int8Array(n);
      for (let i = 0; i < n; i++) {
        const v = ndvi[i], w = ndwi ? ndwi[i] : NaN, b = ndbi ? ndbi[i] : NaN;
        const agua = isFinite(w) && w > 0.10;
        const veget = isFinite(v) && v > 0.25 && !agua;
        const suelo = isFinite(b) && b > 0.10 && !agua && !veget;
        if (agua) cov[i] = 1;
        else if (veget) cov[i] = 2;
        else if (suelo) cov[i] = 3;
        else cov[i] = 0;
      }
      S.coverage = cov;
      renderCoverage();
    } catch (err) {
      showError("No se pudo construir la cobertura: " + (err && err.message ? err.message : String(err)));
    }
  }

  function renderCoverage() {
    try {
      const cov = S.coverage;
      const total = cov.length;
      const c1 = cov.filter((x) => x === 1).length;
      const c2 = cov.filter((x) => x === 2).length;
      const c3 = cov.filter((x) => x === 3).length;
      const ha = (r) => S.resolutionM ? (r * S.resolutionM ** 2 / 10000).toFixed(2) : "-";
      $("areaCover").innerHTML = `
        <table style='width:100%;border-collapse:collapse;font-size:.82rem;margin-bottom:.5rem'>
          <tr><th style='text-align:left'>Cobertura</th><th style='text-align:right'>Pixeles</th><th style='text-align:right'>% Area</th><th style='text-align:right'>Area (ha)</th></tr>
          <tr><td>Agua</td><td style='text-align:right'>${c1.toLocaleString()}</td><td style='text-align:right'>${(c1 / total * 100).toFixed(2)}%</td><td style='text-align:right'>${ha(c1)}</td></tr>
          <tr><td>Vegetacion</td><td style='text-align:right'>${c2.toLocaleString()}</td><td style='text-align:right'>${(c2 / total * 100).toFixed(2)}%</td><td style='text-align:right'>${ha(c2)}</td></tr>
          <tr><td>Suelo expuesto / construido</td><td style='text-align:right'>${c3.toLocaleString()}</td><td style='text-align:right'>${(c3 / total * 100).toFixed(2)}%</td><td style='text-align:right'>${ha(c3)}</td></tr>
        </table>`;
      const canvas = $("coverCanvas");
      canvas.width = S.width; canvas.height = S.height;
      const ctx = canvas.getContext("2d");
      const imgd = ctx.createImageData(S.width, S.height);
      const d = imgd.data;
      const colors = { 0: [210, 210, 210, 0], 1: [74, 144, 226, 255], 2: [126, 211, 33, 255], 3: [224, 161, 59, 255] };
      for (let i = 0; i < cov.length; i++) {
        const base = i * 4;
        const c = colors[cov[i]];
        d[base] = c[0]; d[base+1] = c[1]; d[base+2] = c[2]; d[base+3] = c[3];
      }
      ctx.putImageData(imgd, 0, 0);
    } catch (err) {
      showError("No se pudo renderizar la cobertura: " + (err && err.message ? err.message : String(err)));
    }
  }

  // ---------- navegacion ----------
  function switchPage(id) {
    try {
      document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      $(id).classList.add("active");
      $(`[data-tab="${id}"]`).classList.add("active");
    } catch (err) {
      console.error("Error cambiando pestaña:", err);
    }
  }

  // ---------- CSV ----------
  function downloadCSV() {
    try {
      if (!Object.keys(S.results).length) { alert("No hay resultados para exportar."); return; }
      let csv = "indice,min,max,medio,desvio,mediana,pixeles_validos\n";
      Object.entries(S.results).forEach(([k, r]) => {
        const s = r.stats;
        csv += `${k},${s.min.toFixed(4)},${s.max.toFixed(4)},${s.mean.toFixed(4)},${s.std.toFixed(4)},${s.median.toFixed(4)},${s.count}\n`;
      });
      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "indices_espectrales.csv"; a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      showError("No se pudo descargar el CSV: " + (err && err.message ? err.message : String(err)));
    }
  }

  // ---------- PDF ----------
  async function generatePDF() {
    try {
      const { jsPDF } = window.jspdf || {};
      if (!jsPDF) { showError("jsPDF no cargo. Verifica tu conexion a internet."); return; }
      if (!Object.keys(S.results).length) { alert("No hay resultados para incluir en el reporte."); return; }

      const pdf = new jsPDF({ orientation: "p", unit: "mm", format: "a4" });
      const now = new Date().toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" });
      const fileName = $("fileInput").files[0] ? $("fileInput").files[0].name : "demostracion.tif";

      pdf.setFont("helvetica", "bold");
      pdf.setTextColor(27, 122, 69);
      pdf.fontSize(16);
      pdf.text("Informe de Analisis de Imagen TIFF", 20, 20);
      pdf.setFont("helvetica", "normal");
      pdf.setTextColor(100, 100, 100);
      pdf.fontSize(10);
      pdf.text("Fecha de generacion: " + now, 20, 30);
      pdf.text("Archivo analizado: " + escapeHtml(fileName), 20, 38);
      pdf.text("Dimensiones: " + S.height + " x " + S.width + " pixeles", 20, 46);
      pdf.text("Resolucion espacial: " + (S.resolutionM ? S.resolutionM + " m/pixel" : "no especificada"), 20, 54);

      pdf.setFont("helvetica", "bold");
      pdf.setTextColor(27, 122, 69);
      pdf.fontSize(12);
      pdf.text("Resumen ejecutivo", 20, 68);
      pdf.setFont("helvetica", "normal");
      pdf.setTextColor(60, 60, 60);
      pdf.fontSize(9.5);
      const resumen = $("repResumen").value.split("\n");
      let y = 76;
      resumen.forEach((line) => { pdf.text(escapeHtml(line), 20, y); y += 6; });

      y += 6;
      pdf.setFont("helvetica", "bold");
      pdf.setTextColor(27, 122, 69);
      pdf.fontSize(11);
      pdf.text("Indices espectrales calculados", 20, y);
      y += 6;
      pdf.setFont("helvetica", "normal");
      pdf.setTextColor(60, 60, 60);
      pdf.fontSize(8.5);
      const headers = ["Indice", "Min", "Max", "Medio", "Desv.", "Estado general"];
      const colX = [20, 55, 80, 105, 130, 155];
      pdf.setFillColor(27, 122, 69);
      pdf.setTextColor(255, 255, 255);
      headers.forEach((h, i) => pdf.text(h, colX[i], y));
      pdf.setTextColor(60, 60, 60);
      y += 5;
      Object.entries(S.results).forEach(([k, r]) => {
        const s = r.stats;
        let estado = "";
        if (["NDVI", "SAVI", "EVI"].includes(k)) estado = s.mean > 0.3 ? "Vegetacion destacada" : "Vegetacion limitada";
        else if (["NDWI", "MNDWI"].includes(k)) estado = s.mean > 0.1 ? "Agua significativa" : "Poca agua detectada";
        else if (k === "NDBI") estado = s.mean > 0.05 ? "Suelos expuestos notables" : "Baja exposicion de suelo";
        const row = [k, s.min.toFixed(3), s.max.toFixed(3), s.mean.toFixed(3), s.std.toFixed(3), estado];
        row.forEach((v, i) => pdf.text(v, colX[i], y));
        y += 5;
      });

      for (const kind of ["NDVI", "NDWI", "MNDWI", "NDBI", "SAVI", "EVI"]) {
        const res = S.results[kind];
        if (!res) continue;
        pdf.addPage();
        pdf.setFont("helvetica", "bold");
        pdf.setTextColor(27, 122, 69);
        pdf.fontSize(12.5);
        pdf.text(res.title, 20, 20);
        const cmap = kind === "NDBI" ? "YlOrBr" : (kind === "NDWI" || kind === "MNDWI") ? "Blues" : "RdYlGn";
        drawArrayToCanvas($("indexCanvas"), res.array, cmap, -1, 1);
        const mapImg = $("indexCanvas").toDataURL("image/png");
        pdf.addImage(mapImg, "PNG", 20, 28, 90, 45);
        drawHist(res.array, kind);
        const histImg = $("indexHist").toDataURL("image/png");
        pdf.addImage(histImg, "PNG", 115, 28, 75, 32);
        const s = res.stats;
        y = 80;
        pdf.setFont("helvetica", "normal");
        pdf.setTextColor(60, 60, 60);
        pdf.fontSize(9);
        pdf.text(`Validos: ${s.count.toLocaleString()} pixeles | Medio: ${s.mean.toFixed(3)} | Min: ${s.min.toFixed(3)} | Max: ${s.max.toFixed(3)} | Desv.: ${s.std.toFixed(3)} | Mediana: ${s.median.toFixed(3)}`, 20, y);
        y += 7;
        pdf.setFont("helvetica", "bold");
        pdf.fontSize(10);
        pdf.text("Distribucion por clases", 20, y);
        y += 5;
        pdf.setFont("helvetica", "normal");
        pdf.fontSize(8.5);
        const cheaders = ["Clase", "Rango", "Pixeles", "% Area"];
        const ccolX = [20, 65, 115, 150];
        pdf.setFillColor(27, 122, 69);
        pdf.setTextColor(255, 255, 255);
        cheaders.forEach((h, i) => pdf.text(h, ccolX[i], y));
        pdf.setTextColor(60, 60, 60);
        y += 4.5;
        res.classes.forEach((c) => {
          pdf.text(escapeHtml(c.clase), ccolX[0], y);
          pdf.text(escapeHtml(c.rango), ccolX[1], y);
          pdf.text(c.pixeles.toLocaleString(), ccolX[2], y);
          pdf.text(c.porcentaje.toFixed(2) + "%", ccolX[3], y);
          y += 4.5;
        });
        y += 3;
        pdf.setFont("helvetica", "italic");
        pdf.fontSize(9);
        pdf.text("Interpretacion: valores mas altos indican mayor presencia del fenomeno asociado al indice.", 20, y);
      }

      if (S.coverage) {
        pdf.addPage();
        pdf.setFont("helvetica", "bold");
        pdf.setTextColor(27, 122, 69);
        pdf.fontSize(12.5);
        pdf.text("Clasificacion de cobertura del terreno", 20, 20);
        renderCoverage();
        const covImg = $("coverCanvas").toDataURL("image/png");
        pdf.addImage(covImg, "PNG", 20, 28, 90, 40);
        const total = S.coverage.length;
        const c1 = S.coverage.filter((x) => x === 1).length;
        const c2 = S.coverage.filter((x) => x === 2).length;
        const c3 = S.coverage.filter((x) => x === 3).length;
        y = 78;
        pdf.setFont("helvetica", "normal");
        pdf.setTextColor(60, 60, 60);
        pdf.fontSize(9.5);
        pdf.text(`Agua: ${c1.toLocaleString()} pixeles (${(c1 / total * 100).toFixed(2)}% del area)`, 20, y); y += 6;
        pdf.text(`Vegetacion: ${c2.toLocaleString()} pixeles (${(c2 / total * 100).toFixed(2)}% del area)`, 20, y); y += 6;
        pdf.text(`Suelo expuesto / construido: ${c3.toLocaleString()} pixeles (${(c3 / total * 100).toFixed(2)}% del area)`, 20, y); y += 6;
        if (S.resolutionM) {
          const ha = (r) => (r * S.resolutionM ** 2 / 10000).toFixed(2);
          pdf.text("Areas aproximadas (resolucion " + S.resolutionM + " m/pixel):", 20, y); y += 6;
          pdf.text(`Agua: ${ha(c1)} ha`, 20, y); y += 5;
          pdf.text(`Vegetacion: ${ha(c2)} ha`, 20, y); y += 5;
          pdf.text(`Suelo expuesto / construido: ${ha(c3)} ha`, 20, y);
        }
      }

      pdf.addPage();
      pdf.setFont("helvetica", "bold");
      pdf.setTextColor(27, 122, 69);
      pdf.fontSize(12.5);
      pdf.text("Conclusiones y recomendaciones", 20, 20);
      pdf.setFont("helvetica", "normal");
      pdf.setTextColor(60, 60, 60);
      pdf.fontSize(9.5);
      const concl = $("repConclusiones").value.split("\n");
      y = 30;
      concl.forEach((line) => { pdf.text("• " + escapeHtml(line), 20, y); y += 6.5; });
      y += 4;
      pdf.setFont("helvetica", "italic");
      pdf.fontSize(7.5);
      pdf.setTextColor(140, 140, 140);
      pdf.text("Metodologia: indices espectrales calculados a partir de bandas de reflejo satelital (NDVI, NDWI, MNDWI, NDBI, SAVI, EVI).", 20, y);
      pdf.text("Las areas se estiman en pixeles y, si se proporciona la resolucion espacial, en hectareas.", 20, y + 5);
      pdf.text("Los umbrales de clasificacion son referenciales y deben validarse con datos de campo.", 20, y + 10);

      const blob = pdf.output("blob");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "reporte_analisis_tif.pdf";
      a.click();
      URL.revokeObjectURL(url);
      $("pdfStatus").textContent = "Reporte generado y descargado.";
    } catch (err) {
      showError("No se pudo generar el reporte PDF: " + (err && err.message ? err.message : String(err)));
    }
  }

  // ---------- inicializacion ----------
  function init() {
    try {
      const fi = $("fileInput");
      if (fi) fi.addEventListener("change", (e) => {
        if (e.target.files[0]) loadFile(e.target.files[0]);
      });
      const bd = $("btnDemo");
      if (bd) bd.addEventListener("click", loadDemo);
      const ri = $("resInput");
      if (ri) { ri.addEventListener("change", updateResolution); ri.addEventListener("input", updateResolution); }
      ["rgbR", "rgbG", "rgbB"].forEach((id) => { const el = $(id); if (el) el.addEventListener("change", drawRGB); });
      const is = $("indexSelect");
      if (is) is.addEventListener("change", (e) => showIndex(e.target.value));
      const ir = $("indexRange");
      if (ir) ir.addEventListener("input", (e) => {
        const v = e.target.value.split(",");
        const kind = $("indexSelect").value;
        const res = S.results[kind];
        if (!res) return;
        const cmap = kind === "NDBI" ? "YlOrBr" : (kind === "NDWI" || kind === "MNDWI") ? "Blues" : "RdYlGn";
        drawArrayToCanvas($("indexCanvas"), res.array, cmap, parseFloat(v[0]), parseFloat(v[1]));
        $("rangeVal").textContent = v[0] + " a " + v[1];
      });
      const dc = $("btnDownloadCSV");
      if (dc) dc.addEventListener("click", downloadCSV);
      const gp = $("btnGenPDF");
      if (gp) gp.addEventListener("click", generatePDF);
      document.querySelectorAll(".tab").forEach((t) => {
        t.addEventListener("click", () => switchPage(t.dataset.tab));
      });
      switchPage("visor");
    } catch (err) {
      showError("Error inicializando la aplicacion: " + (err && err.message ? err.message : String(err)));
    }
  }

  return {
    init,
    calcIndex,
    showIndex,
    downloadCSV,
    generatePDF,
    buildCoverage,
    drawRGB,
  };
})();

// manejador global de errores no capturados
window.addEventListener("error", (e) => {
  console.error("Error no capturado:", e.error || e.message);
  alert("Error en la aplicacion: " + (e.error && e.error.message ? e.error.message : e.message));
});
window.addEventListener("unhandledrejection", (e) => {
  console.error("Promesa rechazada no manejada:", e.reason);
  alert("Error: " + (e.reason && e.reason.message ? e.reason.message : String(e.reason)));
});

window.addEventListener("DOMContentLoaded", () => app.init());
