# Dashboard de análisis de ventas

Proyecto de análisis y automatización de reportes para una operación de estaciones de servicio.

## Objetivo

Construir una herramienta que permita analizar volumen, ventas y márgenes mediante indicadores consistentes y reutilizables.

El proyecto combina:

- procesamiento de datos en Python;
- dashboard interactivo con Streamlit;
- generación automatizada de reportes;
- análisis puntuales mediante notebooks;
- Power BI para visualización.

## Diseño analítico

Una parte importante del proyecto fue definir las reglas para que los indicadores fueran comparables:

- Los indicadores de volumen se expresan como litros por día para evitar mezclar el efecto del calendario con el desempeño.
- Los días sin operación se tratan como datos no operativos y no como ventas iguales a cero.
- Las comparaciones entre periodos consideran únicamente las estaciones disponibles en ambos periodos.
- La lógica de cálculo se concentra en un módulo común para evitar que el dashboard y los reportes implementen fórmulas distintas.

## Mi contribución

Definí la estructura analítica, las reglas de negocio, las métricas y la arquitectura general del proyecto. La implementación de parte del código Python, la interfaz y la generación de documentos se realizó con apoyo de herramientas de Inteligencia Artificial.

## Estructura

```
codigo/       Lógica de procesamiento y dashboard
analisis/     Análisis puntuales
informes/     Ejemplos de reportes
```

> Los datos operativos originales de la empresa no forman parte de este repositorio público. Los archivos de demostración deberán utilizar datos anonimizados o sintéticos.

## Tecnologías

Python · Pandas · Streamlit · Power BI · Excel
