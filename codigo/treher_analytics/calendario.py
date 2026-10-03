"""
Calendario mexicano: quincenas (días de pago) y días festivos.

Genera marcadores por fecha que alimentan el modelo y el pronóstico:
  - Quincena: ventana alrededor del día de pago (15 y último día del mes),
    porque la venta de combustible repunta los días posteriores al pago.
  - Festivo: festivos oficiales (descanso obligatorio) + culturales con
    impacto comercial (Madres, San Valentín, Muertos, Semana Santa, etc.).

Todo es por REGLA (no fechas fijas de un solo año), así sirve para 2023-2026
y para fechas futuras del pronóstico. Los festivos oficiales se calculan en su
día observado (lunes) según la Ley Federal del Trabajo.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

import pandas as pd


def _domingo_pascua(anio: int) -> date:
    """Fecha del Domingo de Pascua (algoritmo de Gauss/Meeus)."""
    a = anio % 19
    b, c = divmod(anio, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(anio, mes, dia)


def _lunes_n(anio: int, mes: int, n: int) -> date:
    """N-ésimo lunes del mes (n=1 primer lunes, etc.)."""
    d = date(anio, mes, 1)
    offset = (0 - d.weekday()) % 7          # 0 = lunes
    return d + timedelta(days=offset + 7 * (n - 1))


def festivos_anio(anio: int) -> dict[date, str]:
    """Diccionario fecha -> nombre del festivo para un año."""
    pascua = _domingo_pascua(anio)
    fest = {
        # --- Oficiales (descanso obligatorio), en su día observado ---
        date(anio, 1, 1): "Año Nuevo",
        _lunes_n(anio, 2, 1): "Día de la Constitución",
        _lunes_n(anio, 3, 3): "Natalicio de Benito Juárez",
        date(anio, 5, 1): "Día del Trabajo",
        date(anio, 9, 16): "Independencia",
        _lunes_n(anio, 11, 3): "Revolución Mexicana",
        date(anio, 12, 25): "Navidad",
        # --- Culturales / comerciales (impacto en ventas) ---
        date(anio, 2, 14): "San Valentín",
        date(anio, 5, 5): "Batalla de Puebla",
        date(anio, 5, 10): "Día de las Madres",
        date(anio, 5, 15): "Día del Maestro",
        date(anio, 11, 2): "Día de Muertos",
        date(anio, 12, 12): "Virgen de Guadalupe",
        # --- Semana Santa (Jueves y Viernes Santo) ---
        pascua - timedelta(days=3): "Jueves Santo",
        pascua - timedelta(days=2): "Viernes Santo",
    }
    return fest


def _dias_pago(anios) -> set[date]:
    dias = set()
    for y in anios:
        for m in range(1, 13):
            dias.add(date(y, m, 15))
            dias.add(date(y, m, calendar.monthrange(y, m)[1]))  # último día
    return dias


def marcar(fechas: pd.Series, ventana_pago: int = 2) -> pd.DataFrame:
    """
    Devuelve un DataFrame (mismo índice que `fechas`) con columnas:
      - Quincena: True el día de pago y los `ventana_pago` días siguientes.
      - Festivo: True si la fecha es festivo (oficial o cultural).
      - Festivo_nombre: nombre del festivo ("" si no aplica).
    """
    fechas = pd.to_datetime(fechas)
    anios = range(fechas.dt.year.min(), fechas.dt.year.max() + 2)  # +1 para futuro

    pago = _dias_pago(anios)
    pago_win = {d + timedelta(days=k) for d in pago for k in range(ventana_pago + 1)}

    festivos = {}
    for y in anios:
        festivos.update(festivos_anio(y))

    d = fechas.dt.date
    out = pd.DataFrame(index=fechas.index)
    out["Quincena"] = d.isin(pago_win).values
    out["Festivo"] = d.isin(set(festivos)).values
    out["Festivo_nombre"] = [festivos.get(x, "") for x in d]
    return out
