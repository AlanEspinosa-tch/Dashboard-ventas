"""
Textos del reporte: catálogo de bloques y persistencia (PARTE G).

Categorías:
  A · automático puro  → lo calcula el PDF, no aparece en el formulario.
  B · borrador editable → Python propone, dirección confirma o reescribe.
  C · manual puro       → SOLO el usuario. Si queda vacío, el bloque completo
                          se omite del PDF (ni rótulo ni barra de color).

Persistencia: comentarios.json, indexado por periodo 'YYYY-MM'.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import config as cfg

RUTA = Path(cfg.__file__).resolve().parent.parent / "comentarios.json"

# (id, etiqueta, categoría, límite, sección)
CATALOGO = [
    ("p1.titular", "Titular", "B", 72, "Página 1 · Ventas del mes"),
    ("p1.subtitulo", "Subtítulo", "B", 96, "Página 1 · Ventas del mes"),
    ("p1.lectura.1", "Lectura · Diésel", "B", 300, "Página 1 · Ventas del mes"),
    ("p1.lectura.2", "Lectura · Premium", "B", 300, "Página 1 · Ventas del mes"),
    ("p1.lectura.3", "Lectura · Regular", "B", 300, "Página 1 · Ventas del mes"),
    ("p1.lectura.4", "Lectura · Total", "B", 300, "Página 1 · Ventas del mes"),
    ("ventas_mes.analisis", "Análisis (debajo de la gráfica)", "C", 450,
     "Página 1 · Ventas del mes"),

    ("p2.titular", "Titular", "B", 72, "Página 2 · Desempeño por estación"),
    ("p2.subtitulo", "Subtítulo", "B", 96, "Página 2 · Desempeño por estación"),

    # Los tres van bajo la tabla IMPORTE POR ESTACIÓN, en ese orden.
    ("p2.causa.1", "Causa del crecimiento", "C", 450,
     "Página 3 · Importe por estación"),
    ("p2.causa.2", "Causa de la caída", "C", 450,
     "Página 3 · Importe por estación"),
    ("desempeno_estacion.conclusiones", "Análisis adicional", "C", 450,
     "Página 3 · Importe por estación"),

    ("p3.titular", "Titular", "B", 72, "Página 4 · Desempeño acumulado"),
    ("p3.subtitulo", "Subtítulo", "B", 96, "Página 4 · Desempeño acumulado"),
    ("p3.nota", "Nota de comparabilidad", "C", 180,
     "Página 4 · Desempeño acumulado"),
    ("acumulado.conclusiones", "Análisis (debajo de la gráfica trimestral)",
     "C", 450, "Página 4 · Desempeño acumulado"),

    ("p4.titular", "Titular", "B", 72, "Página 5 · Rentabilidad"),
    ("p4.subtitulo", "Subtítulo", "B", 96, "Página 5 · Rentabilidad"),
    # Manual: vacío = no se imprime y la tabla sube. Era borrador automático,
    # pero su texto citaba el "% de la variación" sobre el neto, que confunde
    # cuando las alzas y las bajas se cancelan entre sí.
    ("p4.nota", "Lectura de estaciones (arriba de la tabla)", "C", 220,
     "Página 6 · Margen por estación"),

    ("rentabilidad.analisis", "Análisis (debajo de la cascada de margen)", "C", 450,
     "Página 5 · Rentabilidad"),

    ("margen_estacion.analisis", "Análisis (debajo de alzas y caídas)",
     "C", 450, "Página 6 · Margen por estación"),

    ("com.interpretacion", "Interpretación del resultado", "C", 400,
     "Comentarios de dirección"),
    ("com.causas", "Causas conocidas", "C", 400, "Comentarios de dirección"),
    ("com.eventos", "Eventos extraordinarios", "C", 400, "Comentarios de dirección"),
    ("com.acciones", "Acciones tomadas", "C", 400, "Comentarios de dirección"),
    ("com.proximos", "Próximos pasos (+ responsable y fecha)", "C", 400,
     "Comentarios de dirección"),
    ("com.riesgos", "Riesgos identificados", "C", 400, "Comentarios de dirección"),
]

LIMITES = {b[0]: b[3] for b in CATALOGO}
CATEGORIA = {b[0]: b[2] for b in CATALOGO}
SECCIONES = []
for b in CATALOGO:
    if b[4] not in SECCIONES:
        SECCIONES.append(b[4])


def _clave(per) -> str:
    return str(per)


def cargar_todos() -> dict:
    if RUTA.exists():
        try:
            return json.loads(RUTA.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def cargar(per) -> dict:
    """{id_bloque: texto} guardado para ese periodo."""
    d = cargar_todos().get(_clave(per), {})
    return {k: v for k, v in d.items() if not k.startswith("_")}


def guardar(per, textos: dict, elaboro: str = "") -> None:
    todos = cargar_todos()
    limpio = {k: str(v).strip() for k, v in textos.items() if str(v).strip()}
    limpio["_meta"] = {"elaboro": elaboro,
                       "actualizado": datetime.now().isoformat(timespec="seconds")}
    todos[_clave(per)] = limpio
    RUTA.write_text(json.dumps(todos, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def acciones_de(per, estaciones) -> list[tuple[str, str, int]]:
    """Bloques dinámicos de acción por estación (categoría C)."""
    return [(f"p5.accion.{e}", f"Acción para {e}", 150) for e in estaciones]


def seguimiento_mes_anterior(per) -> str:
    """Trae 'Próximos pasos' del periodo previo como seguimiento."""
    prev = cargar(per - 1)
    txt = prev.get("com.proximos", "").strip()
    return f"Seguimiento: {txt}" if txt else ""
