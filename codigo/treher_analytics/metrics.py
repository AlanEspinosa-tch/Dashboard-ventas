"""
Métricas y agregaciones.

Principio que cruza todo el módulo: cuando la cobertura entre periodos o
estaciones difiere (cierres, altas/bajas), NO se comparan sumas crudas.
Se compara volumen por día operado o se restringe a periodos/estaciones
con cobertura comparable (like-for-like).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.tseries.offsets import MonthEnd

from . import config as cfg

MESES_ABBR = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}


def _filtrar_estacion(bd: pd.DataFrame, estacion: str | None) -> pd.DataFrame:
    if estacion is None:
        return bd
    df = bd[bd[cfg.COL_ESTACION] == estacion]
    if df.empty:
        raise ValueError(f"No hay datos para la estación {estacion!r}")
    return df


# ----------------------------------------------------------------------
# 1. PROMEDIO POR DÍA OPERADO (sustituye la suma cruda sesgada)
# ----------------------------------------------------------------------
def volumen_mensual(bd: pd.DataFrame, estacion: str | None = None) -> pd.DataFrame:
    """
    Por mes: litros totales, días operados y litros por día operado.

    'Lts_por_dia_op' es la métrica honesta para comparar meses con
    distinta cantidad de días abiertos: un mes a medio cerrar ya no
    parece una caída de demanda.
    """
    df = _filtrar_estacion(bd, estacion).copy()
    df["Periodo"] = df[cfg.COL_FECHA].dt.to_period("M").dt.to_timestamp()

    agg = {cfg.LTS[p]: "sum" for p in cfg.PRODUCTOS}
    out = df.groupby("Periodo").agg(**{
        f"{p}_lts": (cfg.LTS[p], "sum") for p in cfg.PRODUCTOS
    })
    out["Total_lts"] = out.sum(axis=1)
    out["Días_operados"] = df.groupby("Periodo")["Operó"].sum()
    out["Lts_por_dia_op"] = out["Total_lts"] / out["Días_operados"].replace(0, np.nan)
    return out.round(1).reset_index()


# ----------------------------------------------------------------------
# 2. PARTICIPACIÓN DE MERCADO (controla el tamaño de flota)
# ----------------------------------------------------------------------
def participacion_mercado(bd: pd.DataFrame, freq: str = "MS") -> pd.DataFrame:
    """
    Share de cada estación sobre el total del grupo, por periodo.
    Al ser proporción, es inmune a que entren o salgan estaciones:
    mide posición relativa, no nivel absoluto.
    """
    df = bd.copy()
    df["Periodo"] = df[cfg.COL_FECHA].dt.to_period(freq[:1]).dt.to_timestamp()
    piv = (
        df.groupby(["Periodo", cfg.COL_ESTACION])[cfg.COL_TOTAL_LTS]
        .sum(min_count=1)
        .unstack(cfg.COL_ESTACION)
    )
    share = piv.div(piv.sum(axis=1), axis=0) * 100
    return share.round(2)


# ----------------------------------------------------------------------
# 3. CRECIMIENTO YoY / MoM LIKE-FOR-LIKE
# ----------------------------------------------------------------------
def crecimiento_lfl(bd: pd.DataFrame, freq: str = "MS") -> pd.DataFrame:
    """
    Crecimiento del grupo comparando SOLO estaciones activas en ambos
    periodos (like-for-like). Evita el espejismo de crecer/caer solo
    porque abrió o cerró una estación.
    """
    df = bd[bd["Operó"]].copy()
    df["Periodo"] = df[cfg.COL_FECHA].dt.to_period(freq[:1]).dt.to_timestamp()

    vol = df.groupby(["Periodo", cfg.COL_ESTACION])[cfg.COL_TOTAL_LTS].sum(min_count=1)
    vol = vol.unstack(cfg.COL_ESTACION)

    periodos = vol.index
    filas = []
    for i in range(1, len(periodos)):
        prev, cur = vol.iloc[i - 1], vol.iloc[i]
        comunes = prev.notna() & cur.notna()
        if comunes.sum() == 0:
            continue
        v_prev, v_cur = prev[comunes].sum(), cur[comunes].sum()
        filas.append({
            "Periodo": periodos[i],
            "Estaciones_LFL": int(comunes.sum()),
            "Lts_periodo": v_cur,
            "Lts_periodo_prev": v_prev,
            "Crec_%": round(100 * (v_cur / v_prev - 1), 2) if v_prev else np.nan,
        })
    return pd.DataFrame(filas)


# ----------------------------------------------------------------------
# 3b. KPIs DE CRECIMIENTO: MoM, YoY, YTD (todos like-for-like)
# ----------------------------------------------------------------------
def _ultimo_mes_completo(bd: pd.DataFrame):
    """Último mes con datos, excluyendo el mes en curso si está incompleto."""
    ult = bd[cfg.COL_FECHA].max()
    per = ult.to_period("M")
    fin_de_su_mes = (ult + MonthEnd(0)).normalize()
    return per if ult.normalize() == fin_de_su_mes else per - 1


def _vol_por_estacion(bd: pd.DataFrame, ini, fin) -> pd.Series:
    """Litros totales por estación entre dos fechas (solo días operados)."""
    m = (bd[cfg.COL_FECHA] >= ini) & (bd[cfg.COL_FECHA] <= fin) & bd["Operó"]
    return bd.loc[m].groupby(cfg.COL_ESTACION)[cfg.COL_TOTAL_LTS].sum(min_count=1)


def _comparar_lfl(actual: pd.Series, base: pd.Series) -> dict:
    """Crecimiento like-for-like: solo estaciones con volumen en AMBOS periodos."""
    comunes = [e for e in actual.index.intersection(base.index)
               if pd.notna(actual[e]) and pd.notna(base[e]) and base[e] > 0]
    v_act, v_base = actual[comunes].sum(), base[comunes].sum()
    crec = 100 * (v_act / v_base - 1) if v_base else np.nan
    return {"Lts_actual": v_act, "Lts_comparación": v_base,
            "Var_%": crec, "Estaciones_LFL": len(comunes)}


def _label_mes(per) -> str:
    return f"{MESES_ABBR[per.month]} {per.year}"


def kpis_crecimiento(bd: pd.DataFrame) -> pd.DataFrame:
    """
    Tabla con los tres indicadores de crecimiento del grupo, like-for-like,
    tomando como referencia el último mes completo:
      - MoM: mes vs. mes anterior
      - YoY: mes vs. mismo mes del año pasado
      - YTD: acumulado enero→mes vs. mismo tramo del año pasado
    """
    mes = _ultimo_mes_completo(bd)
    mes_prev, mes_yoy = mes - 1, mes - 12

    def ventana(per):
        return per.to_timestamp(), per.to_timestamp(how="end").normalize()

    a_ini, a_fin = ventana(mes)
    p_ini, p_fin = ventana(mes_prev)
    y_ini, y_fin = ventana(mes_yoy)

    ytd_ini = pd.Timestamp(year=mes.year, month=1, day=1)
    ytd_prev_ini = pd.Timestamp(year=mes.year - 1, month=1, day=1)

    vol = _vol_por_estacion  # alias corto
    filas = [
        {"Indicador": "MoM (mensual)",
         "Periodo actual": _label_mes(mes),
         "Comparación": _label_mes(mes_prev),
         **_comparar_lfl(vol(bd, a_ini, a_fin), vol(bd, p_ini, p_fin))},
        {"Indicador": "YoY (interanual)",
         "Periodo actual": _label_mes(mes),
         "Comparación": _label_mes(mes_yoy),
         **_comparar_lfl(vol(bd, a_ini, a_fin), vol(bd, y_ini, y_fin))},
        {"Indicador": "YTD (acumulado)",
         "Periodo actual": f"Ene–{MESES_ABBR[mes.month]} {mes.year}",
         "Comparación": f"Ene–{MESES_ABBR[mes.month]} {mes.year - 1}",
         **_comparar_lfl(vol(bd, ytd_ini, a_fin), vol(bd, ytd_prev_ini, y_fin))},
    ]
    return pd.DataFrame(filas)


# ----------------------------------------------------------------------
# 4. PERFIL POR DÍA DE LA SEMANA
# ----------------------------------------------------------------------
def perfil_dia_semana(bd: pd.DataFrame, estacion: str | None = None,
                      vida_media: int = 30,
                      redondear_a: int | None = None,
                      fecha_ref=None) -> pd.DataFrame:
    """
    Litros por día de la semana y producto (solo días operados):
      - Lts_ponderado_3m: promedio ponderado de los últimos 3 meses con
        decaimiento exponencial (vida media `vida_media` días → lo reciente
        pesa más; a 30 días el peso es 50%, a 60 días 25%).
      - Lts_prom_último_mes: promedio simple de los últimos 30 días.
      - Rango_mín / Rango_máx: banda ±1σ alrededor del ponderado (~74% de los
        días caen ahí). La σ se estima con 12 MESES y DESTENDENCIADA (residuos
        respecto a un nivel móvil local): con 3 meses solo hay ~10 datos
        efectivos y σ saldría hasta 40% subestimada → banda muy angosta y
        falsas alertas. El nivel se mide local (reciente), la dispersión global.

    `redondear_a`: si se indica (ej. 100), redondea las cantidades al múltiplo
    MÁS CERCANO (el .5 sube) — útil para planeación operativa.
    `fecha_ref`: fecha de corte. Si se indica, TODOS los cálculos usan solo
    datos anteriores o iguales a esa fecha (línea base congelada "para atrás").
    """
    df = _filtrar_estacion(bd, estacion)
    if fecha_ref is not None:
        fecha_ref = pd.Timestamp(fecha_ref)
        df = df[df[cfg.COL_FECHA] <= fecha_ref]
    fmax = fecha_ref if fecha_ref is not None else df[cfg.COL_FECHA].max()
    d30 = df[df[cfg.COL_FECHA] > fmax - pd.Timedelta(days=30)]
    d90 = df[df[cfg.COL_FECHA] > fmax - pd.Timedelta(days=90)].copy()
    d365 = df[df[cfg.COL_FECHA] > fmax - pd.Timedelta(days=365)]

    # Ponderación exponencial por ANTIGÜEDAD EN DÍAS (no por posición de fila),
    # para que los días cerrados o faltantes no desajusten los pesos.
    # Vida media de 30 días: hace 1 mes pesa 50%, hace 2 meses 25%, etc.
    antig = (fmax - d90[cfg.COL_FECHA]).dt.days
    d90["_peso"] = 0.5 ** (antig / vida_media)

    filas = []
    for prod in cfg.PRODUCTOS:
        col = cfg.LTS[prod]
        prom_mes = d30[d30[col].notna()].groupby("Dia_semana")[col].mean()

        sub = d90[d90[col].notna()].copy()
        sub["_wx"] = sub[col] * sub["_peso"]
        agg = sub.groupby("Dia_semana").agg(wx=("_wx", "sum"), w=("_peso", "sum"))
        ponderado = agg["wx"] / agg["w"].replace(0, np.nan)

        # σ de 12 meses, destendenciada (residuos vs. nivel móvil local).
        sigma = {}
        for dia in range(7):
            s = (d365[(d365["Dia_semana"] == dia) & d365[col].notna()]
                 .sort_values(cfg.COL_FECHA).set_index(cfg.COL_FECHA)[col])
            if len(s) >= 6:
                nivel = s.rolling(5, center=True, min_periods=3).mean()
                sigma[dia] = (s - nivel).std(ddof=1)
            else:
                sigma[dia] = np.nan

        for dia in range(7):
            mu = ponderado.get(dia, np.nan)
            sd = sigma.get(dia, np.nan)
            filas.append({
                "Producto": prod,
                "Día": cfg.DIAS_SEMANA[dia],
                "_orden": dia,
                "Lts_ponderado_3m": round(mu, 1),
                "Lts_prom_último_mes": round(prom_mes.get(dia, np.nan), 1),
                "Rango_mín": round(max(mu - sd, 0), 1) if pd.notna(mu) and pd.notna(sd) else np.nan,
                "Rango_máx": round(mu + sd, 1) if pd.notna(mu) and pd.notna(sd) else np.nan,
            })
    out = pd.DataFrame(filas).sort_values(["Producto", "_orden"])
    out = out.drop(columns="_orden").reset_index(drop=True)

    if redondear_a:
        cols = ["Lts_ponderado_3m", "Lts_prom_último_mes", "Rango_mín", "Rango_máx"]
        # Redondeo al múltiplo más cercano, con el .5 hacia arriba (evita el
        # redondeo "bancario" de numpy, que llevaría 35,850 → 35,800).
        out[cols] = np.floor(out[cols] / redondear_a + 0.5) * redondear_a
    return out


def comparativa_antes_despues(bd: pd.DataFrame, estacion: str, fecha_corte,
                              vida_media: int = 30) -> pd.DataFrame:
    """
    Mide el cambio de ventas por día de la semana a partir de una fecha (ej.
    un suceso). La LÍNEA BASE se congela con datos ≤ fecha_corte (mismo método
    del perfil); el DESPUÉS usa el promedio simple de los días > fecha_corte.

    Columnas: Lts_antes (esperado congelado), Lts_después (real posterior),
    Var_% (contracción/expansión), Dist_σ (a cuántas σ está el nuevo nivel),
    Días_bajo_mín_% (% de días posteriores por debajo del Rango_mín congelado),
    n_después (nº de días posteriores — vigilar que no sea muy chico).
    """
    fecha_corte = pd.Timestamp(fecha_corte)
    base = perfil_dia_semana(bd, estacion, vida_media=vida_media,
                             fecha_ref=fecha_corte)
    df = _filtrar_estacion(bd, estacion)
    despues = df[df[cfg.COL_FECHA] > fecha_corte]

    filas = []
    for prod in cfg.PRODUCTOS:
        col = cfg.LTS[prod]
        bp = base[base["Producto"] == prod].set_index("Día")
        for dia in range(7):
            dname = cfg.DIAS_SEMANA[dia]
            if dname not in bp.index:
                continue
            mu_a = bp.loc[dname, "Lts_ponderado_3m"]
            mn_a = bp.loc[dname, "Rango_mín"]
            sd_a = bp.loc[dname, "Rango_máx"] - mu_a          # σ superior (sin recorte)
            dd = despues[(despues["Dia_semana"] == dia) & despues[col].notna()][col]
            n = len(dd)
            mu_d = dd.mean() if n else np.nan
            filas.append({
                "Producto": prod, "Día": dname, "_orden": dia,
                "Lts_antes": round(mu_a, 0) if pd.notna(mu_a) else np.nan,
                "Lts_después": round(mu_d, 0) if n else np.nan,
                "Var_%": round(100 * (mu_d / mu_a - 1), 1) if n and mu_a else np.nan,
                "Dist_σ": round((mu_d - mu_a) / sd_a, 2) if n and sd_a else np.nan,
                "Días_bajo_mín_%": round(100 * (dd < mn_a).mean(), 0) if n else np.nan,
                "n_después": n,
            })
    out = pd.DataFrame(filas).sort_values(["Producto", "_orden"])
    return out.drop(columns="_orden").reset_index(drop=True)


def comparativa_antes_despues_total(bd, estacion, fecha_corte,
                                    vida_media: int = 30) -> pd.DataFrame:
    """
    Igual que `comparativa_antes_despues` pero SIN desglosar por combustible:
    el total de la estación por día de la semana, más una fila SEMANA que suma
    los siete días — es decir, cuánto vende en una semana promedio antes vs.
    después del corte.

    La línea base se congela con datos ≤ fecha_corte (ponderado 3 meses con
    decaimiento exponencial); la σ viene de 12 meses destendenciados.
    """
    fecha_corte = pd.Timestamp(fecha_corte)
    df = _filtrar_estacion(bd, estacion)
    hist = df[df[cfg.COL_FECHA] <= fecha_corte]
    col = cfg.COL_TOTAL_LTS

    d90 = hist[hist[cfg.COL_FECHA] > fecha_corte - pd.Timedelta(days=90)].copy()
    d90["_peso"] = 0.5 ** ((fecha_corte - d90[cfg.COL_FECHA]).dt.days / vida_media)
    d365 = hist[hist[cfg.COL_FECHA] > fecha_corte - pd.Timedelta(days=365)]
    despues = df[df[cfg.COL_FECHA] > fecha_corte]

    filas, sd2_sem, ant_sem, des_sem, n_sem = [], 0.0, 0.0, 0.0, 0
    for dia in range(7):
        s = d90[(d90["Dia_semana"] == dia) & d90[col].notna()]
        w = s["_peso"].sum()
        mu_a = (s[col] * s["_peso"]).sum() / w if w else np.nan

        # σ de 12 meses destendenciada (mismo método del perfil)
        h = (d365[(d365["Dia_semana"] == dia) & d365[col].notna()]
             .sort_values(cfg.COL_FECHA).set_index(cfg.COL_FECHA)[col])
        sd_a = ((h - h.rolling(5, center=True, min_periods=3).mean()).std(ddof=1)
                if len(h) >= 6 else np.nan)

        dd = despues[(despues["Dia_semana"] == dia) & despues[col].notna()][col]
        n = len(dd)
        mu_d = dd.mean() if n else np.nan
        mn_a = max(mu_a - sd_a, 0) if pd.notna(mu_a) and pd.notna(sd_a) else np.nan

        filas.append({
            "Día": cfg.DIAS_SEMANA[dia],
            "Lts_antes": round(mu_a, 0) if pd.notna(mu_a) else np.nan,
            "Lts_después": round(mu_d, 0) if n else np.nan,
            "Var_%": round(100 * (mu_d / mu_a - 1), 1) if n and mu_a else np.nan,
            "Dist_σ": round((mu_d - mu_a) / sd_a, 2)
                      if n and pd.notna(sd_a) and sd_a else np.nan,
            "Días_bajo_mín_%": round(100 * (dd < mn_a).mean(), 0)
                               if n and pd.notna(mn_a) else np.nan,
            "n_después": n,
        })
        if pd.notna(mu_a):
            ant_sem += mu_a
        if n:
            des_sem += mu_d
            n_sem += n
        if pd.notna(sd_a):
            sd2_sem += sd_a ** 2

    # Fila SEMANA: la venta de una semana promedio (suma de los siete días).
    # σ semanal = √(Σ σ²) suponiendo independencia entre días.
    sd_sem = np.sqrt(sd2_sem) if sd2_sem else np.nan
    filas.append({
        "Día": "SEMANA PROMEDIO",
        "Lts_antes": round(ant_sem, 0) if ant_sem else np.nan,
        "Lts_después": round(des_sem, 0) if des_sem else np.nan,
        "Var_%": round(100 * (des_sem / ant_sem - 1), 1) if ant_sem and des_sem else np.nan,
        "Dist_σ": round((des_sem - ant_sem) / sd_sem, 2)
                  if des_sem and pd.notna(sd_sem) and sd_sem else np.nan,
        "Días_bajo_mín_%": np.nan,
        "n_después": n_sem,
    })
    return pd.DataFrame(filas)


# ----------------------------------------------------------------------
# 4b. KPIs DE VENTAS (mix, precio realizado, proyección de cierre)
# ----------------------------------------------------------------------
def mix_volumen(bd: pd.DataFrame, estacion: str | None = None,
                anio: int | None = None) -> pd.DataFrame:
    """
    Participación de cada producto en el volumen (y penetración Premium).
    Si `anio` se indica, se limita a ese año (acumulado del año).
    """
    g = _filtrar_estacion(bd, estacion)
    if anio is not None:
        g = g[g[cfg.COL_ANIO] == anio]
    tot = {p: g[cfg.LTS[p]].sum(min_count=1) for p in cfg.PRODUCTOS}
    s = sum(v for v in tot.values() if pd.notna(v))
    return pd.DataFrame([
        {"Producto": p, "Litros": tot[p],
         "% del volumen": 100 * tot[p] / s if s else np.nan}
        for p in cfg.PRODUCTOS
    ])


def precio_realizado(bd: pd.DataFrame, estacion: str | None = None) -> pd.DataFrame:
    """
    Precio efectivo ($/L) por producto en tres momentos:
      - inicio de año (promedio de la 1ª semana de enero del año vigente),
      - mes pasado completo (promedio),
      - más reciente (el último dato disponible, valor único).
    """
    g = _filtrar_estacion(bd, estacion)
    fmax = g[cfg.COL_FECHA].max()
    anio = fmax.year
    ene = g[(g[cfg.COL_FECHA] >= pd.Timestamp(anio, 1, 1)) &
            (g[cfg.COL_FECHA] <= pd.Timestamp(anio, 1, 7))]
    mes_ant = fmax.to_period("M") - 1
    prev = g[g[cfg.COL_FECHA].dt.to_period("M") == mes_ant]

    def _prom(sub, p):
        lts = sub[cfg.LTS[p]].sum(min_count=1)
        imp = (sub[cfg.LTS[p]] * sub[cfg.PRECIO[p]]).sum(min_count=1)
        return imp / lts if lts else np.nan

    filas = []
    for p in cfg.PRODUCTOS:
        reciente = g[g[cfg.PRECIO[p]].notna()].sort_values(cfg.COL_FECHA)
        p_rec = reciente[cfg.PRECIO[p]].iloc[-1] if not reciente.empty else np.nan
        filas.append({
            "Producto": p,
            "Inicio_año (prom 1ª sem ene)": _prom(ene, p),
            f"Mes_pasado {mes_ant} (prom)": _prom(prev, p),
            "Más_reciente": p_rec,
        })
    return pd.DataFrame(filas)


def proyeccion_cierre_mes(bd: pd.DataFrame, estacion: str | None = None) -> pd.DataFrame:
    """
    Run-rate: con lo que va del mes en curso, proyecta el cierre del mes
    (litros) usando el promedio por día operado. Compara vs. el mes anterior.
    """
    g = _filtrar_estacion(bd, estacion)
    ult = g[cfg.COL_FECHA].max()
    ini_mes = ult.to_period("M").to_timestamp()
    dias_en_mes = (ini_mes + MonthEnd(0)).day

    mes = g[(g[cfg.COL_FECHA] >= ini_mes) & g["Operó"]]
    dias_op = mes[cfg.COL_FECHA].nunique()
    lts_acum = mes[cfg.COL_TOTAL_LTS].sum(min_count=1)
    lts_dia = lts_acum / dias_op if dias_op else np.nan
    proyeccion = lts_dia * dias_en_mes

    prev_per = ini_mes.to_period("M") - 1
    prev = g[(g[cfg.COL_FECHA] >= prev_per.to_timestamp()) &
             (g[cfg.COL_FECHA] <= prev_per.to_timestamp(how="end"))]
    lts_prev = prev[cfg.COL_TOTAL_LTS].sum(min_count=1)

    return pd.DataFrame([{
        "Mes_en_curso": ini_mes.strftime("%Y-%m"),
        "Días_operados": dias_op,
        "Litros_acumulados": lts_acum,
        "Litros/día_op": lts_dia,
        "Proyección_cierre": proyeccion,
        "Mes_anterior": lts_prev,
        "Var_vs_mes_ant_%": 100 * (proyeccion / lts_prev - 1) if lts_prev else np.nan,
    }])


# ----------------------------------------------------------------------
# 5. DETECCIÓN DE ANOMALÍAS (alertas diarias)
# ----------------------------------------------------------------------
def anomalias(
    bd: pd.DataFrame,
    estacion: str,
    producto: str = "Diésel",
    ventana: int = 28,
    z: float = 3.5,
) -> pd.DataFrame:
    """
    Marca días anómalos con el z-score MODIFICADO (mediana/MAD), más robusto
    que media/desviación: los propios outliers no inflan el umbral, así que
    no se 'esconden' unos a otros. Solo días operados.

    z_mod = 0.6745 * (x - mediana_móvil) / MAD_móvil
    El umbral 3.5 es el estándar (Iglewicz & Hoaglin) para este estimador.
    """
    col = cfg.LTS[producto]
    df = _filtrar_estacion(bd, estacion).sort_values(cfg.COL_FECHA)
    s = df[[cfg.COL_FECHA, col]].dropna().copy()

    minp = ventana // 2
    mediana = s[col].rolling(ventana, min_periods=minp).median()
    mad = (s[col] - mediana).abs().rolling(ventana, min_periods=minp).median()
    s["z_mod"] = 0.6745 * (s[col] - mediana) / mad.replace(0, np.nan)
    s["Anómalo"] = s["z_mod"].abs() > z
    s["Tipo"] = np.where(s["z_mod"] > 0, "Pico", "Caída")
    return s[s["Anómalo"]].round(2).reset_index(drop=True)


# ----------------------------------------------------------------------
# 6. RANKING DE ESTACIONES (like-for-like en una ventana)
# ----------------------------------------------------------------------
def ranking_estaciones(bd: pd.DataFrame, ultimos_dias: int = 30,
                       tolerancia_baja: int = 60) -> pd.DataFrame:
    """
    Ranking por litros/día operado en una ventana COMPARABLE para todas las
    estaciones. El fin de la ventana se fija en la última fecha de la estación
    vigente MENOS actualizada (no en 'hoy'), para que ninguna quede con 30
    días y otra con 3.

    Se excluyen estaciones DADAS DE BAJA (su última venta quedó más de
    `tolerancia_baja` días atrás del máximo global), para que una estación
    muerta no arrastre la ventana al pasado.
    En df.attrs['ventana'] quedan las fechas usadas.
    """
    ultima_por_est = bd[bd["Operó"]].groupby(cfg.COL_ESTACION)[cfg.COL_FECHA].max()
    max_global = ultima_por_est.max()
    vigentes = ultima_por_est[
        ultima_por_est >= max_global - pd.Timedelta(days=tolerancia_baja)
    ]
    fin = vigentes.min()                        # estación vigente menos actualizada
    ini = fin - pd.Timedelta(days=ultimos_dias)
    df = bd[(bd[cfg.COL_FECHA] > ini) & (bd[cfg.COL_FECHA] <= fin) &
            bd["Operó"] & bd[cfg.COL_ESTACION].isin(vigentes.index)]

    out = df.groupby(cfg.COL_ESTACION).agg(
        Días_operados=("Operó", "sum"),
        Lts_totales=(cfg.COL_TOTAL_LTS, "sum"),
        Venta_total=(cfg.COL_TOTAL_VENTA, "sum"),
    )
    out["Lts_por_dia_op"] = (out["Lts_totales"] / out["Días_operados"]).round(0)
    out = out.sort_values("Lts_por_dia_op", ascending=False).round(1).reset_index()
    out.attrs["ventana"] = (ini.date(), fin.date())
    return out


def promedio_ponderado_estaciones(bd: pd.DataFrame, bloque: int = 28,
                                  n_bloques: int = 3) -> pd.DataFrame:
    """
    Promedio ponderado de litros POR DÍA (últimos ~3 meses), por estación y
    combustible, más el total. Filas = estaciones.

    Ponderación por BLOQUES de `bloque` días (28 = 4 semanas, múltiplo de 7 →
    cada bloque tiene igual nº de cada día de la semana, sin sesgo). Todos los
    días de un bloque pesan igual; cada bloque pesa la mitad del anterior
    (0.5^bloque → reparto ≈ 57% / 29% / 14% para 3 bloques).
    """
    fmax = bd[cfg.COL_FECHA].max()
    ventana = bloque * n_bloques
    d = bd[bd[cfg.COL_FECHA] > fmax - pd.Timedelta(days=ventana)].copy()
    antig = (fmax - d[cfg.COL_FECHA]).dt.days
    d["_peso"] = 0.5 ** (antig // bloque)          # bloque 0,1,2 → peso 1, .5, .25

    filas = []
    for est, g in d.groupby(cfg.COL_ESTACION):
        fila = {cfg.COL_ESTACION: est}
        total = 0.0
        for prod in cfg.PRODUCTOS:
            col = cfg.LTS[prod]
            sub = g[g[col].notna()]
            w = sub["_peso"].sum()
            val = (sub[col] * sub["_peso"]).sum() / w if w else np.nan
            fila[prod] = round(val, 0) if pd.notna(val) else np.nan
            total += val if pd.notna(val) else 0
        fila["Total"] = round(total, 0)
        filas.append(fila)

    out = pd.DataFrame(filas).sort_values("Total", ascending=False).reset_index(drop=True)
    tot = {cfg.COL_ESTACION: "TOTAL"}
    for c in cfg.PRODUCTOS + ["Total"]:
        tot[c] = out[c].sum()
    return pd.concat([out, pd.DataFrame([tot])], ignore_index=True)


def ranking_grupo(bd: pd.DataFrame) -> pd.DataFrame:
    """
    Ranking del grupo que combina el litros/día operado (ventana comparable)
    con las cifras del MES ANTERIOR completo: participación de mercado, litros
    totales y venta ($). Incluye fila TOTAL al final.
    """
    base = ranking_estaciones(bd, 30)
    ventana = base.attrs.get("ventana")
    per = _ultimo_mes_completo(bd)

    mes = bd[bd[cfg.COL_FECHA].dt.to_period("M") == per]
    grp = mes.groupby(cfg.COL_ESTACION).agg(
        Litros_mes_ant=(cfg.COL_TOTAL_LTS, "sum"),
        Venta_mes_ant=(cfg.COL_TOTAL_VENTA, "sum"),
    ).reset_index()
    total_lts = grp["Litros_mes_ant"].sum()
    grp["Participación_%_mes_ant"] = (100 * grp["Litros_mes_ant"] / total_lts).round(1)

    out = base[[cfg.COL_ESTACION, "Lts_por_dia_op"]].merge(
        grp, on=cfg.COL_ESTACION, how="left")
    out = out[[cfg.COL_ESTACION, "Lts_por_dia_op", "Participación_%_mes_ant",
               "Litros_mes_ant", "Venta_mes_ant"]]
    out = out.sort_values("Litros_mes_ant", ascending=False).reset_index(drop=True)

    total = pd.DataFrame([{
        cfg.COL_ESTACION: "TOTAL",
        "Lts_por_dia_op": np.nan,
        "Participación_%_mes_ant": round(out["Participación_%_mes_ant"].sum(), 1),
        "Litros_mes_ant": out["Litros_mes_ant"].sum(),
        "Venta_mes_ant": out["Venta_mes_ant"].sum(),
    }])
    out = pd.concat([out, total], ignore_index=True)
    out.attrs["ventana"] = ventana
    out.attrs["periodo"] = per
    return out


# ----------------------------------------------------------------------
# 7. VARIABILIDAD DE PRECIOS
# ----------------------------------------------------------------------
def variacion_precios(bd: pd.DataFrame, estacion: str) -> pd.DataFrame:
    """Magnitud y frecuencia de cambios de precio por producto."""
    df = _filtrar_estacion(bd, estacion).sort_values(cfg.COL_FECHA)
    filas = []
    for prod in cfg.PRODUCTOS:
        col = cfg.PRECIO[prod]
        datos = df[[cfg.COL_FECHA, col]].dropna()
        difs = datos[col].diff().abs()
        difs = difs[difs > 0]
        if difs.empty:
            continue
        filas.append({
            "Producto": prod,
            "Cambio_promedio": round(difs.mean(), 4),
            "Cambio_máximo": round(difs.max(), 4),
            "N_cambios": int(len(difs)),
        })
    return pd.DataFrame(filas)
