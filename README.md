# Analisis de Imagenes TIFF - Indices Espectrales

Aplicacion interactiva (Streamlit) para cargar imagenes TIFF multibanda, cuantificar
indices espectrales, medir areas de cobertura y generar un reporte en PDF.

## Indices implementados
- **NDVI** — vegetacion: `(NIR - Red) / (NIR + Red)`
- **SAVI** — vegetacion ajustada al suelo
- **EVI** — vegetacion mejorado (necesita banda azul)
- **NDWI / MNDWI** — fuentes hidricas (agua)
- **NDBI** — suelos expuestos / areas construidas

## Requisitos
Python 3.9+ y las dependencias de `requirements.txt`.

## Instalacion y ejecucion

```bash
pip install -r requirements.txt
streamlit run app.py
```

Luego abre la URL que muestre Streamlit (por defecto `http://localhost:8501`).

## Flujo de uso
1. Carga un TIFF multibanda (Landsat, Sentinel, dron, etc.) desde la barra lateral.
   Si no tienes uno, usa el boton de imagen de demostracion.
2. Asigna las bandas a sus roles: Rojo, Verde, NIR, SWIR y Azul.
3. En la pestaña **Indices espectrales**, calcula los indices que necesites.
4. En **Cuantificacion de areas**, consulta el porcentaje de pixeles por clase
   (vegetacion, agua, suelo expuesto) y, si indicas la resolucion espacial,
   el area en hectareas.
5. En **Reporte**, genera un PDF con mapas, cifras, tablas y conclusiones.

## Notas
- Los umbrales de clasificacion son referenciales; validalos con datos de campo.
- Si el TIFF tiene un orden de ejes inesperado, la app intenta detectarlo
  automaticamente (Bandas, Alto, Ancho vs Alto, Ancho, Bandas).
