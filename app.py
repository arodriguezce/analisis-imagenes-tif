"""Aplicacion interactiva Streamlit para analisis espectral de imagenes TIFF."""
from __future__ import annotations

import io
import csv
import datetime

import numpy as np
import tifffile
import streamlit as st

from utils import (
    load_tiff, band_names, select_band, normalize_for_display,
    build_rgb, summary_stats, pixel_area_ha,
)
from indices import (
    ndvi, ndwi, mndwi, ndbi, savi, evi,
    classify_ndvi, classify_ndwi, classify_ndbi, coverage_map,
)
from reporte import build_pdf_report

st.set_page_config(
    page_title="Analisis Espectral TIFF",
    page_icon="🌿",
    layout="wide",
)

st.title("🌿 Analisis de Imagenes TIFF - Indices Espectrales")
st.caption("Carga una imagen TIFF multibanda (Landsat, Sentinel, dron, etc.), cuantifica indices "
           "espectrales, mide areas de vegetacion, suelos y fuentes hidricas, y genera un reporte.")

# ---------------------------------------------------------------------------
# Estado de sesion
# ---------------------------------------------------------------------------
if "tiff_info" not in st.session_state:
    st.session_state.tiff_info = None
if "results" not in st.session_state:
    st.session_state.results = {}        # nombre_indice -> dict(array, stats, classes)
if "coverage" not in st.session_state:
    st.session_state.coverage = None

# ---------------------------------------------------------------------------
# Barra lateral: carga y asignacion de bandas
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("1. Cargar imagen TIFF")
    up = st.file_uploader("Selecciona un archivo .tif / .tiff", type=["tif", "tiff"])
    if up is not None:
        try:
            info = load_tiff(up, axis_order=read_order)
            st.session_state.tiff_info = info
            st.session_state.tiff_file_name = up.name
            st.session_state.results = {}
            st.session_state.coverage = None
            st.success(f"Cargado: {up.name}  |  {info['shape']}  |  {info['ndim']}D")
        except Exception as exc:
            st.error(f"Error al leer el TIFF: {exc}")

        if st.button("🧪 Cargar imagen de demostracion"):
        # Sintetiza una escena con vegetacion, agua y suelo desnudo (3 bandas: Red, Verde, NIR)
        rng = np.random.default_rng(42)
        h, w = 180, 240
        red = np.zeros((h, w), dtype=np.float64)
        green = np.zeros((h, w), dtype=np.float64)
        nir = np.zeros((h, w), dtype=np.float64)
        # Suelo (marrón): red alta, nir media
        red[0:60, :] = 0.45; green[0:60, :] = 0.30; nir[0:60, :] = 0.35
        # Vegetacion: red baja, nir alta
        red[60:120, :] = 0.12; green[60:120, :] = 0.35; nir[60:120, :] = 0.75
        # Agua: todo bajo, nir muy baja
        red[120:, :] = 0.05; green[120:, :] = 0.08; nir[120:, :] = 0.02
        red += rng.normal(0, 0.02, red.shape); green += rng.normal(0, 0.02, green.shape); nir += rng.normal(0, 0.02, nir.shape)
        stack = np.clip(np.stack([red, green, nir]), 0, 1)
        buf = io.BytesIO()
        tifffile.imwrite(buf, stack.astype(np.float32))
        buf.seek(0)
        buf.name = "demo.tif"
        info = load_tiff(buf, axis_order=read_order)
        st.session_state.tiff_info = info
        st.session_state.tiff_file_name = "demo.tif"
        st.session_state.results = {}
        st.session_state.coverage = None
        st.success("Imagen de demostracion cargada (Red, Verde, NIR).")

    st.divider()
    st.header("2. Asignar bandas")
    info = st.session_state.tiff_info
    names = band_names(info) if info else []
    defaults = {"red": None, "green": None, "nir": None, "swir": None, "blue": None}
    if info:
        n = len(names)
        guesses = {"red": None, "green": None, "nir": None, "swir": None, "blue": None}
        if n >= 3:
            guesses["red"] = names[0]
            guesses["green"] = names[1]
            guesses["nir"] = names[2] if n > 3 else names[1]
        if n >= 4:
            guesses["swir"] = names[3]
        if n >= 5:
            guesses["blue"] = names[2]
        defaults.update(guesses)

    st.divider()
    st.header("4. Opciones de lectura")
    order_opt = st.selectbox(
        "Orden de ejes del TIFF",
        ["Automatico", "(Bandas, Alto, Ancho)", "(Alto, Ancho, Bandas)"],
        index=0,
        help="Solo cambialo si las bandas se ven incorrectas.",
    )
    order_map = {"Automatico": None, "(Bandas, Alto, Ancho)": "BHW", "(Alto, Ancho, Bandas)": "HWB"}
    read_order = order_map[order_opt]

    def bandbox(key, label):
        return st.selectbox(label, ["(sin asignar)"] + names,
                            index=(0 if defaults[key] is None else names.index(defaults[key]) + 1))

    band_red = bandbox("red", "Banda Rojo")
    band_green = bandbox("green", "Banda Verde")
    band_nir = bandbox("nir", "Banda NIR (infrarrojo cercano)")
    band_swir = bandbox("swir", "Banda SWIR (infrarrojo de onda corta)")
    band_blue = bandbox("blue", "Banda Azul")

    asg = {}
    if band_red != "(sin asignar)": asg["red"] = band_red
    if band_green != "(sin asignar)": asg["green"] = band_green
    if band_nir != "(sin asignar)": asg["nir"] = band_nir
    if band_swir != "(sin asignar)": asg["swir"] = band_swir
    if band_blue != "(sin asignar)": asg["blue"] = band_blue

    st.divider()
    st.header("3. Area (opcional)")
    res_m = st.number_input("Resolucion espacial (metros / pixel)", min_value=0.0,
                            value=0.0, step=1.0, help="Ej. Landsat 30, Sentinel-2 10. Deja en 0 para solo pixeles.")
    st.session_state.resolution_m = float(res_m) if res_m else None

# ---------------------------------------------------------------------------
# Contenido principal por pestañas
# ---------------------------------------------------------------------------
if st.session_state.tiff_info is None:
    st.info("Carga una imagen TIFF desde la barra lateral para comenzar.")
    st.stop()

info = st.session_state.tiff_info
names = band_names(info)

tab_visor, tab_indices, tab_cuant, tab_reporte = st.tabs(
    ["🖼️ Visor de imagen", "📊 Indices espectrales", "📐 Cuantificacion de areas", "📄 Reporte"]
)

# =========================================================================
# PESTAÑA 1: Visor
# =========================================================================
with tab_visor:
    st.subheader("Visor y compuesta RGB")
    c1, c2 = st.columns([3, 2])
    with c1:
        if len(names) >= 3:
            r_def = names[0]; g_def = names[1] if len(names) > 1 else names[0]
            b_def = names[2] if len(names) > 2 else names[0]
            colr, colg, colb = st.columns(3)
            rb = colr.selectbox("Rojo", names, index=names.index(r_def))
            gb = colg.selectbox("Verde", names, index=names.index(g_def))
            bb = colb.selectbox("Azul", names, index=names.index(b_def))
            try:
                rgb = build_rgb(info, rb, gb, bb)
                st.image(rgb, caption=f"Compuesta RGB: {rb}, {gb}, {bb}", use_container_width=True)
            except Exception as exc:
                st.error(f"No se pudo generar la composta: {exc}")
        else:
            st.warning("Se necesitan al menos 3 bandas para una composta RGB.")
    with c2:
        st.write("Detalle del archivo:")
        st.write(f"- Forma (shape): {info['shape']}")
        st.write(f"- Tipo de datos: {info['dtype']}")
        st.write(f"- Orden de ejes detectado: {info['axis_order']}")
        st.write(f"- Numero de bandas: {len(names)}")
        st.write("Bandas:", ", ".join(names))
        st.divider()
        st.write("Estadisticas por banda:")
        for label, arr in info["bands"]:
            st = summary_stats(arr)
            st.caption(f"**{label}**: medio {st['mean']:.3f}, min {st['min']:.3f}, "
                       f"max {st['max']:.3f}, std {st['std']:.3f}")

# =========================================================================
# PESTAÑA 2: Indices espectrales
# =========================================================================
with tab_indices:
    st.subheader("Calculo de indices espectrales")

    def get(bkey):
        return select_band(info, asg[bkey]) if bkey in asg else None

    colA, colB = st.columns(2)

    def calcular(nombre, funcion, requeridas, kwargs=None):
        falta = [r for r in requeridas if r not in asg]
        if falta:
            st.warning(f"Falta asignar banda(s): {', '.join(falta)}")
            return
        kwargs = kwargs or {}
        args = [get(r) for r in requeridas]
        try:
            arr = funcion(*args, **kwargs)
            st.session_state.results[nombre] = {
                "array": arr,
                "stats": summary_stats(arr),
                "bandas": requeridas,
            }
            st.success(f"{nombre} calculado correctamente.")
        except Exception as exc:
            st.error(f"Error calculando {nombre}: {exc}")

    with colA:
        st.button("NDVI — Vegetacion", use_container_width=True,
                  on_click=calcular, args=("NDVI", ndvi, ["nir", "red"]))
        st.button("NDWI — Agua (McFeeters)", use_container_width=True,
                  on_click=calcular, args=("NDWI", ndwi, ["green", "nir"]))
        st.button("MNDWI — Agua modificado", use_container_width=True,
                  on_click=calcular, args=("MNDWI", mndwi, ["green", "swir"]))
    with colB:
        st.button("NDBI — Suelos/construido", use_container_width=True,
                  on_click=calcular, args=("NDBI", ndbi, ["swir", "nir"]))
        st.button("SAVI — Vegetacion ajuste suelo", use_container_width=True,
                  on_click=calcular, args=("SAVI", savi, ["nir", "red"]))
        st.button("EVI — Vegetacion mejorado", use_container_width=True,
                  on_click=calcular, args=("EVI", evi, ["nir", "red", "blue"]))

    st.divider()
    st.subheader("Visualizacion del indice")
    if st.session_state.results:
        opcion = st.selectbox("Selecciona el indice a mostrar",
                              list(st.session_state.results.keys()))
        res = st.session_state.results[opcion]
        arr = res["array"]
        vmin, vmax = st.slider("Rango de color", -1.0, 1.0, (-1.0, 1.0), 0.1)
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        cmap_name = {"NDVI": "RdYlGn", "SAVI": "RdYlGn", "EVI": "RdYlGn",
                     "NDWI": "Blues", "MNDWI": "Blues", "NDBI": "YlOrBr"}.get(opcion, "viridis")
        fig, ax = plt.subplots(figsize=(7, 3.5))
        im = ax.imshow(arr, cmap=cmap_name, vmin=vmin, vmax=vmax)
        ax.set_title(opcion)
        ax.axis("off")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        st.pyplot(fig, use_container_width=True)

        st.subheader("Estadisticas")
        s = res["stats"]
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Pixeles validos", f"{s['count']:,}")
        sc2.metric("Medio", f"{s['mean']:.3f}")
        sc3.metric("Min", f"{s['min']:.3f}")
        sc4.metric("Max", f"{s['max']:.3f}")
    else:
        st.info("Calcula al menos un indice desde los botones de arriba.")

# =========================================================================
# PESTAÑA 3: Cuantificacion de areas
# =========================================================================
with tab_cuant:
    st.subheader("Cuantificacion de areas por cobertura")

    if not st.session_state.results:
        st.info("Calcula indices en la pestaña anterior para cuantificar areas.")
    else:
        ha_px = pixel_area_ha(st.session_state.get("resolution_m"))
        if ha_px:
            st.caption(f"Cada pixel representa {ha_px:.4f} ha.")

        # NDVI / vegetacion
        st.markdown("### Vegetacion (NDVI)")
        if "NDVI" in st.session_state.results:
            classes, total = classify_ndvi(st.session_state.results["NDVI"]["array"])
            rows = [[c["clase"], c["rango"], f'{c["pixeles"]:,}', f'{c["porcentaje"]:.2f}%'] for c in classes]
            st.table(rows)
            veg_dense = next(c for c in classes if c["clase"] == "Vegetacion densa / sana")
            veg_mod = next(c for c in classes if c["clase"] == "Vegetacion moderada")
            st.caption(f"Vegetacion funcional (moderada + densa): "
                       f"{(veg_mod['porcentaje'] + veg_dense['porcentaje']):.2f}% del area.")
        else:
            st.warning("Calcula NDVI para ver la clasificacion de vegetacion.")

        st.markdown("### Fuentes hidricas (NDWI o MNDWI)")
        agua_key = "MNDWI" if "MNDWI" in st.session_state.results else ("NDWI" if "NDWI" in st.session_state.results else None)
        if agua_key:
            cls_fn = classify_ndwi if agua_key == "NDWI" else classify_ndwi
            classes, total = cls_fn(st.session_state.results[agua_key]["array"])
            rows = [[c["clase"], c["rango"], f'{c["pixeles"]:,}', f'{c["porcentaje"]:.2f}%'] for c in classes]
            st.table(rows)
            agua = next((c for c in classes if "agua" in c["clase"].lower() or "hídrico" in c["clase"]), None)
            if agua:
                st.caption(f"Agua detectada: {agua['porcentaje']:.2f}% del area analizada.")
        else:
            st.warning("Calcula NDWI o MNDWI para ver fuentes hidricas.")

        st.markdown("### Suelos expuestos y areas construidas (NDBI)")
        if "NDBI" in st.session_state.results:
            classes, total = classify_ndbi(st.session_state.results["NDBI"]["array"])
            rows = [[c["clase"], c["rango"], f'{c["pixeles"]:,}', f'{c["porcentaje"]:.2f}%'] for c in classes]
            st.table(rows)
            suelo = next((c for c in classes if "expuesta" in c["clase"]), None)
            if suelo:
                st.caption(f"Area expuesta/construida: {suelo['porcentaje']:.2f}% del area.")
        else:
            st.warning("Calcula NDBI para ver suelos expuestos.")

        st.divider()
        st.markdown("### Clasificacion combinada (cobertura dominante)")
        ndvi_a = st.session_state.results.get("NDVI", {}).get("array")
        ndwi_key = "MNDWI" if "MNDWI" in st.session_state.results else ("NDWI" if "NDWI" in st.session_state.results else None)
        ndwi_a = st.session_state.results[ndwi_key]["array"] if ndwi_key else None
        ndbi_a = st.session_state.results.get("NDBI", {}).get("array")
        if ndvi_a is not None and (ndwi_a is not None or ndbi_a is not None):
            # rellena faltantes con nan para no romper coverage_map
            shape = ndvi_a.shape
            if ndwi_a is None:
                ndwi_a = np.full(shape, np.nan)
            if ndbi_a is None:
                ndbi_a = np.full(shape, np.nan)
            cov = coverage_map(ndvi_a, ndwi_a, ndbi_a)
            st.session_state.coverage = cov
            total = int(np.isfinite(cov).sum())
            filas = [
                ("Agua", int((cov == 1).sum()), f"{int((cov == 1).sum())/total*100:.2f}%"),
                ("Vegetacion", int((cov == 2).sum()), f"{int((cov == 2).sum())/total*100:.2f}%"),
                ("Suelo expuesto / construido", int((cov == 3).sum()), f"{int((cov == 3).sum())/total*100:.2f}%"),
            ]
            st.table(filas)
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(6, 2.6))
            show = np.where(cov > 0, cov, np.nan)
            ax.imshow(show, cmap="tab10", vmin=1, vmax=3)
            ax.set_title("Cobertura dominante por pixel")
            ax.axis("off")
            st.pyplot(fig, use_container_width=True)
        else:
            st.info("Se necesita NDVI y (NDWI/MNDWI o NDBI) para la clasificacion combinada.")

        # Descarga CSV
        st.divider()
        st.download_button(
            "Descargar estadisticas (CSV)",
            data="indice,min,max,medio,desvio\n" + "".join(
                f"{k},{v['stats']['min']:.4f},{v['stats']['max']:.4f},{v['stats']['mean']:.4f},{v['stats']['std']:.4f}\n"
                for k, v in st.session_state.results.items()
            ),
            file_name="indices_espectrales.csv",
            mime="text/csv",
        )

# =========================================================================
# PESTAÑA 4: Reporte
# =========================================================================
with tab_reporte:
    st.subheader("Generar reporte en PDF")
    st.write("El reporte incluye: resumen ejecutivo, mapa y estadisticas de cada indice, "
             "tablas de area por clases, clasificacion de cobertura y conclusiones.")

    if not st.session_state.results:
        st.info("No hay resultados para incluir en el reporte. Calcula al menos un indice.")
    else:
        default_resumen = (
            f"Se analizaron {st.session_state.tiff_info['shape']} pixeles. "
            f"Se calcularon {len(st.session_state.results)} indices espectrales. "
            "Consulte las secciones siguientes para el detalle de vegetacion, fuentes hidricas y suelos."
        )
        resumen = st.text_area("Resumen ejecutivo (personalizable)", value=default_resumen, height=100)
        concl_default = (
            "- Vegetacion: evaluar el porcentaje de area con NDVI >= 0.40 como cobertura vegetal funcional.\n"
            "- Fuentes hidricas: areas con NDWI/MNDWI >= 0.20 indican presencia de cuerpos de agua.\n"
            "- Suelos: NDBI >= 0.10 destaca areas expuestas o construidas.\n"
            "Se recomienda validar los umbrales con muestreo de campo antes de tomar decisiones de gestion."
        )
        conclusiones = st.text_area("Conclusiones y recomendaciones", value=concl_default, height=120)

        if st.button("Generar reporte PDF", type="primary", use_container_width=True):
            try:
                # Arma contexto para el PDF
                indice_tabla = []
                for k, v in st.session_state.results.items():
                    s = v["stats"]
                    estado = ""
                    if k in ("NDVI", "SAVI", "EVI"):
                        estado = "Vegetacion destacada" if s["mean"] > 0.3 else "Vegetacion limitada"
                    elif k in ("NDWI", "MNDWI"):
                        estado = "Agua significativa" if s["mean"] > 0.1 else "Poca agua detectada"
                    elif k == "NDBI":
                        estado = "Suelos expuestos notables" if s["mean"] > 0.05 else "Baja exposicion de suelo"
                    indice_tabla.append([k, f"{s['min']:.3f}", f"{s['max']:.3f}",
                                         f"{s['mean']:.3f}", f"{s['std']:.3f}", estado])

                context = {
                    "file_name": st.session_state.get("tiff_file_name", "TIFF cargado"),
                    "shape": str(st.session_state.tiff_info["shape"]),
                    "resolution_m": st.session_state.get("resolution_m"),
                    "resumen_texto": resumen,
                    "indice_tabla": indice_tabla,
                    "conclusiones": conclusiones.replace("- ", "• "),
                }
                for k in ("NDVI", "NDWI", "MNDWI", "NDBI", "SAVI", "EVI"):
                    if k in st.session_state.results:
                        context[f"res_{k}"] = st.session_state.results[k]
                if st.session_state.coverage is not None:
                    context["coverage"] = st.session_state.coverage

                out_path = os.path.join(tempfile.gettempdir(), "reporte_analisis_tif.pdf")
                import os, tempfile
                build_pdf_report(context, out_path)
                with open(out_path, "rb") as f:
                    st.download_button(
                        "Descargar reporte.pdf",
                        data=f.read(),
                        file_name="reporte_analisis_tif.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                st.success("Reporte generado correctamente.")
            except Exception as exc:
                st.error(f"No se pudo generar el reporte: {exc}")
