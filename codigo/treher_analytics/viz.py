"""
Gráficas reutilizables. Todas devuelven una figura de matplotlib (no llaman
a plt.show()), para poder mostrarlas en Streamlit o exportarlas a PDF.
"""

from __future__ import annotations

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from . import config as cfg
from . import data as dta
from . import margenes as mgn

MESES_ABBR = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
              7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"}

# Colores para barras apiladas (negro/rojo/verde, como pediste).
COLORES_BARRA = {"Diésel": "#1A1A1A", "Premium": "#C1121F", "Regular": "#5BBA6F"}


def _fmt_lts(x, _pos):
    if abs(x) >= 1_000_000:
        return f"{x / 1_000_000:.1f}M"
    if abs(x) >= 10_000:
        return f"{x / 1_000:.0f}k"          # 35k, 40k…
    if abs(x) >= 1_000:
        return f"{x / 1_000:.1f}k"          # 2.4k, 2.6k… (evita repetir "2k")
    return f"{x:.0f}"


def _compacto(v, money=False):
    s = "$" if money else ""
    if abs(v) >= 1_000_000:
        return f"{s}{v / 1_000_000:,.1f}M"
    if abs(v) >= 1_000:
        return f"{s}{v / 1_000:,.0f}k"
    return f"{s}{v:,.0f}"


def _formato_fechas(ax):
    """Eje X de fechas: muchas marcas pero rotadas para que no se encimen."""
    loc = mdates.AutoDateLocator(minticks=8, maxticks=16)
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
    ax.tick_params(axis="x", labelsize=8, rotation=45)
    for lbl in ax.get_xticklabels():
        lbl.set_ha("right")


def _etiqueta_mes(periodo) -> str:
    return f"{MESES_ABBR[periodo.month]} {str(periodo.year)[2:]}"


def _formato_fechas_dias(ax, objetivo_ticks: int = 20):
    """
    Eje X marcado por DÍA con intervalo adaptativo: cada 2 días en rangos
    cortos (~5 semanas se ven 19, 21, 23…) y se ensancha solo en rangos
    largos para no saturar. Formato compacto '19-jul', rotado.
    """
    lo, hi = ax.get_xlim()                        # números de fecha matplotlib = días
    n_dias = max(1, hi - lo)
    interval = max(2, int(np.ceil(n_dias / objetivo_ticks)))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=interval))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d-%b"))
    ax.tick_params(axis="x", labelsize=8, rotation=45)
    for lbl in ax.get_xticklabels():
        lbl.set_ha("right")


def _barras_apiladas(meses, alturas, etiquetas_int, total, titulo, ylabel, money):
    """Núcleo de las barras apiladas mensuales por combustible + línea total."""
    n = len(meses)
    fig, ax = plt.subplots(figsize=(max(11, n * 0.62), 6.5))
    x = np.arange(n)
    bottom = np.zeros(n)
    maxtot = np.nanmax(total) if n else 1

    for fuel in ["Diésel", "Premium", "Regular"]:
        h = np.nan_to_num(alturas[fuel])
        ax.bar(x, h, bottom=bottom, color=COLORES_BARRA[fuel], label=fuel,
               width=0.72, zorder=3)
        txt_color = "black" if fuel == "Regular" else "white"
        for xi in range(n):
            if h[xi] > maxtot * 0.04 and etiquetas_int[fuel][xi]:
                ax.text(x[xi], bottom[xi] + h[xi] / 2, etiquetas_int[fuel][xi],
                        ha="center", va="center", fontsize=7, rotation=90,
                        color=txt_color, zorder=5)
        bottom = bottom + h

    # Línea de total con etiquetas (rotadas para no encimarse).
    ax.plot(x, total, color="#0F6E56", lw=2, marker="o", markersize=4, zorder=4)
    for xi in range(n):
        ax.annotate(_compacto(total[xi], money), (x[xi], total[xi]),
                    xytext=(0, 9), textcoords="offset points", ha="center",
                    fontsize=7, fontweight="bold", rotation=45, zorder=6)

    ax.set_ylim(0, maxtot * 1.28)
    ax.set_xticks(x)
    ax.set_xticklabels(meses, rotation=45, ha="right", fontsize=8)
    ax.set_title(titulo, fontsize=13, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_lts))
    ax.legend(loc="upper left", fontsize=9, ncol=3)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    return fig


def barras_margen_historico(dfm, anios):
    """
    Barras apiladas mensuales de MARGEN BRUTO ($) por combustible.
    Altura de cada sub-barra = margen bruto total del combustible ese mes.
    Etiqueta interna = margen PROMEDIO ($/L) de ese combustible ese mes.
    Línea = margen bruto total de los 3 combustibles.
    """
    g = dfm[dfm["Año"].isin(anios)].copy()
    if g.empty:
        raise ValueError("Sin datos de margen para los años elegidos.")
    g["P"] = g[mgn.COL_FECHA].dt.to_period("M")
    meses = sorted(g["P"].unique())

    alturas, etiquetas = {}, {}
    for fuel in mgn.PRODUCTOS:
        mb = g.groupby("P")[mgn.MB[fuel]].sum(min_count=1).reindex(meses)
        lts = g.groupby("P")[mgn.LTS[fuel]].sum(min_count=1).reindex(meses)
        mgl = mb / lts
        alturas[fuel] = mb.values
        etiquetas[fuel] = [f"${v:,.2f}" if pd.notna(v) else "" for v in mgl.values]

    total = np.nansum([alturas[f] for f in mgn.PRODUCTOS], axis=0)
    meses_lbl = [_etiqueta_mes(p) for p in meses]
    return _barras_apiladas(
        meses_lbl, alturas, etiquetas, total,
        "Margen bruto mensual por combustible  ·  etiqueta interna = margen promedio $/L",
        "Margen bruto ($)", money=True)


def barras_litros_historico(bd, anios):
    """
    Barras apiladas mensuales de LITROS por combustible.
    Altura y etiqueta interna = litros vendidos del combustible ese mes.
    Línea = litros totales de los 3 combustibles.
    """
    g = bd[bd[cfg.COL_ANIO].isin(anios)].copy()
    if g.empty:
        raise ValueError("Sin datos de litros para los años elegidos.")
    g["P"] = g[cfg.COL_FECHA].dt.to_period("M")
    meses = sorted(g["P"].unique())

    alturas, etiquetas = {}, {}
    for fuel in cfg.PRODUCTOS:
        lts = g.groupby("P")[cfg.LTS[fuel]].sum(min_count=1).reindex(meses)
        alturas[fuel] = lts.values
        etiquetas[fuel] = [_compacto(v) if pd.notna(v) else "" for v in lts.values]

    total = np.nansum([alturas[f] for f in cfg.PRODUCTOS], axis=0)
    meses_lbl = [_etiqueta_mes(p) for p in meses]
    return _barras_apiladas(
        meses_lbl, alturas, etiquetas, total,
        "Litros vendidos por mes y combustible",
        "Litros", money=False)


def evolucion_estacion(bd, estacion, ventana_ma: int = 14, anios=None):
    """Litros, precio e ingreso diarios por producto, con media móvil."""
    df = bd[bd[cfg.COL_ESTACION] == estacion].sort_values(cfg.COL_FECHA)
    if anios is not None:
        df = df[df[cfg.COL_ANIO].isin(anios)]
    if df.empty:
        raise ValueError(f"No hay datos para {estacion!r} en los años elegidos")

    # sharex=False -> cada panel muestra su propio eje X con fechas.
    fig, axes = plt.subplots(len(cfg.PRODUCTOS), 1, figsize=(13, 11), sharex=False)
    for ax, prod in zip(axes, cfg.PRODUCTOS):
        col, color = cfg.LTS[prod], cfg.COLOR[prod]
        ax.plot(df[cfg.COL_FECHA], df[col], color=color, lw=1.1, alpha=0.5)
        ma = df[col].rolling(ventana_ma, min_periods=ventana_ma // 2).mean()
        ax.plot(df[cfg.COL_FECHA], ma, color=color, lw=2.2, ls="--",
                label=f"Media móvil {ventana_ma}d")
        ax.set_title(f"{prod} — Litros diarios", fontsize=11, fontweight="bold")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_lts))
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8, loc="upper left")
        _formato_fechas(ax)
    fig.suptitle(f"Evolución de volumen — {estacion}", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.subplots_adjust(hspace=0.45)  # separación para que no se peguen
    return fig


def graficas_residuos(resid, fitted, titulo="", dw=None):
    """
    Diagnóstico visual de residuos (4 paneles). Con N grande las pruebas
    formales rechazan casi siempre; estas gráficas permiten juzgar a ojo:
      1) Residuos en el tiempo
      2) Heterocedasticidad: residuos vs. ajustados (buscar embudo)
      3) Autocorrelación (ACF) — equivalente visual de Durbin-Watson
      4) Normalidad: Q-Q plot (robusto al tamaño de muestra)
    """
    from statsmodels.graphics.tsaplots import plot_acf
    from scipy import stats

    resid = pd.Series(resid).reset_index(drop=True)
    fitted = pd.Series(fitted).reset_index(drop=True)

    fig, axs = plt.subplots(2, 2, figsize=(12, 8))
    if titulo:
        fig.suptitle(f"Diagnóstico de residuos — {titulo}", fontsize=13, fontweight="bold")

    # 1) Residuos en el tiempo
    axs[0, 0].plot(resid, color="#185FA5", lw=0.7, alpha=0.8)
    axs[0, 0].axhline(0, color="#A32D2D", ls="--", lw=1)
    axs[0, 0].set_title("1. Residuos en el tiempo", fontsize=10)
    axs[0, 0].set_xlabel("Observación"); axs[0, 0].set_ylabel("Residuo")

    # 2) Heterocedasticidad
    axs[0, 1].scatter(fitted, resid, s=9, alpha=0.35, color="#185FA5")
    axs[0, 1].axhline(0, color="#A32D2D", ls="--", lw=1)
    axs[0, 1].set_title("2. Heterocedasticidad: residuos vs. ajustados", fontsize=10)
    axs[0, 1].set_xlabel("Ajustado (ŷ)"); axs[0, 1].set_ylabel("Residuo")

    # 3) Autocorrelación (ACF) — visual de Durbin-Watson
    plot_acf(resid, lags=30, ax=axs[1, 0], color="#185FA5")
    titulo_acf = "3. Autocorrelación (ACF)"
    if dw is not None:
        titulo_acf += f"  ·  DW = {dw:.2f}"
    axs[1, 0].set_title(titulo_acf, fontsize=10)
    axs[1, 0].set_xlabel("Rezago"); axs[1, 0].set_ylabel("Correlación")

    # 4) Normalidad (Q-Q plot)
    stats.probplot(resid, dist="norm", plot=axs[1, 1])
    axs[1, 1].get_lines()[0].set(marker="o", markersize=3, alpha=0.4,
                                 color="#185FA5")
    axs[1, 1].get_lines()[1].set(color="#A32D2D", lw=1.4)
    axs[1, 1].set_title("4. Normalidad: Q-Q plot", fontsize=10)

    for ax in axs.flat:
        ax.grid(alpha=0.25)
    fig.tight_layout(rect=[0, 0, 1, 0.96] if titulo else None)
    return fig


def _estilo_ejecutivo(ax):
    """Estilo limpio: sin bordes superiores/derechos, cuadrícula tenue en Y."""
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color("#C9C9C9")
    ax.grid(axis="y", alpha=0.25, lw=0.6)
    ax.grid(axis="x", visible=False)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_lts))
    ax.tick_params(colors="#666", labelsize=8)


def grafico_pronostico(fc, estacion, producto, dias_hist: int = 61):
    """
    Vista ejecutiva: últimos `dias_hist` días de histórico + pronóstico con
    banda 95%. Puntos por día y líneas punteadas para no saturar; una línea
    vertical marca el corte entre histórico y pronóstico.
    """
    hist = fc[fc["Tipo"] == "Histórico"].tail(dias_hist)
    fut = fc[fc["Tipo"] == "Pronóstico"]
    color = cfg.COLOR.get(producto, "#185FA5")
    corte = hist[cfg.COL_FECHA].max()

    fig, ax = plt.subplots(figsize=(13, 4.8))

    # Banda 95% en el HISTÓRICO (gris) y en el PRONÓSTICO (color)
    if hist["LI"].notna().any():
        ax.fill_between(hist[cfg.COL_FECHA], hist["LI"], hist["LS"],
                        color="#9A9A9A", alpha=0.15, lw=0, label="Rango 95% (ajuste)")
    ax.fill_between(fut[cfg.COL_FECHA], fut["LI"], fut["LS"],
                    color=color, alpha=0.16, lw=0, label="Rango 95% (pronóstico)")

    # Histórico: puntos intensos + línea punteada
    ax.plot(hist[cfg.COL_FECHA], hist["Litros"], color="#5C5C5C", lw=1.0,
            ls=":", marker="o", ms=5, alpha=1.0, label="Real")

    # Corte "hoy"
    ax.axvline(corte, color="#BDBDBD", lw=1, ls="--", zorder=1)
    ax.annotate("hoy", xy=(corte, ax.get_ylim()[1]), xytext=(4, -10),
                textcoords="offset points", fontsize=8, color="#999")

    # Pronóstico: puntos intensos + línea punteada del color del producto
    ax.plot(fut[cfg.COL_FECHA], fut["Litros"], color=color, lw=1.8,
            ls="--", marker="o", ms=5.5, label="Pronóstico")

    ax.set_title(f"Pronóstico de litros — {estacion} · {producto}",
                 fontsize=13, fontweight="bold", color="#333", pad=12)
    _estilo_ejecutivo(ax)
    ax.legend(fontsize=8, loc="upper left", ncol=4, frameon=False)
    _formato_fechas_dias(ax)
    fig.tight_layout()
    return fig


def grafico_perfil_vigilancia(bd, estacion, perfil, semanas: int = 8):
    """
    Vista ejecutiva por combustible: ventas diarias de las últimas `semanas`
    contra el RANGO típico por día de la semana (de la tabla de perfil).
    El área sombreada = ±1σ. Cada día se colorea: azul (dentro de ±1σ),
    ÁMBAR (fuera de ±1σ) y ROJO (fuera de ±2σ = realmente inusual).
    """
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    AZUL, AMBAR, ROJO, GRIS = "#2F6DB5", "#E8A317", "#C1121F", "#8A8A8A"
    df = bd[bd[cfg.COL_ESTACION] == estacion].sort_values(cfg.COL_FECHA)
    fmax = df[cfg.COL_FECHA].max()
    d = df[df[cfg.COL_FECHA] > fmax - pd.Timedelta(days=semanas * 7)].copy()
    d["Día"] = d[cfg.COL_FECHA].dt.weekday.map(cfg.DIAS_SEMANA)

    fig, axes = plt.subplots(len(cfg.PRODUCTOS), 1, figsize=(13, 10.5), sharex=False)
    for ax, prod in zip(axes, cfg.PRODUCTOS):
        col = cfg.LTS[prod]
        p = perfil[perfil["Producto"] == prod].set_index("Día")
        s = d[[cfg.COL_FECHA, col, "Día"]].copy()
        s["mn"] = s["Día"].map(p["Rango_mín"])
        s["mx"] = s["Día"].map(p["Rango_máx"])
        s["ce"] = s["Día"].map(p["Lts_ponderado_3m"])
        val = s[col]
        sig = (s["mx"] - s["ce"])                 # σ del lado superior (sin recorte)
        dev = (val - s["ce"]).abs()

        # Banda ±1σ escalonada (sin la línea de "esperado", que hacía ruido)
        ax.fill_between(s[cfg.COL_FECHA], s["mn"], s["mx"], step="mid",
                        color=AZUL, alpha=0.12, lw=0)
        ax.plot(s[cfg.COL_FECHA], val, color=GRIS, lw=0.7, ls=":", zorder=2)

        # Clasificación de cada día
        dentro = val.notna() & (dev <= sig)
        amber = val.notna() & (dev > sig) & (dev <= 2 * sig)
        rojo = val.notna() & (dev > 2 * sig)
        ax.scatter(s.loc[dentro, cfg.COL_FECHA], val[dentro], color=AZUL, s=14, zorder=3)
        ax.scatter(s.loc[amber, cfg.COL_FECHA], val[amber], color=AMBAR, s=26, zorder=4)
        ax.scatter(s.loc[rojo, cfg.COL_FECHA], val[rojo], color=ROJO, s=34, zorder=5)

        # Márgenes para que ningún punto/banda se recorte
        lo = np.nanmin([s["mn"].min(), val.min()])
        hi = np.nanmax([s["mx"].max(), val.max()])
        rng = (hi - lo) or hi
        ax.set_ylim(max(0, lo - rng * 0.08), hi + rng * 0.12)

        ax.set_title(f"{prod}", fontsize=12, fontweight="bold",
                     color=cfg.COLOR.get(prod, "#333"), loc="left", pad=6)
        _estilo_ejecutivo(ax)
        _formato_fechas_dias(ax)

    # Leyenda ÚNICA para toda la figura (evita choques con los datos)
    handles = [
        Patch(facecolor=AZUL, alpha=0.12, label="Rango típico (±1σ)"),
        Line2D([0], [0], marker="o", ls="", color=AZUL, label="Dentro de ±1σ"),
        Line2D([0], [0], marker="o", ls="", color=AMBAR, label="Fuera de ±1σ"),
        Line2D([0], [0], marker="o", ls="", color=ROJO, label="Fuera de ±2σ"),
    ]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.965),
               ncol=4, frameon=False, fontsize=9)
    fig.suptitle(f"Ventas diarias vs. rango típico — {estacion} "
                 f"(últimas {semanas} semanas)", fontsize=13, fontweight="bold", y=1.0)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.subplots_adjust(hspace=0.45)
    return fig


def consolidado_con_flota(bd, anios=None):
    """
    Total del grupo por día CON el número de estaciones activas sobreimpuesto.
    Así una caída del total se lee correctamente: ¿bajó la demanda o solo
    hay menos estaciones abiertas?
    """
    if anios is not None:
        bd = bd[bd[cfg.COL_ANIO].isin(anios)]
    diario = (
        bd.groupby(cfg.COL_FECHA)[cfg.COL_TOTAL_LTS]
        .sum(min_count=1)
        .rename("Total_lts")
        .reset_index()
    )
    activas = dta.estaciones_activas_por_fecha(bd)
    df = diario.merge(activas, on=cfg.COL_FECHA, how="left")
    df["Lts_por_estacion"] = df["Total_lts"] / df["Estaciones_activas"]

    # sharex=False -> cada panel con su propio eje X de fechas.
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), sharex=False)

    color = cfg.COLOR["Total"]
    ax1.plot(df[cfg.COL_FECHA], df["Total_lts"], color=color, lw=1, alpha=0.5)
    ax1.plot(df[cfg.COL_FECHA],
             df["Total_lts"].rolling(14, min_periods=7).mean(),
             color=color, lw=2.2, ls="--", label="Media móvil 14d")
    axb = ax1.twinx()
    axb.fill_between(df[cfg.COL_FECHA], df["Estaciones_activas"],
                     color="#999", alpha=0.15, step="mid")
    axb.set_ylabel("Estaciones activas", color="#777")
    axb.set_ylim(0, df["Estaciones_activas"].max() + 1)
    ax1.set_title("Total del grupo (litros/día) vs. estaciones activas",
                  fontsize=12, fontweight="bold")
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_lts))
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(alpha=0.25)
    _formato_fechas(ax1)

    ax2.plot(df[cfg.COL_FECHA],
             df["Lts_por_estacion"].rolling(14, min_periods=7).mean(),
             color="#185FA5", lw=2)
    ax2.set_title("Litros por estación activa (normalizado por flota)",
                  fontsize=12, fontweight="bold")
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_lts))
    ax2.grid(alpha=0.25)
    _formato_fechas(ax2)

    fig.tight_layout()
    fig.subplots_adjust(hspace=0.35)
    return fig
