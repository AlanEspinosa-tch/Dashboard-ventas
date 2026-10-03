"""
Motor de tablas del reporte ejecutivo v3 (categoría A: cálculo puro).

Reglas:
  - Litros/venta/precio → BD.  Margen → BD_MARGENES.  Sin merge global.
  - V8: la comparación contra un año se marca n/a (NaN) si la estación tuvo
    algún día en cero en cualquiera de los dos periodos (no comparable).
  - Estación comparable = volumen > 0 TODOS los días de AMBOS periodos.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as cfg
from . import margenes as mg

MES_NOMBRE = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo",
              6: "junio", 7: "julio", 8: "agosto", 9: "septiembre",
              10: "octubre", 11: "noviembre", 12: "diciembre"}


def _p(per) -> pd.Period:
    return per if isinstance(per, pd.Period) else pd.Period(per, "M")


def _mes(bd, per):
    return bd[bd[cfg.COL_FECHA].dt.to_period("M") == _p(per)]


def _importe(df, prod):
    return (df[cfg.LTS[prod]] * df[cfg.PRECIO[prod]]).sum(min_count=1)


def _operaron_todo(w: pd.DataFrame, max_cierre: int | None = None) -> set:
    """
    Estaciones COMPARABLES en el subconjunto `w`: las que no tuvieron un
    cierre MATERIAL (menos de `max_cierre` días cerrados; por defecto
    config.DIAS_CIERRE_MATERIAL).

    Usa la marca `Operó` porque los días cerrados vienen como NaN y `min()`
    los ignoraría silenciosamente (dando comparables de más). Un paro corto
    no saca a la estación; un cierre largo o una alta/baja sí.
    """
    if w.empty:
        return set()
    tope = cfg.DIAS_CIERRE_MATERIAL if max_cierre is None else max_cierre
    g = w.groupby(cfg.COL_ESTACION).agg(dias=(cfg.COL_FECHA, "nunique"),
                                        op=("Operó", "sum"))
    cerrados = g["dias"] - g["op"]
    # Doble criterio: absoluto (cierre largo) y proporcional (para que en una
    # ventana mensual un paro de 12 días —39% del mes— también descalifique).
    ok = (cerrados < tope) & (cerrados / g["dias"] <= cfg.FRACCION_CIERRE_MATERIAL)
    return set(g.index[ok])


def _cerradas(w: pd.DataFrame, max_cierre: int | None = None) -> set:
    """Estaciones con cierre material en el subconjunto `w`."""
    if w.empty:
        return set()
    todas = set(w[cfg.COL_ESTACION].unique())
    return todas - _operaron_todo(w, max_cierre)


def comparables(bd, per_a, per_b) -> set:
    """Estaciones que operaron todos los días de ambos periodos."""
    return _operaron_todo(_mes(bd, per_a)) & _operaron_todo(_mes(bd, per_b))


def _var(actual, base):
    """(variación absoluta, variación %) — NaN si no hay base."""
    if pd.isna(base) or base == 0 or pd.isna(actual):
        return np.nan, np.nan
    return actual - base, 100 * (actual / base - 1)


# ----------------------------------------------------------------------
# PÁGINA 1 · por combustible
# ----------------------------------------------------------------------
def volumen_combustible(bd, per) -> pd.DataFrame:
    per = _p(per)
    a, b25, b24 = _mes(bd, per), _mes(bd, per - 12), _mes(bd, per - 24)
    tot = sum(a[cfg.LTS[p]].sum(min_count=1) for p in cfg.PRODUCTOS)
    filas = []
    for p in cfg.PRODUCTOS:
        L, L25, L24 = (a[cfg.LTS[p]].sum(min_count=1),
                       b25[cfg.LTS[p]].sum(min_count=1),
                       b24[cfg.LTS[p]].sum(min_count=1))
        v25, e25 = _var(L, L25)
        v24, e24 = _var(L, L24)
        filas.append({"Etiqueta": p, "Litros": L, "Mix": 100 * L / tot,
                      "Var25": v25, "Evol25": e25, "Var24": v24, "Evol24": e24})
    return _con_total(pd.DataFrame(filas), ["Litros", "Var25", "Var24"], bd,
                      per, "vol")


def importe_combustible(bd, per) -> pd.DataFrame:
    per = _p(per)
    a, b25 = _mes(bd, per), _mes(bd, per - 12)
    tot = sum(_importe(a, p) for p in cfg.PRODUCTOS)
    filas = []
    for p in cfg.PRODUCTOS:
        imp, imp25 = _importe(a, p), _importe(b25, p)
        L, L25 = a[cfg.LTS[p]].sum(min_count=1), b25[cfg.LTS[p]].sum(min_count=1)
        v25, e25 = _var(imp, imp25)
        filas.append({"Etiqueta": p, "Importe": imp, "Mix": 100 * imp / tot,
                      "Var25": v25, "Evol25": e25,
                      "Precio_ant": imp25 / L25 if L25 else np.nan,
                      "Precio_act": imp / L if L else np.nan})
    df = pd.DataFrame(filas)
    imp_t = df["Importe"].sum()
    imp25_t = sum(_importe(b25, p) for p in cfg.PRODUCTOS)
    L_t = sum(a[cfg.LTS[p]].sum(min_count=1) for p in cfg.PRODUCTOS)
    L25_t = sum(b25[cfg.LTS[p]].sum(min_count=1) for p in cfg.PRODUCTOS)
    v25, e25 = _var(imp_t, imp25_t)
    total = {"Etiqueta": "TOTAL", "Importe": imp_t, "Mix": 100.0, "Var25": v25,
             "Evol25": e25, "Precio_ant": imp25_t / L25_t if L25_t else np.nan,
             "Precio_act": imp_t / L_t if L_t else np.nan}
    return pd.concat([df, pd.DataFrame([total])], ignore_index=True)


def _con_total(df, sumables, bd, per, modo):
    """Agrega fila TOTAL recalculando los % desde los totales."""
    per = _p(per)
    a, b25, b24 = _mes(bd, per), _mes(bd, per - 12), _mes(bd, per - 24)
    L = a[cfg.COL_TOTAL_LTS].sum(min_count=1)
    L25 = b25[cfg.COL_TOTAL_LTS].sum(min_count=1)
    L24 = b24[cfg.COL_TOTAL_LTS].sum(min_count=1)
    v25, e25 = _var(L, L25)
    v24, e24 = _var(L, L24)
    total = {"Etiqueta": "TOTAL", "Litros": L, "Mix": 100.0, "Var25": v25,
             "Evol25": e25, "Var24": v24, "Evol24": e24}
    return pd.concat([df, pd.DataFrame([total])], ignore_index=True)


# ----------------------------------------------------------------------
# PÁGINA 2 · por estación (mes)
# ----------------------------------------------------------------------
def _tabla_estacion(bd, per, ini_a=None, fin_a=None, acumulado=False):
    """Volumen por estación del mes (o YTD si acumulado=True)."""
    per = _p(per)
    if acumulado:
        def rango(y):
            return (pd.Timestamp(y, 1, 1),
                    pd.Timestamp(y, per.month, 1) + pd.offsets.MonthEnd(0))
        ventanas = {y: rango(y) for y in (per.year, per.year - 1, per.year - 2)}

        def vol(y):
            i, f = ventanas[y]
            w = bd[(bd[cfg.COL_FECHA] >= i) & (bd[cfg.COL_FECHA] <= f)]
            return w.groupby(cfg.COL_ESTACION)[cfg.COL_TOTAL_LTS].sum(min_count=1)

        def cerradas(y):
            i, f = ventanas[y]
            return _cerradas(bd[(bd[cfg.COL_FECHA] >= i) & (bd[cfg.COL_FECHA] <= f)])
        A, B25, B24 = vol(per.year), vol(per.year - 1), vol(per.year - 2)
        no25 = cerradas(per.year) | cerradas(per.year - 1)
        no24 = cerradas(per.year) | cerradas(per.year - 2)
    else:
        def vol(p):
            return _mes(bd, p).groupby(cfg.COL_ESTACION)[cfg.COL_TOTAL_LTS].sum(min_count=1)

        def cerradas(p):
            return _cerradas(_mes(bd, p))
        A, B25, B24 = vol(per), vol(per - 12), vol(per - 24)
        no25 = cerradas(per) | cerradas(per - 12)
        no24 = cerradas(per) | cerradas(per - 24)

    tot = A.sum()
    filas = []
    for est in A.sort_values(ascending=False).index:
        L = A.get(est, np.nan)
        v25, e25 = (np.nan, np.nan) if est in no25 else _var(L, B25.get(est, np.nan))
        v24, e24 = (np.nan, np.nan) if est in no24 else _var(L, B24.get(est, np.nan))
        filas.append({"Etiqueta": est, "Litros": L, "Mix": 100 * L / tot,
                      "Var25": v25, "Evol25": e25, "Var24": v24, "Evol24": e24})
    df = pd.DataFrame(filas)

    # --- Cuadre con PANEL POR AÑO (decisión W1) ---
    # El panel se RECALCULA para cada año base: una estación puede ser
    # comparable contra 2024 y no contra 2025 (COMBULUB cerró solo en 2025).
    # No existe lista fija de excluidas.
    todas = A.index.union(B25.index).union(B24.index)

    def _s(S, ests):
        return S.reindex(ests).fillna(0).sum()

    paneles = {}
    for etq, B, no_ in (("25", B25, no25), ("24", B24, no24)):
        presentes = set(A.index) & set(B.index)          # opera en ambos años
        panel = sorted(presentes - set(no_))             # sin cierre material
        fuera = sorted(set(todas) - set(panel))
        c = _s(A, panel) - _s(B, panel)
        n = _s(A, fuera) - _s(B, fuera)
        g = _s(A, todas) - _s(B, todas)
        # W5 · el assert corre para cada año base
        assert abs(c + n - g) < 1, f"Descuadre vs 20{etq}: {c} + {n} != {g}"
        paneles[etq] = {
            "panel": panel, "fuera": fuera, "c": c, "n": n, "g": g,
            "ec": _var(_s(A, panel), _s(B, panel))[1],
            "eg": _var(_s(A, todas), _s(B, todas))[1],
            "L_panel": _s(A, panel),
        }

    p25, p24 = paneles["25"], paneles["24"]
    extra = [
        {"Etiqueta": "TOTAL COMPARABLE", "Litros": p25["L_panel"],
         "Mix": 100 * p25["L_panel"] / tot, "Var25": p25["c"], "Evol25": p25["ec"],
         "Var24": p24["c"], "Evol24": p24["ec"]},
        # W4 · si no hay nada que conciliar, la celda va vacía (—), no "+0"
        {"Etiqueta": "No comparables", "Litros": tot - p25["L_panel"],
         "Mix": 100 * (tot - p25["L_panel"]) / tot,
         "Var25": p25["n"] if abs(p25["n"]) > 0.5 else np.nan, "Evol25": np.nan,
         "Var24": p24["n"] if abs(p24["n"]) > 0.5 else np.nan, "Evol24": np.nan},
        {"Etiqueta": "TOTAL GRUPO", "Litros": tot, "Mix": 100.0,
         "Var25": p25["g"], "Evol25": p25["eg"],
         "Var24": p24["g"], "Evol24": p24["eg"]},
    ]
    out = pd.concat([df, pd.DataFrame(extra)], ignore_index=True)
    # W2 · el tamaño del panel se toma de len(panel), nunca escrito a mano
    out.attrs["panel25"] = len(p25["panel"])
    out.attrs["panel24"] = len(p24["panel"])
    out.attrs["fuera25"] = p25["fuera"]
    out.attrs["fuera24"] = p24["fuera"]
    return out


def volumen_estacion(bd, per):
    return _tabla_estacion(bd, per)


def volumen_acumulado_estacion(bd, per):
    return _tabla_estacion(bd, per, acumulado=True)


def importe_estacion(bd, per) -> pd.DataFrame:
    per = _p(per)
    a, b25 = _mes(bd, per), _mes(bd, per - 12)
    imp_a = a.groupby(cfg.COL_ESTACION)[cfg.COL_TOTAL_VENTA].sum(min_count=1)
    imp_b = b25.groupby(cfg.COL_ESTACION)[cfg.COL_TOTAL_VENTA].sum(min_count=1)
    lts_a = a.groupby(cfg.COL_ESTACION)[cfg.COL_TOTAL_LTS].sum(min_count=1)
    no25 = _cerradas(a) | _cerradas(b25)

    tot = imp_a.sum()
    filas = []
    for est in imp_a.sort_values(ascending=False).index:
        imp = imp_a[est]
        v25, e25 = (np.nan, np.nan) if est in no25 else _var(imp, imp_b.get(est, np.nan))
        filas.append({"Etiqueta": est, "Importe": imp, "Mix": 100 * imp / tot,
                      "Var25": v25, "Evol25": e25,
                      "Precio_act": imp / lts_a[est] if lts_a.get(est) else np.nan})
    df = pd.DataFrame(filas)
    v25t, e25t = _var(tot, imp_b.sum())
    total = {"Etiqueta": "TOTAL", "Importe": tot, "Mix": 100.0, "Var25": v25t,
             "Evol25": e25t,
             "Precio_act": tot / lts_a.sum() if lts_a.sum() else np.nan}
    return pd.concat([df, pd.DataFrame([total])], ignore_index=True)


# ----------------------------------------------------------------------
# PÁGINA 3 · crecimiento comparable
# ----------------------------------------------------------------------
def crecimiento_comparable(bd, per) -> pd.DataFrame:
    per = _p(per)

    def rango(y):
        return (pd.Timestamp(y, 1, 1),
                pd.Timestamp(y, per.month, 1) + pd.offsets.MonthEnd(0))

    def vol(y, ests=None):
        i, f = rango(y)
        w = bd[(bd[cfg.COL_FECHA] >= i) & (bd[cfg.COL_FECHA] <= f)]
        if ests is not None:
            w = w[w[cfg.COL_ESTACION].isin(ests)]
        return w[cfg.COL_TOTAL_LTS].sum(min_count=1)

    def sin_cierres(y):
        i, f = rango(y)
        return _operaron_todo(bd[(bd[cfg.COL_FECHA] >= i) & (bd[cfg.COL_FECHA] <= f)])

    def con_datos(y):
        i, f = rango(y)
        w = bd[(bd[cfg.COL_FECHA] >= i) & (bd[cfg.COL_FECHA] <= f)]
        g = w.groupby(cfg.COL_ESTACION)[cfg.COL_TOTAL_LTS].sum(min_count=1)
        return set(g[g > 0].index)

    y = per.year
    n_tot = bd[cfg.COL_ESTACION].nunique()
    # W1 · panel recalculado por año base (no una lista fija)
    panel = {b: (sin_cierres(y) & sin_cierres(b) & con_datos(y) & con_datos(b))
             for b in (y - 1, y - 2)}

    filas = [
        {"Base": f"Cifra del grupo · {n_tot} estaciones",
         "A": vol(y), "B25": vol(y - 1), "B24": vol(y - 2), "N": n_tot,
         "Var25": 100 * (vol(y) / vol(y - 1) - 1),
         "Var24": 100 * (vol(y) / vol(y - 2) - 1)},
        {"Base": "Mismas estaciones",
         "A": vol(y, panel[y - 1]), "B25": vol(y - 1, panel[y - 1]),
         "B24": vol(y - 2, panel[y - 2]), "N": len(panel[y - 1]),
         "Var25": 100 * (vol(y, panel[y - 1]) / vol(y - 1, panel[y - 1]) - 1),
         "Var24": 100 * (vol(y, panel[y - 2]) / vol(y - 2, panel[y - 2]) - 1)},
    ]
    df = pd.DataFrame(filas)
    df.attrs["panel25"] = len(panel[y - 1])
    df.attrs["panel24"] = len(panel[y - 2])
    return df


# ----------------------------------------------------------------------
# PÁGINA 4 · margen por estación
# ----------------------------------------------------------------------
def margen_estacion(bd, dfm, per) -> pd.DataFrame:
    per = _p(per)
    dm = dfm[dfm[mg.COL_FECHA].dt.to_period("M") == per]
    dp = dfm[dfm[mg.COL_FECHA].dt.to_period("M") == per - 1]
    mb = dm.groupby(mg.COL_EST)["Margen_total"].sum(min_count=1)
    mb_p = dp.groupby(mg.COL_EST)["Margen_total"].sum(min_count=1)
    lts = dm.groupby(mg.COL_EST)["Litros_total"].sum(min_count=1)
    b = _mes(bd, per)
    venta = b.groupby(cfg.COL_ESTACION)[cfg.COL_TOTAL_VENTA].sum(min_count=1)

    tot = mb.sum()
    filas = []
    for est in mb.sort_values(ascending=False).index:
        v = venta.get(est, np.nan)
        filas.append({
            "Etiqueta": est, "Margen": mb[est], "Pct_grupo": 100 * mb[est] / tot,
            "MgL": mb[est] / lts[est] if lts.get(est) else np.nan,
            "Mg_venta": 100 * mb[est] / v if v and not pd.isna(v) else np.nan,
            "Delta": mb[est] - mb_p.get(est, np.nan),
        })
    df = pd.DataFrame(filas)
    v_tot = venta.reindex(mb.index).sum()
    total = {"Etiqueta": "TOTAL", "Margen": tot, "Pct_grupo": 100.0,
             "MgL": tot / lts.sum() if lts.sum() else np.nan,
             "Mg_venta": 100 * tot / v_tot if v_tot else np.nan,
             "Delta": tot - mb_p.sum()}
    return pd.concat([df, pd.DataFrame([total])], ignore_index=True)


# ----------------------------------------------------------------------
# PÁGINA 5 · oportunidad de recuperación (P75 de los últimos 6 meses)
# ----------------------------------------------------------------------
def ventas_trimestrales(bd) -> pd.DataFrame:
    """
    Litros por trimestre y año, SOLO trimestres completos (v6·5.2): se verifica
    la cobertura contra el calendario, no se asume. Quedan fuera 2021 Q1 (la
    base inicia el 20-mar-2021) y el trimestre en curso.
    Devuelve un DataFrame índice=año, columnas=Q1..Q4 (NaN si incompleto).
    """
    import calendar
    anios = sorted(bd[cfg.COL_ANIO].unique())
    out = pd.DataFrame(index=anios, columns=["Q1", "Q2", "Q3", "Q4"], dtype=float)
    for y in anios:
        for q in (1, 2, 3, 4):
            meses = [(q - 1) * 3 + m for m in (1, 2, 3)]
            esperados = sum(calendar.monthrange(y, m)[1] for m in meses)
            w = bd[(bd[cfg.COL_ANIO] == y) & (bd[cfg.COL_MES].isin(meses))]
            if w[cfg.COL_FECHA].nunique() == esperados:
                out.loc[y, f"Q{q}"] = w[cfg.COL_TOTAL_LTS].sum(min_count=1)
    return out.dropna(how="all")


def margen_alzas_bajas(bd, dfm, per, n: int = 3):
    """
    Parte MARGEN POR ESTACIÓN en dos tablas: las `n` mayores alzas y las `n`
    mayores caídas contra el mes anterior.

    El porcentaje se calcula DENTRO de cada grupo (Δ ÷ Σ alzas, o Δ ÷ Σ bajas),
    nunca sobre el neto del grupo: con alzas y bajas que se cancelan, el neto
    queda chico y los porcentajes se disparan por encima de 100%.

    Cada tabla cierra con "Otras N estaciones" y el total del grupo, así que
    la columna de % suma 100% aunque solo se nombren las `n` primeras.
    """
    me = margen_estacion(bd, dfm, per)
    me = me[me["Etiqueta"] != "TOTAL"].copy()
    me = me[me["Delta"].notna()]

    def _bloque(sub, signo):
        base = sub["Delta"].sum()
        if sub.empty or not base:
            return pd.DataFrame(columns=list(me.columns) + ["Pct_grupo_mov"])
        sub = sub.copy()
        sub["Pct_grupo_mov"] = 100 * sub["Delta"] / base
        sub = sub.sort_values("Pct_grupo_mov", ascending=False)
        top = sub.head(n)
        filas = [top]
        resto = sub.iloc[n:]
        if not resto.empty:
            etq = (f"Otras {len(resto)} estaciones" if len(resto) > 1
                   else "Otra estación")
            filas.append(pd.DataFrame([{
                "Etiqueta": etq,
                "Margen": resto["Margen"].sum(), "Pct_grupo": np.nan,
                "MgL": np.nan, "Mg_venta": np.nan,
                "Delta": resto["Delta"].sum(),
                "Pct_grupo_mov": resto["Pct_grupo_mov"].sum()}]))
        filas.append(pd.DataFrame([{
            "Etiqueta": f"TOTAL {signo} ({len(sub)} est.)",
            "Margen": sub["Margen"].sum(), "Pct_grupo": np.nan,
            "MgL": np.nan, "Mg_venta": np.nan,
            "Delta": base, "Pct_grupo_mov": 100.0}]))
        return pd.concat(filas, ignore_index=True)

    alzas = _bloque(me[me["Delta"] > 0], "ALZAS")
    bajas = _bloque(me[me["Delta"] < 0], "BAJAS")
    return alzas, bajas


def evolucion_mensual(bd, dfm, anio: int | None = None,
                      hasta=None) -> pd.DataFrame:
    """
    Serie mensual del año: volumen, ingreso, margen bruto y margen bruto %.

    Reglas (v5·3):
      3.1 corta en el último mes con datos de MARGEN (no de venta): un mes con
          ventas pero sin márgenes no aparece.
      3.2 la fila de acumulado es obligatoria y su % es Σmargen ÷ Σingreso
          (NO el promedio de los porcentajes mensuales).
      3.3 volumen e ingreso vienen de BD; margen bruto de BD_MARGENES.
      3.4 `hasta` (periodo del reporte) NUNCA se rebasa: un reporte de julio no
          puede mostrar agosto aunque el margen de agosto ya esté cargado.
    """
    ult_margen = dfm[mg.COL_FECHA].dt.to_period("M").max()
    if hasta is not None:
        ult_margen = min(ult_margen, _p(hasta))
    anio = anio or ult_margen.year
    periodos = [pd.Period(f"{anio}-{m:02d}") for m in range(1, 13)
                if pd.Period(f"{anio}-{m:02d}") <= ult_margen]

    filas = []
    for per in periodos:
        b = _mes(bd, per)
        dm = dfm[dfm[mg.COL_FECHA].dt.to_period("M") == per]
        vol = b[cfg.COL_TOTAL_LTS].sum(min_count=1)
        ing = b[cfg.COL_TOTAL_VENTA].sum(min_count=1)
        marg = dm["Margen_total"].sum(min_count=1)
        filas.append({"Mes": MES_NOMBRE[per.month].capitalize(),
                      "Volumen": vol, "Ingreso": ing, "Margen": marg,
                      "Margen_pct": 100 * marg / ing if ing else np.nan})
    df = pd.DataFrame(filas)
    v, i, m = df["Volumen"].sum(), df["Ingreso"].sum(), df["Margen"].sum()
    ini, fin = MES_NOMBRE[periodos[0].month][:3], MES_NOMBRE[periodos[-1].month][:3]
    df.loc[len(df)] = {"Mes": f"ACUMULADO {ini.upper()}–{fin.upper()}",
                       "Volumen": v, "Ingreso": i, "Margen": m,
                       "Margen_pct": 100 * m / i if i else np.nan}
    return df


def oportunidad_recuperacion(dfm, per, meses: int = 6, pct: int = 75) -> pd.DataFrame:
    """(MuP_benchmark − MuP_actual) × litros_actual, con benchmark = percentil
    `pct` del margen unitario mensual de la propia estación en los últimos
    `meses` (régimen actual)."""
    per = _p(per)
    periodos = [per - i for i in range(meses)]
    d = dfm[dfm[mg.COL_FECHA].dt.to_period("M").isin(periodos)].copy()
    d["P"] = d[mg.COL_FECHA].dt.to_period("M")
    g = d.groupby([mg.COL_EST, "P"]).agg(mb=("Margen_total", "sum"),
                                         lt=("Litros_total", "sum"))
    g["mu"] = g["mb"] / g["lt"]

    act = dfm[dfm[mg.COL_FECHA].dt.to_period("M") == per]
    mb_a = act.groupby(mg.COL_EST)["Margen_total"].sum(min_count=1)
    lt_a = act.groupby(mg.COL_EST)["Litros_total"].sum(min_count=1)

    filas = []
    for est in mb_a.index:
        serie = g.loc[est, "mu"].dropna()
        if serie.empty or not lt_a.get(est):
            continue
        bench = np.percentile(serie, pct)
        mu_act = mb_a[est] / lt_a[est]
        filas.append({"Estación": est, "MgL_actual": mu_act,
                      "MgL_benchmark": bench,
                      "Oportunidad_$": max(bench - mu_act, 0) * lt_a[est]})
    out = pd.DataFrame(filas).sort_values("Oportunidad_$", ascending=False)
    return out.reset_index(drop=True)
