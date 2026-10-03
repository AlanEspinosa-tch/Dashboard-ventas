"""
Dashboard de análisis de ventas — Grupo Treher.

Ejecutar desde la carpeta "Códigos":
    streamlit run app.py
"""

import io

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from treher_analytics import borradores as bord
from treher_analytics import comentarios as cmt
from treher_analytics import config as cfg
from treher_analytics import data as dta
from treher_analytics import ejecutivo as ej
from treher_analytics import margenes as mg
from treher_analytics import reporte_pdf as rpdf
from treher_analytics import metrics, model, viz

st.set_page_config(page_title="Análisis de Ventas — Treher", layout="wide")


# ----------------------------------------------------------------------
# CARGA (con caché para no releer el Excel en cada interacción)
# ----------------------------------------------------------------------
@st.cache_data(show_spinner="Cargando base de datos…")
def _cargar():
    bd = dta.cargar_bd()
    return bd, dta.resumen_estaciones(bd)


@st.cache_data(show_spinner="Auditando outliers…")
def _outliers():
    return dta.reporte_outliers()


@st.cache_data(show_spinner="Cargando márgenes…")
def _margenes():
    return mg.cargar_margenes()


# Cálculos pesados cacheados por estación/producto (el guion bajo en _bd
# evita que Streamlit intente hashear el DataFrame completo).
@st.cache_data(show_spinner=False)
def _vig_oos(_bd, est, prod):
    return model.vigilancia_oos(_bd, est, prod, 14)


@st.cache_data(show_spinner=False)
def _bt_rolling(_bd, est, prod):
    return model.backtest_rolling(_bd, est, prod)


# ----------------------------------------------------------------------
# TABLAS BONITAS: formato de números, % en verde/rojo, NaN como —
# ----------------------------------------------------------------------
def _styler(df: pd.DataFrame):
    if not isinstance(df.index, pd.RangeIndex):
        df = df.reset_index()
    df = df.copy()

    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    fmt = {}
    for c in num_cols:
        cl = str(c).lower()
        if "%" in str(c):
            # '+' solo en variaciones (crecimiento); en shares queda plano.
            fmt[c] = "{:+.1f}%" if ("var" in cl or "crec" in cl) else "{:.1f}%"
        elif "/l" in cl or cl.startswith("mgl"):       # margen por litro
            fmt[c] = "{:,.3f}"
        elif any(k in cl for k in ["lts", "litros", "venta", "importe", "total",
                                   "valor", "cambio", "margen", "$/día", "$/dia",
                                   "monto", "_$", "efecto"]):
            fmt[c] = "{:,.0f}"
        else:
            s = df[c].dropna()
            entero = len(s) > 0 and (s.mod(1) == 0).all()   # columnas de conteo
            fmt[c] = "{:,.0f}" if entero else "{:,.2f}"

    sty = df.style.format(fmt, na_rep="—")

    # Solo colorear variaciones (verde/rojo), no los shares.
    pct_cols = [c for c in num_cols
                if "%" in str(c) and ("var" in str(c).lower() or "crec" in str(c).lower())]
    if pct_cols:
        def _color(v):
            if isinstance(v, (int, float)) and pd.notna(v):
                if v > 0:
                    return "color:#137333;font-weight:600"
                if v < 0:
                    return "color:#c5221f;font-weight:600"
            return ""
        try:
            sty = sty.map(_color, subset=pct_cols)
        except AttributeError:           # pandas < 2.1
            sty = sty.applymap(_color, subset=pct_cols)
    return sty


def mostrar(df: pd.DataFrame):
    """Muestra un DataFrame con formato limpio y sin índice crudo."""
    st.dataframe(_styler(df), width="stretch", hide_index=True)


def _boton_pdf(fig, nombre, etiqueta="📄 Descargar en PDF (vectorial)"):
    """Botón para descargar una figura de matplotlib como PDF sin pérdida."""
    buf = io.BytesIO()
    fig.savefig(buf, format="pdf", bbox_inches="tight", facecolor="white")
    st.download_button(etiqueta, buf.getvalue(), f"{nombre}.pdf",
                       "application/pdf", key=f"pdf_{nombre}")


# ----------------------------------------------------------------------
bd, resumen = _cargar()
estaciones = sorted(bd[cfg.COL_ESTACION].unique())

# ----------------------------------------------------------------------
# SIDEBAR
# ----------------------------------------------------------------------
st.sidebar.title("⛽ Treher · Ventas")
estacion = st.sidebar.selectbox(
    "Estación", estaciones,
    index=estaciones.index("QL") if "QL" in estaciones else 0,
)
st.sidebar.caption(
    f"Datos: {bd[cfg.COL_FECHA].min().date()} → {bd[cfg.COL_FECHA].max().date()}  ·  "
    f"{len(estaciones)} estaciones"
)

info = resumen.set_index(cfg.COL_ESTACION).loc[estacion]
if info["Días_cerrados"] > 0:
    st.sidebar.warning(
        f"⚠️ {estacion} tuvo **{int(info['Días_cerrados'])} días cerrados** "
        f"({info['% operación']}% de operación). Los promedios usan solo días operados."
    )

# ----------------------------------------------------------------------
# PESTAÑAS
# ----------------------------------------------------------------------
(tab_exec, tab_grupo, tab_est, tab_margen, tab_modelo,
 tab_pronostico, tab_sarimax, tab_cobertura) = st.tabs(
    ["🎯 Ejecutivo", "📊 Grupo", "🏪 Estación", "💰 Márgenes",
     "📈 Modelo precio-volumen", "🔮 Pronóstico (robusto)",
     "🤖 Pronóstico SARIMAX", "🩺 Cobertura/Cierres"]
)

# ===== EJECUTIVO (nivel Dirección General, mensual, tablas primero) =====
with tab_exec:
    dfm_x = _margenes()
    meses_x = sorted(dfm_x[mg.COL_FECHA].dt.to_period("M").unique())
    etiquetas = {mg.etiqueta_periodo(p): p for p in meses_x}
    st.subheader("Resumen Ejecutivo — Rentabilidad del grupo")
    cpx1, cpx2 = st.columns(2)
    lbl_sel = cpx1.selectbox("Mes a reportar", list(etiquetas.keys()),
                             index=len(etiquetas) - 1)
    per = etiquetas[lbl_sel]
    bases = [p for p in meses_x if p < per]
    _lbls_base = [mg.etiqueta_periodo(p) for p in bases]
    # C1 · la base de la cascada es FEBRERO (config.BASE_CASCADA), no enero:
    # con enero el efecto volumen sale negativo y contradice la pág. de ventas.
    _def = pd.Period(cfg.BASE_CASCADA, "M")
    _idx = bases.index(_def) if _def in bases else max(0, len(bases) - 1)
    lbl_base = cpx2.selectbox("Mes de referencia (base de la cascada)",
                              _lbls_base, index=_idx)
    per_base = etiquetas[lbl_base]
    per_prev = per - 1
    per_yoy = per - 12

    r = ej.margen_sobre_venta(bd, dfm_x, per)
    r_prev = ej.margen_sobre_venta(bd, dfm_x, per_prev) if per_prev in meses_x else None
    r_base = ej.margen_sobre_venta(bd, dfm_x, per_base)
    r_yoy = ej.margen_sobre_venta(bd, dfm_x, per_yoy) if per_yoy in meses_x else None

    k1, k2, k3, k4 = st.columns(4)
    d_mb = (f"{100*(r['margen_bruto']/r_prev['margen_bruto']-1):+.1f}% vs mes ant."
            if r_prev else "")
    k1.metric("Margen bruto", f"${r['margen_bruto']/1e6:,.2f} M", d_mb)
    k2.metric("Margen sobre venta ⭐", f"{r['margen_sobre_venta_%']:.1f}%",
              f"vs {r_base['margen_sobre_venta_%']:.1f}% en {lbl_base}",
              delta_color="off")
    d_vol = (f"{100*(r['litros']/r_yoy['litros']-1):+.1f}% vs a.a." if r_yoy else "")
    k3.metric("Volumen", f"{r['litros']/1e6:,.2f} M L", d_vol)
    d_v = (f"{100*(r['venta']/r_yoy['venta']-1):+.1f}% vs a.a." if r_yoy else "")
    k4.metric("Venta", f"${r['venta']/1e6:,.2f} M", d_v)
    st.caption(f"⭐ El **margen sobre venta** es el indicador titular. "
               f"Comparación principal: {lbl_sel} vs {lbl_base}. "
               "Fuente litros/venta: BD · margen: BD_MARGENES.")

    st.markdown("---")
    st.markdown(f"**¿Por qué cambió el margen?** — descomposición {lbl_sel} vs {lbl_base} "
                "(volumen · mix · margen unitario)")
    mostrar(ej.descomposicion_margen(dfm_x, per, per_base))
    st.caption("Lectura: si el grueso está en *margen unitario*, el problema es "
               "de compra/precio, no de volumen ni de mezcla.")

    st.markdown(f"**¿Cuánto de la venta es volumen y cuánto es precio?** — {lbl_sel} vs {lbl_base}")
    mostrar(ej.descomposicion_venta(bd, per, per_base))

    st.markdown("---")
    st.markdown(f"**Margen bruto por estación — {lbl_sel}** (dónde se genera el resultado)")
    mostrar(ej.margen_por_estacion(dfm_x, per))
    st.markdown(f"**Contribución a la variación de margen** — {lbl_sel} vs {mg.etiqueta_periodo(per_base)}")
    mostrar(ej.contribucion_variacion(dfm_x, per, per_base))

    st.markdown("---")
    _cre = ej.crecimiento_mismas_estaciones(bd, per.year, per.month)
    _tot = _cre.iloc[0]["Var_%"]
    _mm = _cre.iloc[1]["Var_%"]
    st.markdown(f"**Crecimiento del grupo (YTD ene–{lbl_sel.split()[0]}): "
                f"{_tot:+.1f}%**")
    st.caption(f"Cifra principal = **todo el grupo** ({int(_cre.iloc[0]['Estaciones'])} "
               f"estaciones, sin excluir). Comparación justa (mismas estaciones, "
               f"sin reaperturas ni bajas): **{_mm:+.1f}%** "
               f"({int(_cre.iloc[1]['Estaciones'])} estaciones).")
    mostrar(_cre)

    st.markdown("---")
    st.markdown("**Serie de margen — últimos 13 meses**")
    mostrar(ej.serie_margen(bd, dfm_x, 13))

    # ---- Textos del reporte (categorías B y C) ----
    st.markdown("---")
    st.markdown("### ✍️ Textos del reporte")
    st.caption("**Python calcula, la dirección interpreta.** Los campos "
               "🟦 *borrador* llegan precargados con los datos del mes (edítalos "
               "o déjalos). Los 🟧 *manuales* llegan vacíos: solo tú puedes "
               "explicar el porqué — si los dejas vacíos, ese bloque **no se "
               "imprime** en el PDF.")

    pk = str(per)
    _draft = bord.generar(bd, dfm_x, per, per_base)
    _guard = cmt.cargar(per)
    _caidas = list(ej.contribucion_variacion(dfm_x, per, per - 1)
                   .query("`Δ_margen_$` < 0").head(3)["Estación"])
    _bloques = [(bid, lbl, cat, lim, sec) for bid, lbl, cat, lim, sec in cmt.CATALOGO]
    for bid, lbl, lim in cmt.acciones_de(per, _caidas):
        _bloques.append((bid, lbl, "C", lim, "Página 5 · Acciones"))

    for bid, lbl, cat, lim, sec in _bloques:
        k = f"tx_{pk}_{bid}"
        if k not in st.session_state:
            st.session_state[k] = _guard.get(
                bid, _draft.get(bid, "") if cat == "B" else "")

    c_a, c_b = st.columns([1, 1])
    if c_a.button("↻ Regenerar borradores (solo campos vacíos)", key="regen"):
        for bid, _, cat, _, _ in _bloques:
            k = f"tx_{pk}_{bid}"
            if cat == "B" and not st.session_state.get(k, "").strip():
                st.session_state[k] = _draft.get(bid, "")
    if c_b.button("↩ Cargar seguimiento del mes anterior", key="seguim"):
        seg = cmt.seguimiento_mes_anterior(per)
        if seg:
            st.session_state[f"tx_{pk}_com.acciones"] = seg
        else:
            st.info("El mes anterior no tiene 'Próximos pasos' capturados.")

    _secs = []
    for b in _bloques:
        if b[4] not in _secs:
            _secs.append(b[4])
    for sec in _secs:
        with st.expander(sec, expanded=(sec == "Comentarios de dirección")):
            for bid, lbl, cat, lim, s in _bloques:
                if s != sec:
                    continue
                marca = "🟦" if cat == "B" else "🟧"
                ayuda = ("Borrador automático — edítalo si quieres."
                         if cat == "B" else
                         "Solo tú puedes explicar esto (queda vacío si no lo escribes).")
                st.text_area(f"{marca} {lbl}", key=f"tx_{pk}_{bid}",
                             height=68, help=ayuda)
                val = st.session_state.get(f"tx_{pk}_{bid}", "")
                n = len(val)
                # El límite es orientativo, NO bloquea: el PDF envuelve el
                # texto y la consola avisa si una hoja se queda sin espacio.
                if n > lim:
                    st.caption(f"{n} caracteres (referencia {lim}) — "
                               f"revisa que la hoja no se apriete.")
                else:
                    st.caption(f"{n}/{lim} caracteres")

    _textos = {bid: st.session_state.get(f"tx_{pk}_{bid}", "")
               for bid, _, _, _, _ in _bloques}
    cg1, cg2 = st.columns([1, 1])
    if cg1.button("💾 Guardar textos", key="save_tx"):
        cmt.guardar(per, _textos)
        st.success(f"Textos de {lbl_sel} guardados.")

    # ---- Generar el PDF ejecutivo del mes seleccionado ----
    st.markdown("---")
    st.markdown("**Reporte ejecutivo en PDF** — 6 páginas: ventas → desempeño "
                "(volumen · importe) → acumulado → rentabilidad → margen por "
                "estación")
    if cg2.button(f"📄 Generar PDF de {lbl_sel}", key="gen_pdf"):
        with st.spinner("Generando PDF…"):
            _pdf = rpdf.generar_pdf(bd, dfm_x, per, per_base, textos=_textos)
        st.download_button("⬇️ Descargar PDF", _pdf,
                           f"Reporte_Ejecutivo_{per}.pdf", "application/pdf",
                           key="dl_pdf")

# ===== GRUPO =====
with tab_grupo:
    st.subheader("Crecimiento del grupo (like-for-like)")

    kpis = metrics.kpis_crecimiento(bd)
    cols = st.columns(3)
    for col, (_, row) in zip(cols, kpis.iterrows()):
        col.metric(
            label=row["Indicador"],
            value=f"{row['Lts_actual'] / 1e6:,.2f} M L",
            delta=f"{row['Var_%']:+.1f}%",
            help=f"{row['Periodo actual']} vs {row['Comparación']} · "
                 f"{int(row['Estaciones_LFL'])} estaciones comparables",
        )
    st.caption(
        "La cifra grande es el **volumen del periodo actual**; el porcentaje en "
        "color es el **crecimiento** vs. el periodo de comparación. "
        "MoM = mes vs. mes anterior · YoY = mismo mes año pasado · "
        "YTD = acumulado del año. Detalle exacto de periodos:"
    )
    mostrar(kpis)

    activas_hoy = int(
        dta.estaciones_activas_por_fecha(bd).iloc[-1]["Estaciones_activas"]
    )
    mejor = metrics.ranking_estaciones(bd, 30).iloc[0]
    st.caption(
        f"Estaciones activas el último día con datos: **{activas_hoy}**  ·  "
        f"Mejor estación (lts/día, 30d): **{mejor[cfg.COL_ESTACION]}** "
        f"({mejor['Lts_por_dia_op']:,.0f} L)"
    )

    st.markdown("---")
    st.markdown("**Consolidado normalizado por flota** "
                "(una caída del total puede ser solo por menos estaciones abiertas)")
    _yrs = sorted(bd[cfg.COL_ANIO].unique())
    _c_lo, _c_hi = st.slider("Años a mostrar", min(_yrs), max(_yrs),
                             (min(_yrs), max(_yrs)), key="cons_anios")
    st.pyplot(viz.consolidado_con_flota(bd, anios=list(range(_c_lo, _c_hi + 1))))
    plt.close("all")

    st.markdown("**Promedio ponderado por día — últimos 3 meses** "
                "(litros/día por combustible; bloques de 28 días, cada bloque "
                "pesa la mitad del anterior ≈ 57% / 29% / 14%)")
    mostrar(metrics.promedio_ponderado_estaciones(bd))

    rk = metrics.ranking_grupo(bd)
    ini_rk, fin_rk = rk.attrs["ventana"]
    per_ant = rk.attrs["periodo"]
    st.markdown(f"**Ranking del grupo** — litros/día operado (ventana comparable "
                f"{ini_rk} → {fin_rk}) y cifras del mes anterior ({per_ant})")
    mostrar(rk)

    dfm_gm = _margenes()
    st.markdown("**Gross margin del grupo — últimos 6 meses** "
                "(gross margin = margen bruto ÷ ventas $). Litros y ventas de "
                "BD_Limpia; margen de la base de márgenes.")
    mostrar(mg.gross_margin_mensual(dfm_gm, bd))

    lbl_gm = mg.etiqueta_periodo(mg.mes_anterior_completo(dfm_gm))
    st.markdown(f"**Gross margin por combustible — {lbl_gm}** (grupo)")
    mostrar(mg.gross_margin_por_producto(dfm_gm, bd))

    st.markdown("---")
    st.markdown("**Litros vendidos por mes y combustible** (grupo)")
    anios_lts = sorted(bd[cfg.COL_ANIO].unique())
    sel_lts = st.multiselect("Años a mostrar", anios_lts, default=anios_lts,
                             key="lts_anios")
    if sel_lts:
        st.pyplot(viz.barras_litros_historico(bd, sel_lts))
        plt.close("all")
    else:
        st.info("Selecciona al menos un año.")

    st.markdown("**Margen bruto por mes y combustible** (grupo)")
    dfm_g = _margenes()
    anios_mg = sorted(dfm_g["Año"].unique())
    sel_mg = st.multiselect("Años a mostrar", anios_mg, default=anios_mg,
                            key="mg_anios")
    if sel_mg:
        st.pyplot(viz.barras_margen_historico(dfm_g, sel_mg))
        plt.close("all")
    else:
        st.info("Selecciona al menos un año.")

# ===== ESTACIÓN =====
with tab_est:
    st.subheader(f"Estación: {estacion}")
    _yrs_e = sorted(bd[bd[cfg.COL_ESTACION] == estacion][cfg.COL_ANIO].unique())
    if len(_yrs_e) > 1:
        _e_lo, _e_hi = st.slider("Años a mostrar", min(_yrs_e), max(_yrs_e),
                                 (min(_yrs_e), max(_yrs_e)), key="evo_anios")
        _e_anios = list(range(_e_lo, _e_hi + 1))
    else:
        _e_anios = _yrs_e
    try:
        st.pyplot(viz.evolucion_estacion(bd, estacion, anios=_e_anios))
    except ValueError as e:
        st.info(str(e))
    plt.close("all")

    # KPIs de ventas
    k1, k2, k3 = st.columns(3)
    proy = metrics.proyeccion_cierre_mes(bd, estacion).iloc[0]
    k1.metric(f"Proyección cierre {proy['Mes_en_curso']}",
              f"{proy['Proyección_cierre'] / 1e6:,.2f} M L",
              f"{proy['Var_vs_mes_ant_%']:+.1f}%",
              help="Run-rate: litros/día operado × días del mes. Var vs. mes anterior.")
    mixv = metrics.mix_volumen(bd, estacion).set_index("Producto")["% del volumen"]
    k2.metric("Penetración Premium", f"{mixv.get('Premium', float('nan')):.1f}%",
              help="% del volumen que es Premium")
    pr = metrics.precio_realizado(bd, estacion).set_index("Producto")["Más_reciente"]
    k3.metric("Precio Diésel más reciente", f"${pr.get('Diésel', float('nan')):.2f}/L",
              help="Último precio disponible de Diésel")

    anio_vig = int(bd[cfg.COL_ANIO].max())
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Volumen mensual** — últimos 12 meses (con días operados)")
        mostrar(metrics.volumen_mensual(bd, estacion).tail(12))
        st.markdown(f"**Mix de producto (volumen)** — acumulado {anio_vig}")
        mostrar(metrics.mix_volumen(bd, estacion, anio=anio_vig))
    with c2:
        st.markdown("**Precio realizado ($/L)** — inicio de año · mes pasado · más reciente")
        mostrar(metrics.precio_realizado(bd, estacion))
        dfm_e = _margenes()
        if estacion in dfm_e[mg.COL_EST].unique():
            lbl_e = mg.etiqueta_periodo(mg.mes_anterior_completo(dfm_e))
            st.markdown(f"**Gross margin por combustible — {lbl_e}**")
            mostrar(mg.gross_margin_por_producto(dfm_e, bd, estacion=estacion))
        else:
            st.info(f"{estacion} sin datos de margen (cobertura 12 est. desde 2025).")
        st.markdown("**Anomalías — Diésel** · últimos 15 eventos "
                    "(z-score robusto mediana/MAD > 3.5)")
        mostrar(metrics.anomalias(bd, estacion, "Diésel").tail(15))

    # ---- Perfil por día de la semana: línea base actual o congelada ----
    st.markdown("---")
    st.markdown("### Perfil por día de la semana")
    modo = st.radio("Línea base", ["Actual", "A una fecha"], horizontal=True,
                    key="perf_modo",
                    help="'Actual' usa los datos recientes. 'A una fecha' congela "
                         "la base con datos ≤ esa fecha (para medir un suceso).")
    fecha_ref = None
    fest = bd[bd[cfg.COL_ESTACION] == estacion][cfg.COL_FECHA]
    if modo == "A una fecha":
        fecha_ref = st.date_input(
            "Calcular con datos hasta (inclusive):",
            value=fest.max().date(), min_value=fest.min().date(),
            max_value=fest.max().date(), key="perf_fecha")
        st.caption(f"Línea base congelada con datos ≤ **{fecha_ref}** "
                   "(promedios, σ, mín y máx solo de esa fecha para atrás).")

    _perf_full = metrics.perfil_dia_semana(bd, estacion, fecha_ref=fecha_ref)
    _perf_red = metrics.perfil_dia_semana(bd, estacion, redondear_a=100,
                                          fecha_ref=fecha_ref)
    pc1, pc2 = st.columns(2)
    with pc1:
        st.markdown("**Detalle** — ponderado 3m vs. último mes")
        mostrar(_perf_full)
    with pc2:
        st.markdown("**Redondeado** — mín · esperado · máx")
        mostrar(_perf_red[["Producto", "Día", "Rango_mín",
                           "Lts_ponderado_3m", "Rango_máx"]])
    st.caption(
        "*Lts_ponderado_3m*: promedio de 3 meses con **peso exponencial** "
        "(vida media 30 días). *Rango_mín/máx*: banda **±1σ** (~74% de los días); "
        "la σ se estima con 12 meses destendenciados."
    )

    st.markdown("---")
    st.markdown("**¿Las ventas se mantienen dentro del rango típico?** "
                "Cada punto es un día; el área es el rango ±1σ de la tabla de "
                "arriba según el día de la semana. 🔵 dentro · 🟡 fuera de ±1σ "
                "(atención) · 🔴 fuera de ±2σ (inusual). Vigila **rachas**, no un "
                "día suelto.")
    sem = st.slider("Semanas a mostrar", 4, 12, 8, key="vig_sem")
    _fig_vig = viz.grafico_perfil_vigilancia(bd, estacion, _perf_red, semanas=sem)
    st.pyplot(_fig_vig)
    _boton_pdf(_fig_vig, f"vigilancia_{estacion}_{sem}sem")
    plt.close("all")

    # ---- Comparativa antes/después (solo con base congelada) ----
    if modo == "A una fecha" and fecha_ref is not None:
        st.markdown("---")
        st.markdown(f"**Comparativa antes/después del {fecha_ref}** "
                    "(por día de la semana)")
        comp = metrics.comparativa_antes_despues(bd, estacion, fecha_ref)
        mostrar(comp)
        st.caption(
            "*Lts_antes*: esperado congelado (≤ fecha) · *Lts_después*: promedio "
            "real posterior · *Var_%*: cambio · *Dist_σ*: a cuántas σ quedó el "
            "nuevo nivel (|>1.5| ya es señal fuerte, no ruido) · "
            "*Días_bajo_mín_%*: % de días posteriores bajo el mínimo previo · "
            "*n_después*: nº de días — **con pocos días el Var_% es ruidoso**, "
            "guíate por Dist_σ y Días_bajo_mín_%."
        )

        st.markdown(f"**Consolidado de la estación** (todos los combustibles) — "
                    f"antes/después del {fecha_ref}")
        mostrar(metrics.comparativa_antes_despues_total(bd, estacion, fecha_ref))
        st.caption(
            "Mismo cálculo pero con el **total de la estación**, sin separar por "
            "combustible. La fila **SEMANA PROMEDIO** suma los siete días: es "
            "cuánto vende la estación en una semana típica, antes vs. después."
        )

# ===== MÁRGENES =====
with tab_margen:
    dfm = _margenes()
    st.subheader("Rentabilidad (márgenes brutos)")
    st.caption(
        f"{mg.frescura(dfm)} · base independiente de BD_Limpia. "
        "Aquí *Total $* = **margen bruto**, no venta."
    )

    km = mg.kpis_margen(dfm)
    cols = st.columns(3)
    for col, (_, row) in zip(cols, km.iterrows()):
        col.metric(
            label=row["Indicador"],
            value=f"${row['Margen_actual_$'] / 1e6:,.2f} M",
            delta=f"{row['Var_%']:+.1f}%",
            help=f"{row['Periodo actual']} vs {row['Comparación']} · "
                 f"{int(row['Estaciones_LFL'])} estaciones comparables",
        )
    st.caption("Crecimiento del **margen bruto** del grupo, like-for-like. "
               "Detalle exacto de periodos:")
    mostrar(km)

    mes_ant = mg.mes_anterior_completo(dfm)
    lbl_mes = mg.etiqueta_periodo(mes_ant)

    st.markdown("---")
    st.markdown(f"**Volumen vs. margen — {lbl_mes}** (mes anterior al vigente). "
                "El tamaño (litros) no es lo mismo que la rentabilidad: "
                "compara `Rank_volumen` contra `Rank_margen`.")
    mostrar(mg.volumen_vs_margen(dfm, periodo=mes_ant))

    st.markdown(f"**Mix por producto (grupo) — {lbl_mes}:** % del volumen vs. "
                "% del margen. Un producto puede pesar mucho en litros y poco en margen.")
    mostrar(mg.mix_volumen_vs_margen(dfm, periodo=mes_ant))

    st.markdown("**Resumen de rentabilidad por estación** — histórico completo "
                "(margen $/día operado — respeta cierres)")
    mostrar(mg.resumen_margen(dfm))

    st.markdown("---")
    st.markdown(f"**Estación seleccionada: {estacion}**")
    if estacion not in dfm[mg.COL_EST].unique():
        st.info(f"{estacion} no está en la base de márgenes "
                "(cobertura: 12 estaciones desde 2025).")
    else:
        cm1, cm2 = st.columns(2)
        with cm1:
            st.markdown("Evolución mensual del margen — histórico")
            mostrar(mg.evolucion_mensual(dfm, estacion))
        with cm2:
            st.markdown(f"Mix volumen vs. margen — {lbl_mes}")
            mostrar(mg.mix_volumen_vs_margen(dfm, estacion, periodo=mes_ant))
        perd = mg.dias_a_perdida(dfm, estacion)
        if perd.empty:
            st.success("✅ Sin días de venta a pérdida.")
        else:
            st.markdown("⚠️ Días de venta a pérdida (margen/L < 0)")
            mostrar(perd)

# ===== MODELO =====
with tab_modelo:
    st.subheader(f"Modelo precio-volumen — {estacion}")
    st.caption(
        "ln(litros) ~ ln(precio) + tendencia + día de semana + estacionalidad anual. "
        "La elasticidad indica el % de cambio en litros ante +1% de precio. "
        "Se reporta la elasticidad OLS y la **robusta (RLM-Huber)**: si difieren, "
        "la columna *Sensible_a_outliers* lo marca. El semáforo resume la confiabilidad."
    )
    st.caption(
        "**Mejora_vs_naive_%**: cuánto menos se equivoca el modelo que el *naive "
        "estacional* ('este día = el mismo día de la semana pasada'). Es una vara "
        "exigente; >0 ya significa que el modelo aporta sobre el patrón semanal."
    )
    if not info["Historia_suficiente"]:
        st.info(f"{estacion} tiene historia insuficiente (<1 año operado) "
                "para un modelo estacional confiable.")
    else:
        with st.spinner("Ajustando modelo…"):
            res = model.modelo_precio_volumen(bd, estacion)
        mostrar(res)
        st.caption("🟢 ≥80 · 🟡 ≥60 · 🟠 ≥40 · 🔴 <40 · ⚪ sin datos")
        st.caption(
            "Pruebas de residuos (p-valor; **>0.05 es bueno**): "
            "**DW** ~2 sin autocorrelación · **BG_p** autocorrelación · "
            "**BP_p** heterocedasticidad (varianza constante) · "
            "**JB_p** normalidad de los errores (Jarque-Bera)."
        )
        st.warning(
            "⚠️ Con tantos datos (N grande) estas pruebas casi siempre rechazan "
            "(p≈0) aunque la desviación sea mínima — el test se vuelve "
            "hipersensible. Por eso conviene **juzgar por las gráficas**, no por "
            "el p-valor."
        )

        st.markdown("---")
        st.markdown("**Diagnóstico visual de residuos** (una gráfica por combustible)")
        diag = model.residuos_modelo(bd, estacion)
        if diag:
            dw_por_prod = res["DW"] if "DW" in res.columns else {}
            for prod_diag, d in diag.items():
                dw_val = dw_por_prod.get(prod_diag) if hasattr(dw_por_prod, "get") else None
                try:
                    dw_val = float(dw_val)
                except (TypeError, ValueError):
                    dw_val = None
                st.pyplot(viz.graficas_residuos(d["resid"], d["fitted"],
                                                f"{estacion} · {prod_diag}", dw=dw_val))
                plt.close("all")
            st.caption(
                "Cómo leerlas: **1)** residuos sin patrón alrededor de 0 · "
                "**2)** nube sin forma de embudo (si se abre = heterocedasticidad) · "
                "**3)** barras de ACF dentro de la banda azul (fuera = autocorrelación) · "
                "**4)** puntos sobre la línea roja (se desvían en las colas = no normal)."
            )
        else:
            st.info("Sin productos con historia suficiente para el diagnóstico.")

# ===== PRONÓSTICO =====
with tab_pronostico:
    st.subheader(f"Pronóstico de volumen — {estacion}")
    st.caption(
        "Ajuste **robusto (RLM-Huber)**: los días extremos pesan menos, para no "
        "sobre-estimar. La banda 95% es **empírica** (cuantiles de los residuos) "
        "→ asimétrica y bien calibrada. El precio futuro se mantiene en el último "
        "observado salvo que pruebes otro escenario."
    )
    if not info["Historia_suficiente"]:
        st.info(f"{estacion} tiene historia insuficiente (<1 año) para pronosticar.")
    else:
        cc1, cc2, cc3 = st.columns(3)
        prod_fc = cc1.selectbox("Producto", cfg.PRODUCTOS, key="fc_prod")
        dias_fc = cc2.slider("Días a pronosticar", 7, 90, 30, step=7)
        precio_fc = cc3.number_input("Precio escenario ($/L, 0 = actual)",
                                     min_value=0.0, value=0.0, step=0.10)
        try:
            with st.spinner("Calculando pronóstico…"):
                fc = model.pronostico(bd, estacion, prod_fc, dias_fc,
                                      precio_fc or None)
            st.pyplot(viz.grafico_pronostico(fc, estacion, prod_fc))
            plt.close("all")

            fut = fc[fc["Tipo"] == "Pronóstico"]
            total = fut["Litros"].sum()
            st.metric(f"Litros pronosticados ({dias_fc} días)",
                      f"{total / 1e6:,.2f} M L",
                      help="Suma del pronóstico en el horizonte seleccionado")

            st.markdown("**🚦 Vigilancia (out-of-sample) — últimos 14 días.** "
                        "La banda se genera con un modelo entrenado **sin** estos "
                        "días, así una anomalía no puede enmascararse. Un 🔴 es "
                        "señal temprana de que algo cambió respecto a lo normal.")
            try:
                vig = _vig_oos(bd, estacion, prod_fc)
                n_fuera = (vig["Estado"] == "🔴 fuera").sum()
                if n_fuera == 0:
                    st.success("✅ Los 14 días se comportaron dentro de lo esperado.")
                else:
                    st.warning(f"⚠️ {n_fuera} de 14 días se salieron de la banda esperada.")
                mostrar(vig)
            except ValueError as e:
                st.info(str(e))

            st.markdown("**Proyección del próximo mes calendario** (robusto, vs. mismo mes del año pasado)")
            mostrar(model.proyeccion_mes_siguiente(bd, estacion, prod_fc, motor="robusto",
                                                   precio=precio_fc or None))
            mostrar(fut[[cfg.COL_FECHA, "Litros", "LI", "LS"]])
        except ValueError as e:
            st.warning(str(e))

# ===== PRONÓSTICO SARIMAX =====
with tab_sarimax:
    st.subheader(f"Pronóstico SARIMAX — {estacion}")
    st.caption(
        "Mismos regresores que el pronóstico robusto, pero modelando la **autocorrelación** de "
        "los residuos (errores ARIMA). Suele dar bandas más realistas. "
        "La interpretación económica (elasticidad) se lee en la pestaña *Modelo* "
        "— aquí los coeficientes no son elasticidad."
    )
    if not info["Historia_suficiente"]:
        st.info(f"{estacion} tiene historia insuficiente (<1 año) para pronosticar.")
    else:
        sc1, sc2, sc3 = st.columns(3)
        prod_sx = sc1.selectbox("Producto", cfg.PRODUCTOS, key="sx_prod")
        dias_sx = sc2.slider("Días a pronosticar", 7, 90, 30, step=7, key="sx_dias")
        precio_sx = sc3.number_input("Precio escenario ($/L, 0 = actual)",
                                     min_value=0.0, value=0.0, step=0.10, key="sx_precio")
        try:
            with st.spinner("Ajustando SARIMAX…"):
                fc = model.pronostico_sarimax(bd, estacion, prod_sx, dias_sx,
                                              precio_sx or None)
            r = fc.attrs.get("resumen", {})
            st.pyplot(viz.grafico_pronostico(fc, estacion, prod_sx))
            plt.close("all")
            st.caption(f"Ajuste: AIC {r.get('AIC')} · ARMA {r.get('Orden_ARMA')} · "
                       f"{r.get('Días_historia')} días de historia")

            st.markdown("**🚦 Vigilancia (out-of-sample) — últimos 14 días** "
                        "(banda de un modelo entrenado sin estos días)")
            try:
                vig = _vig_oos(bd, estacion, prod_sx)
                n_fuera = (vig["Estado"] == "🔴 fuera").sum()
                if n_fuera == 0:
                    st.success("✅ Los 14 días se comportaron dentro de lo esperado.")
                else:
                    st.warning(f"⚠️ {n_fuera} de 14 días se salieron de la banda esperada.")
                mostrar(vig)
            except ValueError as e:
                st.info(str(e))

            st.markdown("**Proyección del próximo mes calendario** (SARIMAX, vs. año pasado)")
            mostrar(model.proyeccion_mes_siguiente(bd, estacion, prod_sx, motor="sarimax",
                                                   precio=precio_sx or None))

            st.markdown("**Backtest rolling — desempeño en varias ventanas.** "
                        "Promedia el error en múltiples cortes temporales (no uno "
                        "solo): menor MAPE gana, menor *std* = más estable, y "
                        "`Cobertura_95` debería rondar 95% si la banda es honesta.")
            with st.spinner("Validación rolling (varias ventanas, puede tardar)…"):
                mostrar(_bt_rolling(bd, estacion, prod_sx))
            mostrar(fc[fc["Tipo"] == "Pronóstico"][[cfg.COL_FECHA, "Litros", "LI", "LS"]])
        except ValueError as e:
            st.warning(str(e))

# ===== COBERTURA =====
with tab_cobertura:
    st.subheader("Diagnóstico de cobertura y cierres")
    st.caption(
        "Esta tabla es la base para interpretar todo lo demás: cuántos días "
        "operó realmente cada estación. Los promedios excluyen días cerrados; "
        "los totales crudos no — por eso aquí se ve el panorama real."
    )
    mostrar(resumen)

    st.markdown("---")
    st.markdown("**Auditoría de outliers** — valores físicamente imposibles "
                "descartados en la carga (precios fuera de rango, volúmenes "
                "desproporcionados). Los picos reales de negocio NO se tocan.")
    rep = _outliers()
    if rep.empty:
        st.success("✅ No se detectaron errores de captura imposibles en la base.")
    else:
        mostrar(rep)
