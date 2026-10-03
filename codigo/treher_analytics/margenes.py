"""
Análisis de márgenes (rentabilidad), fuente: MARGENES..xlsx / hoja "Concentrado".

Es una base INDEPENDIENTE de BD_Limpia:
  - Cobertura 2025-01 → 2026-05 (más corta), 12 estaciones (sin TREHER LL).
  - Sus litros NO coinciden con BD_Limpia, así que no se mezcla: el margen
    se calcula con los propios datos de este archivo.

Verdad de referencia: las columnas MB (margen bruto $ por producto) y
'Total $' (margen bruto total del día). El margen por litro se RECALCULA
como MB ÷ litros para no depender de columnas con inconsistencias.
Se respeta la regla de cierres: los promedios usan solo días operados.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.tseries.offsets import MonthEnd

from . import config as cfg

# Esquema de la hoja Concentrado (tras limpiar espacios en encabezados)
COL_FECHA = "FECHA"
COL_EST = "ESTACION"
COL_TOTAL_MB = "Total $"          # margen bruto total del día
LTS = {"Diésel": "D LTS", "Premium": "P LTS", "Regular": "R LTS"}
MB = {"Diésel": "MB DIESEL", "Premium": "MB PREMIUM", "Regular": "MB REGULAR"}
PRODUCTOS = list(LTS.keys())

MESES_ABBR = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}


# ----------------------------------------------------------------------
# CARGA
# ----------------------------------------------------------------------
def cargar_margenes(ruta: Path | str | None = None) -> pd.DataFrame:
    """Lee la hoja Concentrado y devuelve un DataFrame saneado."""
    ruta = Path(ruta) if ruta else cfg.RUTA_MARGENES

    def _abrir(p):
        # El `with` es obligatorio: sin cerrar el manejador, Windows no deja
        # borrar la copia temporal y el respaldo truena con WinError 32.
        with pd.ExcelFile(p, engine="openpyxl") as xl:
            hoja = next((s for s in xl.sheet_names
                         if s.strip() == cfg.HOJA_MARGENES.strip()),
                        xl.sheet_names[0])
            return pd.read_excel(xl, sheet_name=hoja)

    try:
        df = _abrir(ruta)
    except PermissionError:                      # archivo abierto en Excel
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp_path = tmp.name
        shutil.copy2(ruta, tmp_path)
        try:
            df = _abrir(tmp_path)
        finally:
            try:                                 # limpieza best-effort
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:
                pass

    return _sanear(df)


def _sanear(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    df[COL_EST] = df[COL_EST].astype(str).str.strip().str.upper()   # V01: TREHER T
    df[COL_FECHA] = pd.to_datetime(df[COL_FECHA], errors="coerce")
    df = df.dropna(subset=[COL_FECHA, COL_EST])
    df = df[df[COL_FECHA] <= pd.Timestamp.today().normalize()]       # V08: sin futuras

    num = list(LTS.values()) + list(MB.values()) + [COL_TOTAL_MB]
    df[num] = df[num].apply(pd.to_numeric, errors="coerce")

    df = df.sort_values([COL_EST, COL_FECHA])
    df = df.drop_duplicates(subset=[COL_EST, COL_FECHA], keep="first")

    # Día operado: vendió algún litro real.
    df["Operó"] = df[list(LTS.values())].gt(0).any(axis=1)

    # Margen por litro recalculado (robusto), solo donde hubo litros.
    for prod in PRODUCTOS:
        litros = df[LTS[prod]].where(df[LTS[prod]] > 0)
        df[f"MgL {prod}"] = df[MB[prod]] / litros

    df["Margen_total"] = df[list(MB.values())].sum(axis=1, min_count=1)
    df["Litros_total"] = df[list(LTS.values())].sum(axis=1, min_count=1)
    df["Año"] = df[COL_FECHA].dt.year
    df["Mes"] = df[COL_FECHA].dt.month
    return df.reset_index(drop=True)


def frescura(df: pd.DataFrame) -> str:
    """Texto de cobertura para mostrar en el dashboard."""
    fmin, fmax = df[COL_FECHA].min(), df[COL_FECHA].max()
    return (f"Márgenes {fmin.date()} → {fmax.date()} · "
            f"{df[COL_EST].nunique()} estaciones")


# ----------------------------------------------------------------------
# AGREGADOS
# ----------------------------------------------------------------------
def resumen_margen(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por estación: rentabilidad total, por día y por litro."""
    filas = []
    for est, g in df.groupby(COL_EST):
        op = g[g["Operó"]]
        dias = len(op)
        mb_total = g["Margen_total"].sum(min_count=1)
        lts_total = g["Litros_total"].sum(min_count=1)
        perdidas = sum(
            (g[f"MgL {p}"] < 0).sum() for p in PRODUCTOS
        )
        filas.append({
            COL_EST: est,
            "Margen_total_$": mb_total,
            "Margen_$/día_op": mb_total / dias if dias else np.nan,
            "Margen_$/L": mb_total / lts_total if lts_total else np.nan,
            "Días_operados": dias,
            "Días_a_pérdida": int(perdidas),
        })
    return (pd.DataFrame(filas)
            .sort_values("Margen_$/día_op", ascending=False)
            .reset_index(drop=True))


def etiqueta_periodo(per) -> str:
    """'May 2026' a partir de un Period mensual."""
    return f"{MESES_ABBR[per.month]} {per.year}"


def mes_anterior_completo(df: pd.DataFrame):
    """Último mes con datos completo (= mes anterior al vigente)."""
    return _ultimo_mes_completo(df)


def mix_volumen_vs_margen(df: pd.DataFrame, estacion: str | None = None,
                          periodo=None) -> pd.DataFrame:
    """
    Por producto: % del VOLUMEN y % del MARGEN que aporta, más su margen/L.
    Revela cuando un producto pesa poco en litros pero mucho en rentabilidad.
    Si `periodo` (Period mensual) se da, se limita a ese mes.
    """
    g = df if estacion is None else df[df[COL_EST] == estacion]
    if periodo is not None:
        g = g[g[COL_FECHA].dt.to_period("M") == periodo]
    if g.empty:
        raise ValueError(f"Sin datos de margen para {estacion!r}")

    lts = {p: g[LTS[p]].sum(min_count=1) for p in PRODUCTOS}
    mb = {p: g[MB[p]].sum(min_count=1) for p in PRODUCTOS}
    tot_lts, tot_mb = sum(lts.values()), sum(mb.values())

    filas = []
    for p in PRODUCTOS:
        filas.append({
            "Producto": p,
            "% del volumen": 100 * lts[p] / tot_lts if tot_lts else np.nan,
            "% del margen": 100 * mb[p] / tot_mb if tot_mb else np.nan,
            "Margen_$/L": mb[p] / lts[p] if lts[p] else np.nan,
        })
    return pd.DataFrame(filas)


def volumen_vs_margen(df: pd.DataFrame, periodo=None) -> pd.DataFrame:
    """
    Contrasta tamaño (litros/día op) contra rentabilidad (margen $/día op y
    margen/L) en un mes. Por defecto usa el mes anterior completo.
    En df.attrs['periodo'] queda el mes usado.
    """
    per = periodo or _ultimo_mes_completo(df)
    g = df[(df[COL_FECHA].dt.to_period("M") == per) & df["Operó"]]
    filas = []
    for est, h in g.groupby(COL_EST):
        dias = len(h)
        lts = h["Litros_total"].sum(min_count=1)
        mb = h["Margen_total"].sum(min_count=1)
        filas.append({
            COL_EST: est,
            "Litros_$/día_op": lts / dias if dias else np.nan,
            "Margen_$/día_op": mb / dias if dias else np.nan,
            "Margen_$/L": mb / lts if lts else np.nan,
        })
    out = pd.DataFrame(filas)
    if out.empty:
        return out
    out["Rank_volumen"] = out["Litros_$/día_op"].rank(ascending=False).astype(int)
    out["Rank_margen"] = out["Margen_$/día_op"].rank(ascending=False).astype(int)
    out = out.sort_values("Margen_$/día_op", ascending=False).reset_index(drop=True)
    out.attrs["periodo"] = per
    return out


def _meses_previos(df: pd.DataFrame, n: int):
    per_ult = _ultimo_mes_completo(df)
    return [per_ult - i for i in range(n - 1, -1, -1)]


def gross_margin_mensual(df: pd.DataFrame, bd: pd.DataFrame,
                         meses: int = 6) -> pd.DataFrame:
    """
    Gross margin del grupo por mes (últimos `meses` completos):
    litros, ventas ($), margen bruto ($) y GROSS MARGIN = margen bruto ÷ ventas.
    El margen viene de esta base; las ventas ($) y litros, de BD_Limpia
    (restringido a las estaciones que sí tienen margen).
    """
    periodos = _meses_previos(df, meses)
    ests = df[COL_EST].unique()

    dm = df.copy()
    dm["P"] = dm[COL_FECHA].dt.to_period("M")
    marg = dm[dm["P"].isin(periodos)].groupby("P")["Margen_total"].sum(min_count=1)

    b = bd[bd[cfg.COL_ESTACION].isin(ests)].copy()
    b["P"] = b[cfg.COL_FECHA].dt.to_period("M")
    imp = pd.DataFrame({p: b[cfg.LTS[p]] * b[cfg.PRECIO[p]] for p in cfg.PRODUCTOS})
    b["rev"] = imp.sum(axis=1, min_count=1)
    bm = b[b["P"].isin(periodos)].groupby("P").agg(
        Litros=(cfg.COL_TOTAL_LTS, "sum"), Ventas=("rev", "sum"))

    filas = []
    for per in periodos:
        litros = bm["Litros"].get(per, np.nan)
        ventas = bm["Ventas"].get(per, np.nan)
        mb = marg.get(per, np.nan)
        filas.append({
            "Mes": etiqueta_periodo(per),
            "Litros": litros,
            "Ventas_$": ventas,
            "Margen_bruto_$": mb,
            "Gross_margin_%": 100 * mb / ventas if ventas else np.nan,
        })
    return pd.DataFrame(filas)


def gross_margin_por_producto(df: pd.DataFrame, bd: pd.DataFrame,
                              estacion: str | None = None,
                              periodo=None) -> pd.DataFrame:
    """
    Gross margin por combustible (filas) en un mes: ventas ($), margen bruto ($)
    y GROSS MARGIN %. Por defecto usa el mes anterior completo. Si `estacion`
    se indica, se limita a esa estación.
    """
    per = periodo or _ultimo_mes_completo(df)
    dm = df if estacion is None else df[df[COL_EST] == estacion]
    dm = dm[dm[COL_FECHA].dt.to_period("M") == per]

    b = bd if estacion is None else bd[bd[cfg.COL_ESTACION] == estacion]
    if estacion is None:
        b = b[b[cfg.COL_ESTACION].isin(df[COL_EST].unique())]
    b = b[b[cfg.COL_FECHA].dt.to_period("M") == per]

    filas = []
    for p in PRODUCTOS:
        mb = dm[MB[p]].sum(min_count=1)
        rev = (b[cfg.LTS[p]] * b[cfg.PRECIO[p]]).sum(min_count=1)
        filas.append({
            "Producto": p,
            "Ventas_$": rev,
            "Margen_bruto_$": mb,
            "Gross_margin_%": 100 * mb / rev if rev else np.nan,
        })
    return pd.DataFrame(filas)


def evolucion_mensual(df: pd.DataFrame, estacion: str) -> pd.DataFrame:
    """Margen $ y margen/L por mes para una estación."""
    g = df[df[COL_EST] == estacion].copy()
    if g.empty:
        raise ValueError(f"Sin datos de margen para {estacion!r}")
    g["Periodo"] = g[COL_FECHA].dt.to_period("M").dt.to_timestamp()
    out = g.groupby("Periodo").agg(
        Margen_total_=("Margen_total", "sum"),
        Litros_=("Litros_total", "sum"),
        Días_operados=("Operó", "sum"),
    )
    out = out.rename(columns={"Margen_total_": "Margen_total_$"})
    out["Margen_$/L"] = out["Margen_total_$"] / out["Litros_"].replace(0, np.nan)
    out["Margen_$/día_op"] = out["Margen_total_$"] / out["Días_operados"].replace(0, np.nan)
    return out.drop(columns="Litros_").reset_index()


def dias_a_perdida(df: pd.DataFrame, estacion: str | None = None) -> pd.DataFrame:
    """Días con margen por litro negativo (venta por debajo del costo)."""
    g = df if estacion is None else df[df[COL_EST] == estacion]
    mask = pd.concat([g[f"MgL {p}"] < 0 for p in PRODUCTOS], axis=1).any(axis=1)
    cols = [COL_FECHA, COL_EST] + [f"MgL {p}" for p in PRODUCTOS]
    return g.loc[mask, cols].sort_values(COL_FECHA).reset_index(drop=True)


# ----------------------------------------------------------------------
# KPIs DE CRECIMIENTO DEL MARGEN (MoM / YoY / YTD, like-for-like)
# ----------------------------------------------------------------------
def _ultimo_mes_completo(df: pd.DataFrame):
    ult = df[COL_FECHA].max()
    per = ult.to_period("M")
    return per if ult.normalize() == (ult + MonthEnd(0)).normalize() else per - 1


def _mb_por_estacion(df, ini, fin) -> pd.Series:
    m = (df[COL_FECHA] >= ini) & (df[COL_FECHA] <= fin) & df["Operó"]
    return df.loc[m].groupby(COL_EST)["Margen_total"].sum(min_count=1)


def _lfl(actual: pd.Series, base: pd.Series) -> dict:
    comunes = [e for e in actual.index.intersection(base.index)
               if pd.notna(actual[e]) and pd.notna(base[e]) and base[e] > 0]
    va, vb = actual[comunes].sum(), base[comunes].sum()
    return {"Margen_actual_$": va, "Margen_comparación_$": vb,
            "Var_%": 100 * (va / vb - 1) if vb else np.nan,
            "Estaciones_LFL": len(comunes)}


def kpis_margen(df: pd.DataFrame) -> pd.DataFrame:
    """MoM / YoY / YTD del margen bruto del grupo, like-for-like."""
    mes = _ultimo_mes_completo(df)
    mes_prev, mes_yoy = mes - 1, mes - 12

    def vent(per):
        return per.to_timestamp(), per.to_timestamp(how="end").normalize()

    a = vent(mes)
    filas = [
        {"Indicador": "MoM (mensual)", "Periodo actual": _lbl(mes),
         "Comparación": _lbl(mes_prev),
         **_lfl(_mb_por_estacion(df, *a), _mb_por_estacion(df, *vent(mes_prev)))},
        {"Indicador": "YoY (interanual)", "Periodo actual": _lbl(mes),
         "Comparación": _lbl(mes_yoy),
         **_lfl(_mb_por_estacion(df, *a), _mb_por_estacion(df, *vent(mes_yoy)))},
        {"Indicador": "YTD (acumulado)",
         "Periodo actual": f"Ene–{MESES_ABBR[mes.month]} {mes.year}",
         "Comparación": f"Ene–{MESES_ABBR[mes.month]} {mes.year - 1}",
         **_lfl(
             _mb_por_estacion(df, pd.Timestamp(mes.year, 1, 1), a[1]),
             _mb_por_estacion(df, pd.Timestamp(mes.year - 1, 1, 1), vent(mes_yoy)[1]))},
    ]
    return pd.DataFrame(filas)


def _lbl(per) -> str:
    return f"{MESES_ABBR[per.month]} {per.year}"
