"""Cálculo de índices espectrales y clasificación de coberturas."""
from __future__ import annotations

import numpy as np


def _safe_div(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.full_like(num, np.nan, dtype=np.float64)
        mask = np.abs(den) > 1e-12
        out[mask] = num[mask] / den[mask]
    return out


def ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """Índice de Vegetación de Diferencia Normalizada."""
    return _safe_div(nir - red, nir + red)


def ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Índice de Agua de Diferencia Normalizada (McFeeters)."""
    return _safe_div(green - nir, green + nir)


def mndwi(green: np.ndarray, swir: np.ndarray) -> np.ndarray:
    """Índice Modificado de Agua de Diferencia Normalizada."""
    return _safe_div(green - swir, green + swir)


def ndbi(swir: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Índice de Edificaciones de Diferencia Normalizada (suelos desnudos/urbanos)."""
    return _safe_div(swir - nir, swir + nir)


def savi(nir: np.ndarray, red: np.ndarray, L: float = 0.5) -> np.ndarray:
    """Índice de Vegetación Ajustado por Suelo."""
    return (nir - red) / (nir + red + L) * (1 + L)


def evi(nir: np.ndarray, red: np.ndarray, blue: np.ndarray,
        C1: float = 6.0, C2: float = 7.5, L: float = 1.0, G: float = 2.5) -> np.ndarray:
    """Índice de Vegetación Mejorado."""
    return G * (nir - red) / (nir + C1 * red - C2 * blue + L)


# ---------------------------------------------------------------------------
# Clasificaciones de cobertura (rango -> etiqueta)
# ---------------------------------------------------------------------------

NDVI_CLASSES = [
    ("Agua / Sin vegetación", "< 0.00"),
    ("Suelo desnudo / muy baja", "0.00 – 0.20"),
    ("Vegetación baja / estrés", "0.20 – 0.40"),
    ("Vegetación moderada", "0.40 – 0.60"),
    ("Vegetación densa / sana", ">= 0.60"),
]

NDWI_CLASSES = [
    ("Sin agua / suelo seco", "< 0.00"),
    ("Humedad moderada", "0.00 – 0.20"),
    ("Cuerpo hídrico / agua", ">= 0.20"),
]

NDBI_CLASSES = [
    ("Suelo vegetado / agua", "< 0.00"),
    ("Suelo desnudo mixto", "0.00 – 0.10"),
    ("Área expuesta / construida", ">= 0.10"),
]


def _classify(arr: np.ndarray, classes: list[tuple[str, str, callable]]) -> tuple[list[dict], int]:
    total = int(np.isfinite(arr).sum())
    rows = []
    for name, rango, fn in classes:
        mask = fn(arr) & np.isfinite(arr)
        cnt = int(mask.sum())
        pct = (cnt / total * 100.0) if total else 0.0
        rows.append({"clase": name, "rango": rango, "pixeles": cnt, "porcentaje": pct})
    return rows, total


def classify_ndvi(arr: np.ndarray) -> tuple[list[dict], int]:
    rules = [
        ("Agua / Sin vegetación", "< 0.00", lambda a: a < 0),
        ("Suelo desnudo / muy baja", "0.00 – 0.20", lambda a: (a >= 0) & (a < 0.2)),
        ("Vegetación baja / estrés", "0.20 – 0.40", lambda a: (a >= 0.2) & (a < 0.4)),
        ("Vegetación moderada", "0.40 – 0.60", lambda a: (a >= 0.4) & (a < 0.6)),
        ("Vegetación densa / sana", ">= 0.60", lambda a: a >= 0.6),
    ]
    return _classify(arr, rules)


def classify_ndwi(arr: np.ndarray) -> tuple[list[dict], int]:
    rules = [
        ("Sin agua / suelo seco", "< 0.00", lambda a: a < 0),
        ("Humedad moderada", "0.00 – 0.20", lambda a: (a >= 0) & (a < 0.2)),
        ("Cuerpo hídrico / agua", ">= 0.20", lambda a: a >= 0.2),
    ]
    return _classify(arr, rules)


def classify_ndbi(arr: np.ndarray) -> tuple[list[dict], int]:
    rules = [
        ("Suelo vegetado / agua", "< 0.00", lambda a: a < 0),
        ("Suelo desnudo mixto", "0.00 – 0.10", lambda a: (a >= 0) & (a < 0.1)),
        ("Área expuesta / construida", ">= 0.10", lambda a: a >= 0.1),
    ]
    return _classify(arr, rules)


def coverage_map(ndvi_a: np.ndarray, ndwi_a: np.ndarray, ndbi_a: np.ndarray) -> np.ndarray:
    """Asigna una clase dominante por píxel: 0=Otro, 1=Agua, 2=Vegetación, 3=Suelo."""
    out = np.zeros_like(ndvi_a, dtype=np.int8)
    valid = np.isfinite(ndvi_a) | np.isfinite(ndwi_a) | np.isfinite(ndbi_a)
    agua = np.isfinite(ndwi_a) & (ndwi_a > 0.10)
    veg = np.isfinite(ndvi_a) & (ndvi_a > 0.25) & ~agua
    suelo = np.isfinite(ndbi_a) & (ndbi_a > 0.10) & ~agua & ~veg
    out[agua] = 1
    out[veg] = 2
    out[suelo] = 3
    out[~valid] = 0
    return out
