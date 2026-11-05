"""Generación del reporte en PDF con fpdf2."""
from __future__ import annotations

import os
import tempfile
import datetime
from typing import Dict, Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from fpdf import FPDF

CMAPS = {"NDVI": "RdYlGn", "NDWI": "Blues", "MNDWI": "Blues", "NDBI": "YlOrBr", "SAVI": "RdYlGn", "EVI": "RdYlGn"}


def _sanitize(text: str) -> str:
    """Reemplaza caracteres fuera de latin-1 no soportados por la fuente base Helvetica."""
    return (str(text)
            .replace("\u2013", "-")   # –
            .replace("\u2014", "-")   # —
            .replace("\u2212", "-")   # −
            .replace("\u2022", "-")   # •
            .replace("\u2265", ">=")  # ≥
            .replace("\u2264", "<=")  # ≤
            .replace("\u2192", "->")  # →
            .replace("\u2026", "...") # …
            )


class PDF(FPDF):
    def cell(self, w, h=0, text="", *args, **kwargs):
        return super().cell(w, h, _sanitize(text), *args, **kwargs)

    def multi_cell(self, w, h, text, *args, **kwargs):
        return super().multi_cell(w, h, _sanitize(text), *args, **kwargs)

    def write(self, h, text, *args, **kwargs):
        return super().write(h, _sanitize(text), *args, **kwargs)

    def header(self):
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(34, 100, 60)
        self.cell(0, 10, "Reporte de Analisis Espectral - Imagen TIFF", new_x="LMARGIN", new_y="NEXT", align="C")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 6, "Generado con la aplicacion de cuantificacion de indices espectrales",
                  new_x="LMARGIN", new_y="NEXT", align="C")
        self.ln(4)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 8, f"Pagina {self.page_no()} - {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}",
                  new_x="LMARGIN", new_y="NEXT", align="C")

VMIN = {"NDVI": -1, "NDWI": -1, "MNDWI": -1, "NDBI": -1, "SAVI": -1, "EVI": -1}
VMAX = {"NDVI": 1, "NDWI": 1, "MNDWI": 1, "NDBI": 1, "SAVI": 1, "EVI": 1}

CLASS_TITLES = {
    "NDVI": "Vegetación (NDVI / SAVI)",
    "NDWI": "Fuentes hídricas (NDWI / MNDWI)",
    "NDBI": "Suelos expuestos y áreas construidas (NDBI)",
}


def _save_index_figure(arr: np.ndarray, name: str) -> str:
    fig, ax = plt.subplots(figsize=(6.5, 3.6), dpi=150)
    vmin, vmax = VMIN.get(name, -1), VMAX.get(name, 1)
    im = ax.imshow(arr, cmap=CMAPS.get(name, "viridis"), vmin=vmin, vmax=vmax)
    ax.set_title(f"Mapa de {name}", fontsize=11)
    ax.axis("off")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(name, fontsize=9)
    fig.tight_layout()
    path = os.path.join(tempfile.gettempdir(), f"rep_{name}.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _save_coverage_figure(cov: np.ndarray) -> str:
    colors = {0: "#cccccc", 1: "#4a90e2", 2: "#7ed321", 3: "#e0a13b"}
    labels = {0: "Otro / sin datos", 1: "Agua", 2: "Vegetación", 3: "Suelo expuesto / construido"}
    fig, ax = plt.subplots(figsize=(6.5, 3.6), dpi=150)
    show = np.where(cov > 0, cov, np.nan)
    im = ax.imshow(show, cmap="tab10", vmin=1, vmax=3)
    ax.set_title("Clasificación de cobertura combinada", fontsize=11)
    ax.axis("off")
    handles = [plt.Line2D([0], [0], marker="s", color="w", markerfacecolor=colors[i],
                          markersize=10, label=labels[i]) for i in range(1, 4)]
    ax.legend(handles=handles, loc="lower left", fontsize=8, framealpha=0.9)
    fig.tight_layout()
    path = os.path.join(tempfile.gettempdir(), "rep_cobertura.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _hist_png(arr: np.ndarray, name: str) -> str:
    fig, ax = plt.subplots(figsize=(5.6, 2.6), dpi=150)
    fin = arr[np.isfinite(arr)]
    ax.hist(fin, bins=40, color="#4a90e2", edgecolor="white")
    ax.set_title(f"Histograma {name}", fontsize=10)
    ax.set_xlabel(name, fontsize=8)
    ax.set_ylabel("Px", fontsize=8)
    ax.tick_params(labelsize=7)
    fig.tight_layout()
    path = os.path.join(tempfile.gettempdir(), f"rep_hist_{name}.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def build_pdf_report(context: Dict[str, Any], output_path: str) -> str:
    """Construye el PDF del reporte a partir del contexto de la aplicación."""
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margin(15)
    ew = pdf.w - 2 * pdf.l_margin  # ancho efectivo para celdas de texto

    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    # ---------- Portada / resumen ----------
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(34, 100, 60)
    pdf.multi_cell(ew, 10, "Informe de Analisis de Imagen TIFF")
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(80, 80, 80)
    pdf.multi_cell(ew, 7, f"Fecha de generacion: {now}")
    pdf.multi_cell(ew, 7, f"Archivo analizado: {context.get('file_name', '-')}")
    pdf.multi_cell(ew, 7, f"Dimensiones: {context.get('shape', '-')}")
    res = context.get("resolution_m")
    pdf.multi_cell(ew, 7, f"Resolucion espacial: {res} m/pixel" if res else "Resolucion espacial: no especificada")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(34, 100, 60)
    pdf.cell(0, 10, "Resumen ejecutivo", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(60, 60, 60)
    resumen = context.get("resumen_texto", "Sin resumen disponible.")
    pdf.multi_cell(ew, 7, resumen)
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Indices espectrales calculados", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    tabla = context.get("indice_tabla", [])
    if tabla:
        col_w = [34, 19, 19, 19, 19, 28]
        headers = ["Indice", "Min", "Max", "Medio", "Desv.", "Estado general"]
        pdf.set_fill_color(34, 100, 60)
        pdf.set_text_color(255, 255, 255)
        for w, h in zip(col_w, headers):
            pdf.cell(w, 7, h, border=1, fill=True, align="C")
        pdf.ln()
        pdf.set_text_color(60, 60, 60)
        for row in tabla:
            for w, val in zip(col_w, row):
                pdf.cell(w, 6, str(val), border=1, align="C")
            pdf.ln()
    pdf.ln(3)

    # ---------- Secciones por indice ----------
    for name in ("NDVI", "NDWI", "MNDWI", "NDBI", "SAVI", "EVI"):
        res = context.get(f"res_{name}")
        if not res:
            continue
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(34, 100, 60)
        pdf.cell(0, 10, CLASS_TITLES.get(name, name), new_x="LMARGIN", new_y="NEXT")

        fig_path = _save_index_figure(res["array"], name)
        hist_path = _hist_png(res["array"], name)
        pdf.image(fig_path, x=60, w=90)
        pdf.image(hist_path, x=115, w=75)
        pdf.ln(2)

        stats = res["stats"]
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(60, 60, 60)
        pdf.multi_cell(ew, 6,
                       f"Validos: {stats['count']} pixeles | Medio: {stats['mean']:.3f} | "
                       f"Min: {stats['min']:.3f} | Max: {stats['max']:.3f} | "
                       f"Desv. est.: {stats['std']:.3f} | Mediana: {stats['median']:.3f}")
        pdf.ln(1)

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, "Distribucion por clases", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        cw = [55, 30, 25, 25]
        pdf.set_fill_color(34, 100, 60)
        pdf.set_text_color(255, 255, 255)
        for w, h in zip(cw, ["Clase", "Rango", "Pixeles", "% Area"]):
            pdf.cell(w, 7, h, border=1, fill=True, align="C")
        pdf.ln()
        pdf.set_text_color(60, 60, 60)
        for r in res["classes"]:
            for w, val in zip(cw, [r["clase"], r["rango"], f'{r["pixeles"]:,}', f'{r["porcentaje"]:.2f}']):
                pdf.cell(w, 6, str(val), border=1, align="C")
            pdf.ln()
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(ew, 6, res.get("interpretacion", ""))

    # ---------- Cobertura combinada ----------
    cov = context.get("coverage")
    if cov is not None:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(34, 100, 60)
        pdf.cell(0, 10, "Clasificacion de cobertura del terreno", new_x="LMARGIN", new_y="NEXT")
        cov_path = _save_coverage_figure(cov)
        pdf.image(cov_path, x=60, w=90)
        pdf.ln(2)
        total = int(np.isfinite(cov).sum())
        for val, lbl in [(1, "Agua"), (2, "Vegetacion"), (3, "Suelo expuesto / construido")]:
            cnt = int((cov == val).sum())
            pct = cnt / total * 100 if total else 0
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(ew, 6, f"{lbl}: {cnt:,} pixeles ({pct:.2f}% del area analizada)")
        if res := context.get("resolution_m"):
            ha = (res ** 2) / 10_000.0
            pdf.ln(1)
            for val, lbl in [(1, "Agua"), (2, "Vegetacion"), (3, "Suelo expuesto / construido")]:
                cnt = int((cov == val).sum())
                pdf.multi_cell(ew, 6, f"Area aproximada {lbl}: {cnt * ha:.2f} ha")

    # ---------- Conclusiones ----------
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(34, 100, 60)
    pdf.cell(0, 10, "Conclusiones y recomendaciones", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(60, 60, 60)
    conclusiones = context.get("conclusiones", "-")
    pdf.multi_cell(ew, 7, conclusiones)
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(140, 140, 140)
    pdf.multi_cell(ew, 5, "Metodologia: indices espectrales calculados a partir de bandas de reflejo satelital "
                         "(NDVI, NDWI, MNDWI, NDBI, SAVI, EVI). Las areas se estiman en pixeles y, si se "
                         "proporciona la resolucion espacial, en hectareas. Los umbrales de clasificacion son "
                         "referenciales y deben validarse con datos de campo.")

    pdf.output(output_path)
    return output_path
