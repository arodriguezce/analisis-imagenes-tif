# Analisis de Imagenes TIFF - Indices Espectrales (GitHub Pages)

Sitio estatico (HTML/JS/CSS) que se ejecuta **100% en el navegador** y se publica con GitHub Pages. No requiere servidor Python.

## Que hace
- Carga imagenes TIFF multibanda (Landsat, Sentinel, dron, etc.) desde el navegador.
- Calcula indices espectrales: **NDVI, SAVI, EVI** (vegetacion), **NDWI, MNDWI** (fuentes hídricas/agua), **NDBI** (suelos expuestos / areas construidas).
- Visualiza mapas de calor, histogramas y compuesta RGB.
- Cuantifica areas en pixeles y porcentajes por clase de cobertura.
- Si se indica la resolucion espacial (m/pixel), convierte a **hectareas**.
- Genera un **reporte PDF** con mapas, cifras, tablas y conclusiones.

## Como usarlo localmente
Abre `index.html` directamente en el navegador, o sirvelo con cualquier servidor estatico:

```bash
python3 -m http.server 8080
# luego abre http://localhost:8080
```

## Publicacion en GitHub Pages
1. Sube la rama a GitHub.
2. En el repositorio: **Settings > Pages > Build and deployment > Source** = `arena/bdfca1c7-analisis-imagenes-tif` (o `main`), carpeta `/ (root)`.
3. El sitio queda disponible en `https://arodriguezce.github.io/analisis-imagenes-tif/`.

## Archivos
- `index.html` — aplicacion de una sola pagina (visores, indices, areas, reporte).
- `style.css` — estilos.
- `app.js` — logica: lectura de TIFF (geotiff.js), indices, clasificacion, graficos (Chart.js) y PDF (jsPDF).
- `app.py`, `utils.py`, `indices.py`, `reporte.py` — version original en Python/Streamlit (conservada como referencia).
