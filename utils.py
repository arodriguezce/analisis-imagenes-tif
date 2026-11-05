"""Utilidades para lectura de TIFF, visualización y estadísticas básicas."""
from __future__ import annotations

import numpy as np
import tifffile


def load_tiff(uploaded_file, axis_order: str | None = None) -> dict:
    """Lee un archivo TIFF (subido vía Streamlit o ruta) y devuelve metadatos.

    `axis_order` permite forzar "BHW" (bandas, alto, ancho) o "HWB" (alto, ancho, bandas).
    """
    data = np.asarray(tifffile.imread(uploaded_file))
    info = {
        "shape": tuple(data.shape),
        "dtype": str(data.dtype),
        "ndim": int(data.ndim),
        "bands": [],
        "axis_order": None,
        "array": data,
    }

    if data.ndim == 2:
        info["bands"] = [("Banda 1", data.astype(np.float64))]
        info["axis_order"] = "single"
    elif data.ndim == 3:
        b, h, w = data.shape
        if axis_order in ("BHW", "HWB"):
            order = axis_order
        else:
            # Heurística: si la primera dimensión es la más pequeña y parece conteo de bandas -> (B, H, W)
            if b <= h and b <= w and 1 <= b <= 16:
                order = "BHW"
            else:
                order = "HWB"
        info["axis_order"] = order
        if order == "BHW":
            for i in range(b):
                info["bands"].append((f"Banda {i + 1}", data[i].astype(np.float64)))
        else:
            for i in range(data.shape[2]):
                info["bands"].append((f"Banda {i + 1}", data[:, :, i].astype(np.float64)))
    else:
        raise ValueError(f"Formato TIFF no soportado: {data.shape}")
    return info


def band_names(info: dict) -> list[str]:
    return [label for label, _ in info["bands"]]


def select_band(info: dict, name: str) -> np.ndarray:
    for label, arr in info["bands"]:
        if label == name:
            return arr
    raise ValueError(f"Banda '{name}' no encontrada")


def normalize_for_display(arr: np.ndarray, p_low: float = 2.0, p_high: float = 98.0) -> np.ndarray:
    """Estira un array al rango [0, 1] usando percentiles (para visualización RGB)."""
    a = np.asarray(arr, dtype=np.float64)
    finite = a[np.isfinite(a)]
    if finite.size == 0:
        return np.zeros_like(a, dtype=np.float32)
    lo, hi = np.percentile(finite, [p_low, p_high])
    if hi - lo < 1e-12:
        return np.zeros_like(a, dtype=np.float32)
    out = np.clip((a - lo) / (hi - lo), 0.0, 1.0)
    return out.astype(np.float32)


def build_rgb(info: dict, red: str, green: str, blue: str) -> np.ndarray:
    """Construye una imagen RGB a partir de tres bandas del TIFF."""
    r = select_band(info, red)
    g = select_band(info, green)
    b = select_band(info, blue)
    rgb = np.dstack([
        normalize_for_display(r),
        normalize_for_display(g),
        normalize_for_display(b),
    ])
    return rgb


def summary_stats(arr: np.ndarray) -> dict:
    a = np.asarray(arr, dtype=np.float64)
    fin = a[np.isfinite(a)]
    if fin.size == 0:
        return {"mean": np.nan, "std": np.nan, "min": np.nan, "max": np.nan,
                "median": np.nan, "count": 0}
    return {
        "mean": float(fin.mean()),
        "std": float(fin.std()),
        "min": float(fin.min()),
        "max": float(fin.max()),
        "median": float(np.median(fin)),
        "count": int(fin.size),
    }


def pixel_area_ha(resolution_m: float | None) -> float | None:
    """Hectáreas que representa un píxel dado la resolución en metros/píxel."""
    if resolution_m is None:
        return None
    return (resolution_m ** 2) / 10_000.0
