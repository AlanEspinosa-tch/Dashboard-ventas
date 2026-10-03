"""
treher_analytics — herramienta de análisis de ventas para el grupo gasolinero.

Uso típico:
    from treher_analytics import data, metrics, model, viz
    bd = data.cargar_bd()
    metrics.ranking_estaciones(bd)
"""

from . import (borradores, comentarios, config, data, ejecutivo,  # noqa: F401
               margenes, metrics, model, reporte_pdf, tablas, viz)

__all__ = ["borradores", "comentarios", "config", "data", "ejecutivo",
           "margenes", "metrics", "model", "reporte_pdf", "tablas", "viz"]
__version__ = "0.1.0"
