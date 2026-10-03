"""
Motor de KPIs ejecutivos (nivel Dirección General).

Todo parametrizado por MES (`YYYY-MM`) para presentación mensual. Sigue la
jerarquía de fuentes de la especificación:
  - Litros, venta y precio  → BD (data.cargar_bd)
  - Margen bruto y unitario → BD_MARGENES (margenes.cargar_margenes)
El margen sobre venta cruza ambas por (estación, mes), nunca con merge global.
El margen unitario del grupo se calcula SIEMPRE ponderado (Σ MB / Σ litros).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as cfg
from . import margenes as mg


def _p(per) -> pd.Period:
    return per if isinstance(per, pd.Period) else pd.Period(per, "M")


def _bd_mes(bd, per):
    return bd[bd[cfg.COL_FECHA].dt.to_period("M") == _p(per)]


def _mg_mes(dfm, per):
    return dfm[dfm[mg.COL_FECHA].dt.to_period("M") == _p(per)]


# ----------------------------------------------------------------------
# A1 · Margen sobre venta (%)
# ----------------------------------------------------------------------
def margen_sobre_venta(bd, dfm, per) -> dict:
    dm = _mg_mes(dfm, per)
    ests = dm[mg.COL_EST].unique()
    marg = dm["Margen_total"].sum(min_count=1)
    b = _bd_mes(bd, per)
    b = b[b[cfg.COL_ESTACION].isin(ests)]
    venta = b[cfg.COL_TOTAL_VENTA].sum(min_count=1)
    lts = dm["Litros_total"].sum(min_count=1)
    return {
        "margen_bruto": marg,
        "venta": venta,
        "litros": lts,
        "margen_sobre_venta_%": 100 * marg / venta if venta else np.nan,
        "margen_unitario": marg / lts if lts else np.nan,
    }


# ----------------------------------------------------------------------
# A2 · Descomposición de la variación de margen (Volumen / Mix / Mg unitario)
# ----------------------------------------------------------------------
def descomposicion_margen(dfm, p_actual, p_base) -> pd.DataFrame:
    da, db = _mg_mes(dfm, p_actual), _mg_mes(dfm, p_base)
    L1, L0 = da["Litros_total"].sum(min_count=1), db["Litros_total"].sum(min_count=1)
    MB1, MB0 = da["Margen_total"].sum(min_count=1), db["Margen_total"].sum(min_count=1)
    mu0 = MB0 / L0                                     # margen unitario ponderado base

    efecto_vol = (L1 - L0) * mu0
    efecto_mix = 0.0
    for p in mg.PRODUCTOS:
        L0p = db[mg.LTS[p]].sum(min_count=1)
        L1p = da[mg.LTS[p]].sum(min_count=1)
        MB0p = db[mg.MB[p]].sum(min_count=1)
        mu0p = MB0p / L0p if L0p else 0.0
        efecto_mix += (L1p / L1 - L0p / L0) * L1 * (mu0p - mu0)
    efecto_mu = (MB1 - MB0) - efecto_vol - efecto_mix

    total = MB1 - MB0
    filas = [
        ("Margen base", MB0, np.nan),
        ("Efecto volumen", efecto_vol, 100 * efecto_vol / total if total else np.nan),
        ("Efecto mix", efecto_mix, 100 * efecto_mix / total if total else np.nan),
        ("Efecto margen unitario", efecto_mu, 100 * efecto_mu / total if total else np.nan),
        ("Margen actual", MB1, np.nan),
        ("Δ Total", total, 100.0),
    ]
    return pd.DataFrame(filas, columns=["Concepto", "Monto_$", "%_de_la_variación"])


# ----------------------------------------------------------------------
# A3 · Descomposición de la variación de venta (Volumen / Precio) por combustible
# ----------------------------------------------------------------------
def descomposicion_venta(bd, p_actual, p_base) -> pd.DataFrame:
    da, db = _bd_mes(bd, p_actual), _bd_mes(bd, p_base)
    filas = []
    for p in cfg.PRODUCTOS:
        L1 = da[cfg.LTS[p]].sum(min_count=1)
        L0 = db[cfg.LTS[p]].sum(min_count=1)
        imp1 = (da[cfg.LTS[p]] * da[cfg.PRECIO[p]]).sum(min_count=1)
        imp0 = (db[cfg.LTS[p]] * db[cfg.PRECIO[p]]).sum(min_count=1)
        P0 = imp0 / L0 if L0 else np.nan
        P1 = imp1 / L1 if L1 else np.nan
        filas.append({
            "Combustible": p,
            "Δ_venta_$": imp1 - imp0,
            "Efecto_volumen_$": (L1 - L0) * P0,
            "Efecto_precio_$": (P1 - P0) * L1,
        })
    out = pd.DataFrame(filas)
    tot = {"Combustible": "TOTAL"}
    for c in ["Δ_venta_$", "Efecto_volumen_$", "Efecto_precio_$"]:
        tot[c] = out[c].sum()
    return pd.concat([out, pd.DataFrame([tot])], ignore_index=True)


# ----------------------------------------------------------------------
# A4 · Margen bruto por estación + contribución (Pareto)
# ----------------------------------------------------------------------
def margen_por_estacion(dfm, per) -> pd.DataFrame:
    dm = _mg_mes(dfm, per)
    g = (dm.groupby(mg.COL_EST)["Margen_total"].sum(min_count=1)
         .sort_values(ascending=False).rename("Margen_bruto_$").reset_index())
    tot = g["Margen_bruto_$"].sum()
    g["%_del_grupo"] = 100 * g["Margen_bruto_$"] / tot
    g["%_acumulado"] = g["%_del_grupo"].cumsum()
    return g.rename(columns={mg.COL_EST: "Estación"})


# ----------------------------------------------------------------------
# A5 · Contribución a la variación de margen (por estación)
# ----------------------------------------------------------------------
def contribucion_variacion(dfm, p_actual, p_base) -> pd.DataFrame:
    da, db = _mg_mes(dfm, p_actual), _mg_mes(dfm, p_base)
    ga = da.groupby(mg.COL_EST)["Margen_total"].sum(min_count=1)
    gb = db.groupby(mg.COL_EST)["Margen_total"].sum(min_count=1)
    idx = ga.index.union(gb.index)
    delta = ga.reindex(idx).fillna(0) - gb.reindex(idx).fillna(0)
    d_grupo = delta.sum()
    out = delta.rename("Δ_margen_$").reset_index().rename(columns={mg.COL_EST: "Estación"})
    out["%_de_la_variación"] = 100 * out["Δ_margen_$"] / d_grupo if d_grupo else np.nan
    return out.reindex(out["Δ_margen_$"].abs().sort_values(ascending=False).index).reset_index(drop=True)


# ----------------------------------------------------------------------
# A6 · Crecimiento total vs. mismas estaciones (YTD)
# ----------------------------------------------------------------------
def _sin_cierres(bd, ini, fin):
    """Estaciones que operaron TODOS los días del rango (sin cierres)."""
    w = bd[(bd[cfg.COL_FECHA] >= ini) & (bd[cfg.COL_FECHA] <= fin)]
    por_est = w.groupby(cfg.COL_ESTACION).agg(
        dias=(cfg.COL_FECHA, "nunique"), op=("Operó", "sum"))
    return set(por_est.index[por_est["dias"] == por_est["op"]])


def crecimiento_mismas_estaciones(bd, anio, mes_hasta) -> pd.DataFrame:
    """YTD enero..mes_hasta del año vs. mismo tramo del año anterior:
    variación TOTAL y de MISMAS ESTACIONES (sin cierres en ninguno de los dos)."""
    a_ini = pd.Timestamp(anio, 1, 1); a_fin = pd.Timestamp(anio, mes_hasta, 1) + pd.offsets.MonthEnd(0)
    b_ini = pd.Timestamp(anio - 1, 1, 1); b_fin = pd.Timestamp(anio - 1, mes_hasta, 1) + pd.offsets.MonthEnd(0)

    def vol(ini, fin, ests=None):
        w = bd[(bd[cfg.COL_FECHA] >= ini) & (bd[cfg.COL_FECHA] <= fin)]
        if ests is not None:
            w = w[w[cfg.COL_ESTACION].isin(ests)]
        return w[cfg.COL_TOTAL_LTS].sum(min_count=1)

    tot_a, tot_b = vol(a_ini, a_fin), vol(b_ini, b_fin)
    comunes = _sin_cierres(bd, a_ini, a_fin) & _sin_cierres(bd, b_ini, b_fin)
    mm_a, mm_b = vol(a_ini, a_fin, comunes), vol(b_ini, b_fin, comunes)

    return pd.DataFrame([
        {"Base": f"Total {anio} vs {anio-1}", "Litros_actual": tot_a,
         "Litros_base": tot_b, "Var_%": 100 * (tot_a / tot_b - 1) if tot_b else np.nan,
         "Estaciones": bd[cfg.COL_ESTACION].nunique()},
        {"Base": f"Mismas estaciones {anio} vs {anio-1}", "Litros_actual": mm_a,
         "Litros_base": mm_b, "Var_%": 100 * (mm_a / mm_b - 1) if mm_b else np.nan,
         "Estaciones": len(comunes)},
    ])


# ----------------------------------------------------------------------
# Serie mensual de margen (para tarjetas y tabla de 13 meses)
# ----------------------------------------------------------------------
def serie_margen(bd, dfm, n_meses=13) -> pd.DataFrame:
    per_ult = dfm[mg.COL_FECHA].dt.to_period("M").max()
    periodos = [per_ult - i for i in range(n_meses - 1, -1, -1)]
    filas = []
    for per in periodos:
        r = margen_sobre_venta(bd, dfm, per)
        filas.append({
            "Mes": mg.etiqueta_periodo(per),
            "Litros": r["litros"], "Venta_$": r["venta"],
            "Margen_bruto_$": r["margen_bruto"],
            "Margen_$/L": r["margen_unitario"],
            "Margen_s/venta_%": r["margen_sobre_venta_%"],
        })
    return pd.DataFrame(filas)


def ultimo_mes_margen(dfm) -> pd.Period:
    """Último mes con datos de margen (referencia por defecto del dashboard)."""
    return dfm[mg.COL_FECHA].dt.to_period("M").max()
