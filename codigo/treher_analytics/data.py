"""
Carga y saneamiento de la base.

Aquí se resuelve el problema central: distinguir un día CERRADO/sin dato
(no debe contar como venta de 0) de un día operado con venta real.

Reglas:
  - Los ceros y errores ya vienen como NaN en BD_Limpia. Un NaN en litros
    significa "ese producto no operó / no hay dato ese día".
  - Un día se considera CERRADO para la estación si TODOS sus productos
    están en NaN. Si la estación operó pero un producto fue 0, eso es un
    cero legítimo y NO se borra.
  - Las fechas duplicadas se colapsan (se conserva la primera).
  - Nunca se imputa volumen en días cerrados: imputar inflaría los totales.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import calendario
from . import config as cfg


# ----------------------------------------------------------------------
# CARGA
# ----------------------------------------------------------------------
def cargar_bd(ruta: Path | str | None = None, hoja: str = cfg.HOJA_BD) -> pd.DataFrame:
    """
    Lee la hoja BD de BD_Limpia.xlsx y devuelve un DataFrame saneado.

    Si el archivo está abierto en Excel (bloqueado en Windows), lo copia a
    un temporal y lee la copia, para no fallar por el lock.
    """
    ruta = Path(ruta) if ruta else cfg.RUTA_BD

    try:
        bd = pd.read_excel(ruta, sheet_name=hoja, engine="openpyxl")
    except PermissionError:
        # Archivo abierto en Excel -> trabajar sobre una copia temporal.
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp_path = tmp.name
        shutil.copy2(ruta, tmp_path)
        try:
            bd = pd.read_excel(tmp_path, sheet_name=hoja, engine="openpyxl")
        finally:
            try:                                 # limpieza best-effort
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:
                pass

    return sanear(bd)


# ----------------------------------------------------------------------
# SANEAMIENTO
# ----------------------------------------------------------------------
def sanear(bd: pd.DataFrame) -> pd.DataFrame:
    """Normaliza tipos, limpia encabezados, deduplica y marca cierres."""
    bd = bd.copy()
    bd.columns = [c.strip() for c in bd.columns]  # 'Contador ' -> 'Contador'

    bd[cfg.COL_FECHA] = pd.to_datetime(bd[cfg.COL_FECHA], errors="coerce")
    bd = bd.dropna(subset=[cfg.COL_FECHA, cfg.COL_ESTACION])

    # (V01) Normalizar nombre de estación (quita "TREHER T " con espacio, etc.).
    bd[cfg.COL_ESTACION] = bd[cfg.COL_ESTACION].astype(str).str.strip().str.upper()

    # (V08) Descartar fechas FUTURAS (errores de captura que anclan mal los
    # cálculos "recientes" a un mes vacío del futuro).
    hoy = pd.Timestamp.today().normalize()
    bd = bd[bd[cfg.COL_FECHA] <= hoy]

    # Por si quedara algún cero/string de error sin convertir en la fuente.
    cols_num = cfg.COLS_LTS + cfg.COLS_PRECIO
    bd[cols_num] = bd[cols_num].replace(
        [0, "", " ", "#N/A", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?"], np.nan
    )
    bd[cols_num] = bd[cols_num].apply(pd.to_numeric, errors="coerce")

    # (A) Descartar errores de captura FÍSICAMENTE IMPOSIBLES -> NaN.
    # No toca picos reales; solo lo que no puede ser cierto.
    bd = _descartar_errores_imposibles(bd)

    # Deduplicar fechas repetidas por estación (AURORA, TEOLOYUCAN, etc.).
    bd = bd.sort_values([cfg.COL_ESTACION, cfg.COL_FECHA])
    n_dups = bd.duplicated(subset=[cfg.COL_ESTACION, cfg.COL_FECHA]).sum()
    if n_dups:
        bd = bd.drop_duplicates(
            subset=[cfg.COL_ESTACION, cfg.COL_FECHA], keep="first"
        )

    # Marca de operación: True si la estación operó ese día (algún litro real).
    bd["Operó"] = bd[cfg.COLS_LTS].notna().any(axis=1)

    # Productos operados ese día (0 a 3): útil para distinguir cierre parcial.
    bd["Productos_operados"] = bd[cfg.COLS_LTS].notna().sum(axis=1)

    # Recalcular totales SOLO con lo realmente operado (NaN no suma como 0
    # gracias a min_count=1: si no hubo nada, el total queda NaN, no 0).
    bd[cfg.COL_TOTAL_LTS] = bd[cfg.COLS_LTS].sum(axis=1, min_count=1)

    importes = pd.DataFrame(index=bd.index)
    for prod in cfg.PRODUCTOS:
        importes[prod] = bd[cfg.LTS[prod]] * bd[cfg.PRECIO[prod]]
    bd[cfg.COL_TOTAL_VENTA] = importes.sum(axis=1, min_count=1)

    # Variables de calendario derivadas (no dependemos de las de Excel).
    bd[cfg.COL_ANIO] = bd[cfg.COL_FECHA].dt.year
    bd[cfg.COL_MES] = bd[cfg.COL_FECHA].dt.month
    bd["Dia_semana"] = bd[cfg.COL_FECHA].dt.weekday
    bd["Trimestre"] = bd[cfg.COL_FECHA].dt.quarter
    bd["Dia_año"] = bd[cfg.COL_FECHA].dt.dayofyear

    # Marcadores de calendario (quincena y festivos) para modelo/pronóstico.
    cal = calendario.marcar(bd[cfg.COL_FECHA])
    bd["Quincena"] = cal["Quincena"].values
    bd["Festivo"] = cal["Festivo"].values

    return bd.reset_index(drop=True)


# ----------------------------------------------------------------------
# (A) FILTRO DE ERRORES DE CAPTURA IMPOSIBLES
# ----------------------------------------------------------------------
def _descartar_errores_imposibles(bd: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte a NaN los valores que NO pueden ser reales:
      - Precios fuera de la banda plausible (config.PRECIO_PLAUSIBLE).
      - Volúmenes negativos.
      - Volúmenes por encima del techo absoluto (config.VOL_MAX_PLAUSIBLE) —
        atrapa volcados/saldos de apertura como el del 2021-03-17.
      - Volúmenes que superan FACTOR_VOL_OUTLIER veces la mediana de su
        propia estación-producto (error de dígito).
    Solo elimina basura evidente; los picos reales se conservan.
    """
    bd = bd.copy()
    pmin, pmax = cfg.PRECIO_PLAUSIBLE

    # Precios imposibles -> NaN
    for col in cfg.COLS_PRECIO:
        fuera = bd[col].notna() & ((bd[col] < pmin) | (bd[col] > pmax))
        bd.loc[fuera, col] = np.nan

    # Volúmenes negativos, sobre el techo absoluto, o desproporcionados -> NaN
    for col in cfg.COLS_LTS:
        bd.loc[bd[col] < 0, col] = np.nan
        bd.loc[bd[col] > cfg.VOL_MAX_PLAUSIBLE, col] = np.nan
        med = bd.groupby(cfg.COL_ESTACION)[col].transform("median")
        gigante = bd[col].notna() & (bd[col] > cfg.FACTOR_VOL_OUTLIER * med)
        bd.loc[gigante, col] = np.nan

    return bd


def reporte_outliers(ruta=None, hoja: str = cfg.HOJA_BD) -> pd.DataFrame:
    """
    Muestra QUÉ se descartó por el filtro (A), para auditoría. Compara los
    datos crudos contra los saneados y lista los valores eliminados.
    """
    ruta = ruta or cfg.RUTA_BD
    try:
        crudo = pd.read_excel(ruta, sheet_name=hoja, engine="openpyxl")
    except PermissionError:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp_path = tmp.name
        shutil.copy2(ruta, tmp_path)
        try:
            crudo = pd.read_excel(tmp_path, sheet_name=hoja, engine="openpyxl")
        finally:
            try:                                 # limpieza best-effort
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:
                pass
    crudo.columns = [c.strip() for c in crudo.columns]
    crudo[cfg.COL_FECHA] = pd.to_datetime(crudo[cfg.COL_FECHA], errors="coerce")

    limpio = sanear(crudo)
    idx = [cfg.COL_ESTACION, cfg.COL_FECHA]
    crudo_i = crudo.set_index(idx)
    limpio_i = limpio.set_index(idx)

    filas = []
    for col in cfg.COLS_PRECIO + cfg.COLS_LTS:
        if col not in crudo_i:
            continue
        original = pd.to_numeric(crudo_i[col], errors="coerce")
        nuevo = limpio_i[col].reindex(crudo_i.index)
        descartado = original.notna() & nuevo.isna() & (original != 0)
        for (est, fecha), val in original[descartado].items():
            filas.append({"Estación": est, "Fecha": fecha,
                          "Columna": col, "Valor_descartado": val})
    return pd.DataFrame(filas)


# ----------------------------------------------------------------------
# DIAGNÓSTICO DE COBERTURA / CIERRES
# ----------------------------------------------------------------------
def resumen_estaciones(bd: pd.DataFrame) -> pd.DataFrame:
    """
    Una fila por estación con su historia, días operados y cierres.
    Sirve para saber de un vistazo qué estación es comparable.
    """
    filas = []
    for est, g in bd.groupby(cfg.COL_ESTACION):
        fmin, fmax = g[cfg.COL_FECHA].min(), g[cfg.COL_FECHA].max()
        dias_cal = (fmax - fmin).days + 1
        dias_op = int(g["Operó"].sum())
        filas.append({
            cfg.COL_ESTACION: est,
            "Inicio": fmin.date(),
            "Fin": fmax.date(),
            "Días_calendario": dias_cal,
            "Días_operados": dias_op,
            "Días_cerrados": dias_cal - dias_op,
            "% operación": round(100 * dias_op / dias_cal, 1) if dias_cal else 0,
            "Historia_suficiente": dias_op >= cfg.MIN_DIAS_HISTORIA,
        })
    return (
        pd.DataFrame(filas)
        .sort_values("Días_operados", ascending=False)
        .reset_index(drop=True)
    )


def estaciones_activas_por_fecha(bd: pd.DataFrame) -> pd.DataFrame:
    """
    Conteo de estaciones operando cada día. Clave para interpretar el
    consolidado: una caída del total puede ser por menos estaciones
    abiertas, no por menos demanda.
    """
    return (
        bd[bd["Operó"]]
        .groupby(cfg.COL_FECHA)[cfg.COL_ESTACION]
        .nunique()
        .rename("Estaciones_activas")
        .reset_index()
    )


def estaciones_comparables(bd: pd.DataFrame) -> list[str]:
    """Estaciones con historia suficiente para modelar/comparar."""
    r = resumen_estaciones(bd)
    return r.loc[r["Historia_suficiente"], cfg.COL_ESTACION].tolist()
