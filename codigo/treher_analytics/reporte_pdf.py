"""
Reporte ejecutivo mensual — PDF (6 páginas).

Orden: ventas → desempeño por estación (volumen · importe) → acumulado →
rentabilidad → margen por estación.
Tablas primero. Categorías de texto: A (automático), B (borrador editable),
C (manual puro: si está vacío, el bloque COMPLETO se omite y la página se
reflowea).
"""

from __future__ import annotations

import io

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from . import borradores as bo
from . import comentarios as cmt
from . import config as cfg
from . import ejecutivo as ej
from . import margenes as mg
from . import tablas as tb

mpl.rcParams["text.parse_math"] = False          # G8: el $ no es fórmula

# --- Paleta (E1) ---
INK, INK2, MUTED = "#0B2244", "#41505F", "#7A8593"
SER1, SER2 = "#2A5CA8", "#C8622A"
POS, NEG = "#1E7A50", "#B3261E"
# v6·2 · el color de DESEMPEÑO pasa a azul/naranja para no competir con la
# identidad de combustible (verde = regular, rojo = premium).
BUENO, MALO = "#247BA0", "#D45F31"       # número
TPOS, TNEG = "#E8F1F5", "#FDECE4"        # fondo de celda
TXPOS, TXNEG = BUENO, MALO               # texto sobre celda teñida
# Relleno completo de la celda de combustible (v6·3)
FUEL_BG = {"Diésel": ("#D9DCE1", "#1A1A1A"),
           "Premium": ("#F6D9D6", "#8E1811"),
           "Regular": ("#D9EDE2", "#1F6B45")}
# Rampa morada verificada para la gráfica trimestral (v6·5.4)
RAMPA = {2026: ("#38126A", 3.2, 6.5, 1.00), 2025: ("#4C1C90", 2.5, 5.0, 0.95),
         2024: ("#6430B4", 2.0, 4.0, 0.90), 2023: ("#8050C8", 1.6, 0, 0.85),
         2022: ("#9C74D6", 1.3, 0, 0.80), 2021: ("#A9A3B4", 1.0, 0, 0.75)}
GRID, PANEL, TOTALBG = "#E4E7EB", "#F4F6F8", "#D9DEE5"
FUEL = {"Diésel": "#1A1A1A", "Premium": "#A81E17", "Regular": "#2E8B57"}

MENOS = "−"                                  # signo negativo U+2212


# ----------------------------------------------------------------------
# Formato numérico (E2)
# ----------------------------------------------------------------------
def _sg(x, dec=1, suf="%"):
    if pd.isna(x):
        return "n/a"
    s = f"{abs(x):,.{dec}f}"
    return f"{'+' if x >= 0 else MENOS}{s}{suf}"


def _num(x, dec=0):
    if pd.isna(x):
        return "n/a"
    return f"{MENOS if x < 0 else ''}{abs(x):,.{dec}f}"


def _pesos(x, dec=0):
    if pd.isna(x):
        return "n/a"
    return f"{MENOS if x < 0 else ''}${abs(x):,.{dec}f}"


def _pesos_var(x):
    return "n/a" if pd.isna(x) else f"{'+' if x >= 0 else MENOS}${abs(x):,.0f}"


def _M(x):
    """Pesos en texto: ≥ $1 M en millones; por debajo en miles (V9: nunca $0.0M)."""
    if pd.isna(x):
        return "n/a"
    if abs(x) < 1_000_000:
        return f"{MENOS if x < 0 else ''}${abs(x)/1e3:,.0f} K"
    return f"{MENOS if x < 0 else ''}${abs(x)/1e6:,.1f} M"


def _pct(x, dec=1):
    return "n/a" if pd.isna(x) else f"{x:,.{dec}f}%"


# ----------------------------------------------------------------------
# Estructura de página
# ----------------------------------------------------------------------
LOGO_NAR = "#F4571B"          # naranja del monograma
_LOGO = None


def _logo_ruta():
    """
    Monograma TH vectorizado (Logo_ruta.npz): contornos trazados sobre
    Logo.jpg, con los arcos pegados a su radio exacto y simplificados. Va como
    trazo, no como imagen, para que no dependa de la resolución al imprimir.
    """
    global _LOGO
    if _LOGO is None:
        from pathlib import Path as _P
        import matplotlib.path as mpath
        p = _P(cfg.__file__).resolve().parent.parent / "Logo_ruta.npz"
        if p.exists():
            z = np.load(p)
            _LOGO = mpath.Path(z["verts"].astype(float), z["codes"])
        else:
            _LOGO = False
    return _LOGO


def _sello(fig, y0, alto):
    """Logo en la esquina derecha de la franja, ajustado a su altura."""
    ruta = _logo_ruta()
    if ruta is False:
        return
    import matplotlib.patches as mpatches
    filete = 3 / 72 / 11
    d_h = (alto - filete) * 0.68                 # diámetro en fracción de alto
    d_w = d_h * 11 / 8.5                         # corrige el aspecto de la hoja
    ax = fig.add_axes([0.945 - d_w,
                       y0 + filete + (alto - filete - d_h) / 2, d_w, d_h],
                      zorder=5)
    ax.set_xlim(-1.04, 1.04)
    ax.set_ylim(1.04, -1.04)                     # y crece hacia abajo (imagen)
    ax.axis("off")
    ax.patch.set_alpha(0)
    ax.add_patch(mpatches.PathPatch(ruta, facecolor=LOGO_NAR, edgecolor="none",
                                    antialiased=True))


def _pagina(titulo, base_txt, subtitulo_banda=None):
    """Banda de sección. Si `subtitulo_banda` se pasa, la banda es de dos
    niveles (v6·1) y crece de 0.056 a 0.072. Todas llevan filete naranja."""
    fig = plt.figure(figsize=(8.5, 11))
    fig.patch.set_facecolor("white")
    alto = 0.072 if subtitulo_banda else 0.056
    y0 = 1 - alto
    fig.patches.append(plt.Rectangle((0, y0), 1, alto, transform=fig.transFigure,
                                     color=INK, zorder=0))
    # Filete naranja de 3 pt al pie de la banda (identidad, en todas las páginas)
    fig.patches.append(plt.Rectangle((0, y0), 1, 3 / 72 / 11,
                                     transform=fig.transFigure, color=SER2, zorder=1))
    if subtitulo_banda:
        fig.text(0.055, y0 + alto * 0.62, titulo, color="white", fontsize=18,
                 fontweight="bold", va="center")
        fig.text(0.055, y0 + alto * 0.26, subtitulo_banda, color="#AFC0D6",
                 fontsize=10, va="center")
    else:
        # El logo ocupa la esquina derecha en lugar del periodo y la base;
        # esos datos siguen en la banda de la hoja 1 y en el pie de cada hoja.
        fig.text(0.055, y0 + alto / 2, titulo, color="white", fontsize=16,
                 fontweight="bold", va="center")
    _sello(fig, y0, alto)
    fig.attrs_y0 = y0
    return fig


def _titulares(fig, titular, subtitulo, y=0.905):
    """
    Titular y subtítulo. Ambos se envuelven si son largos: ya no hay tope duro
    de caracteres, así que el texto nunca debe salirse de la hoja ni reventar
    la generación del PDF.
    """
    import textwrap
    if titular:
        for ln in textwrap.wrap(str(titular), width=72):
            fig.text(0.055, y, ln, fontsize=13, fontweight="bold", color=INK,
                     va="top")
            y -= 0.024
    if subtitulo:
        for ln in textwrap.wrap(str(subtitulo), width=104):
            fig.text(0.055, y, ln, fontsize=10, color=INK2, va="top")
            y -= 0.022
    return y - 0.008


def _pie(fig, n):
    """Solo el folio. Las notas metodológicas se retiraron del reporte."""
    fig.text(0.945, 0.014, f"Grupo Treher · {n}/6", color=MUTED, fontsize=6.8,
             ha="right", va="center")


def _tarjetas(fig, y, items, destacada=0):
    """items: [(etiqueta, valor, delta)]. Una sola destacada por página (D)."""
    n = len(items)
    w, gap = 0.205, 0.0217
    x0 = 0.055
    for i, (lbl, val, dlt) in enumerate(items):
        x = x0 + i * (w + gap)
        dest = (i == destacada)
        ax = fig.add_axes([x, y - 0.085, w, 0.085]); ax.axis("off")
        ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                                   facecolor=(INK if dest else PANEL), lw=0))
        ax.text(0.5, 0.78, lbl, ha="center", va="center", fontsize=7.4,
                color=("#AEB8C8" if dest else MUTED), transform=ax.transAxes)
        ax.text(0.5, 0.46, val, ha="center", va="center",
                fontsize=(21 if dest else 18), fontweight="bold",
                color=("white" if dest else INK), transform=ax.transAxes)
        ax.text(0.5, 0.15, dlt, ha="center", va="center", fontsize=7.2,
                color=(SER2 if dest else MUTED), transform=ax.transAxes)
    return y - 0.085 - 0.018


def _tabla(fig, y, alto, cols, filas, titulo=None, tintes=None, barras=None,
           negritas=None, x=0.055, ancho=0.89, relleno_etq=None):
    """
    cols   : [(encabezado, alineación, ancho_relativo)]
    filas  : lista de listas de str (la última puede ser TOTAL)
    tintes : dict (fila, col) -> color de fondo
    barras : dict fila -> color de barra de identidad (combustible)
    negritas: set de filas con el nombre en negrita
    """
    if titulo:
        fig.text(x, y, titulo, fontsize=9.5, fontweight="bold", color=INK,
                 va="top")
        y -= 0.017
    ax = fig.add_axes([x, y - alto, ancho, alto]); ax.axis("off")
    anchos = [c[2] for c in cols]
    t = ax.table(cellText=filas, colLabels=[c[0] for c in cols],
                 colWidths=[a / sum(anchos) for a in anchos],
                 loc="upper center", cellLoc="center", bbox=[0, 0, 1, 1])
    t.auto_set_font_size(False)
    n_filas = len(filas)
    for (r, c), cell in t.get_celld().items():
        cell.set_edgecolor("#E8EBEF"); cell.set_linewidth(0.4)
        if r == 0:
            cell.set_facecolor(INK)
            cell.set_text_props(color="white", fontweight="bold", fontsize=6.9)
            cell.set_height(cell.get_height() * 1.15)
        else:
            i = r - 1
            etq = filas[i][0].strip().upper()
            es_total = etq.startswith("TOTAL") or etq.startswith("ACUMULADO")
            es_nota = etq.startswith("NO COMPARABLES")
            bg = (TOTALBG if es_total else
                  ("#EDEFF2" if es_nota else (PANEL if i % 2 else "white")))
            teñida = bool(tintes) and (i, c) in tintes
            if teñida:
                bg = tintes[(i, c)]
            bold = es_total or (negritas and i in negritas and c == 0) or teñida
            color_txt = INK if es_total else (MUTED if es_nota else INK2)
            if teñida:                      # texto del mismo tono que el fondo
                color_txt = TXPOS if bg == TPOS else TXNEG
            # v6·3 · celda de combustible rellena de borde a borde
            if relleno_etq and c == 0 and i in relleno_etq:
                bg, color_txt = relleno_etq[i]
                bold = True
            cell.set_facecolor(bg)
            cell.set_text_props(color=color_txt, fontsize=7.2,
                                fontweight="bold" if bold else "normal")
        cell.set_text_props(ha={"r": "right", "l": "left"}.get(cols[c][1], "center"))
        if cols[c][1] == "l":
            # Sangría extra en la etiqueta para que la barra de identidad
            # del combustible no pise el texto.
            cell.PAD = 0.09 if barras else 0.05
    # Barras de identidad de combustible (A4: solo en la etiqueta)
    if barras:
        for i, color in barras.items():
            cy = 1 - (i + 1.5) / (n_filas + 1)
            ax.add_patch(plt.Rectangle((0.004, cy - 0.5 / (n_filas + 1)), 0.006,
                                       1 / (n_filas + 1) * 0.72, color=color,
                                       transform=ax.transAxes, zorder=5))
    return y - alto - 0.014


def _lecturas(fig, y, textos, colores):
    """
    Bloques de lectura con barra de color, uno por combustible. Omite los
    vacíos (reflow). El texto se envuelve y respeta los saltos de línea, así
    que una lectura larga crece hacia abajo en vez de salirse de la hoja.
    """
    for txt, col in zip(textos, colores):
        if not txt:
            continue
        lineas = _renglones(txt)
        alto = 0.004 + SALTO_TXT * len(lineas)
        fig.patches.append(plt.Rectangle((0.055, y - alto), 0.005, alto,
                                         transform=fig.transFigure, color=col))
        yy = y - 0.002
        for ln, _ in lineas:
            if ln:
                fig.text(0.070, yy, ln, fontsize=8.6, color=INK2, va="top")
            yy -= SALTO_TXT
        y -= alto + 0.009
    return y


ANCHO_TXT = 108          # caracteres por renglón
SALTO_TXT = 0.0158       # alto de renglón en fracción de figura


def _renglones(texto):
    """
    Convierte el texto manual en renglones listos para dibujar.

    RESPETA LOS SALTOS DE LÍNEA: cada línea del cuadro de texto se envuelve por
    separado, las líneas en blanco se conservan como separación, y las que
    empiezan con -, *, • o · se dibujan como viñeta con sangría francesa.
    Devuelve [(texto, es_viñeta_continuación)].
    """
    import textwrap
    out = []
    crudo = str(texto).replace("\r\n", "\n").replace("\r", "\n")
    for linea in crudo.split("\n"):
        if not linea.strip():
            out.append(("", False))                      # renglón en blanco
            continue
        limpia = linea.strip()
        if limpia[:1] in "-*•·" and len(limpia) > 1:
            cuerpo = limpia[1:].strip()
            env = textwrap.wrap(cuerpo, width=ANCHO_TXT - 3) or [""]
            out.append(("•  " + env[0], False))
            out.extend((("   " + e), True) for e in env[1:])
        else:
            for e in (textwrap.wrap(limpia, width=ANCHO_TXT) or [""]):
                out.append((e, False))
    while out and out[-1][0] == "":                      # sin colas vacías
        out.pop()
    return out


def _texto_libre(fig, y, texto):
    """
    Espacio de análisis manual. Sin rótulo: el texto se integra al reporte.
    Si está vacío NO imprime nada y lo que sigue sube a ocupar su lugar.
    """
    if not texto or not str(texto).strip():
        return y
    lineas = _renglones(texto)
    alto = 0.006 + SALTO_TXT * len(lineas)
    fig.patches.append(plt.Rectangle((0.055, y - alto), 3 / 72 / 8.5, alto,
                                     transform=fig.transFigure, color=SER2))
    yy = y - 0.004
    for ln, _ in lineas:
        if ln:
            fig.text(0.068, yy, ln, fontsize=9, color=INK2, va="top")
        yy -= SALTO_TXT
    return y - alto - 0.012


def _alto_bloque(texto):
    """Espacio vertical que ocupará un bloque de análisis (0 si está vacío)."""
    if not texto or not str(texto).strip():
        return 0.0
    return 0.006 + SALTO_TXT * len(_renglones(texto)) + 0.012


def _alto_bloque_c(texto):
    """Alto de un bloque CON rótulo (0 si está vacío)."""
    if not texto or not str(texto).strip():
        return 0.0
    return 0.020 + SALTO_TXT * len(_renglones(texto)) + 0.012


def _bloque_c(fig, y, titulo, texto, color):
    """
    Bloque con rótulo propio y barra de color (Causa del crecimiento / Causa
    de la caída). Si está vacío NO se imprime nada, ni el rótulo.
    El cuerpo envuelve y respeta saltos de línea y viñetas.
    """
    if not texto or not str(texto).strip():
        return y
    lineas = _renglones(texto)
    alto = 0.020 + SALTO_TXT * len(lineas)
    fig.patches.append(plt.Rectangle((0.055, y - alto), 0.005, alto,
                                     transform=fig.transFigure, color=color))
    fig.text(0.070, y - 0.002, titulo, fontsize=8.5, fontweight="bold",
             color=INK, va="top")
    yy = y - 0.019
    for ln, _ in lineas:
        if ln:
            fig.text(0.070, yy, ln, fontsize=9, color=INK2, va="top")
        yy -= SALTO_TXT
    return y - alto - 0.012


# ----------------------------------------------------------------------
# Tintes condicionales (PARTE D)
# ----------------------------------------------------------------------
def _presupuesto(pagina, requerido, disponible=0.86):
    """D6 · imprime en consola el presupuesto vertical de cada página."""
    estado = "OK" if requerido <= disponible + 1e-9 else "DESBORDA"
    print(f"[PDF] {pagina:<34} requiere {requerido:.3f} / {disponible:.3f} — {estado}")
    return requerido <= disponible + 1e-9


def _grafica_trimestral(fig, bd, y_top, y_bot):
    """v6·5 · una línea por año sobre el eje de trimestres, con etiquetas
    directas, valores de 2026, banda de variación, máximo histórico y nota."""
    t = tb.ventas_trimestrales(bd)
    fig.text(0.055, y_top, "VENTAS TRIMESTRALES POR AÑO · millones de litros",
             fontsize=9.5, fontweight="bold", color=INK, va="top")
    ax = fig.add_axes([0.075, y_bot + 0.052, 0.79, y_top - 0.020 - y_bot - 0.052])
    qs = ["Q1", "Q2", "Q3", "Q4"]
    x = np.arange(4)
    ult = int(t.index.max())

    for anio in sorted(t.index):
        col, lw, ms, alpha = RAMPA.get(int(anio), (MUTED, 1.0, 0, 0.7))
        v = t.loc[anio, qs].astype(float).values / 1e6
        ax.plot(x, v, color=col, lw=lw, alpha=alpha, zorder=int(anio) - 2000,
                marker="o" if ms else None, markersize=ms,
                markerfacecolor=col, markeredgecolor="white", markeredgewidth=1.2)
        # a) etiqueta directa al final de la línea (sin caja de leyenda)
        idx = np.where(~np.isnan(v))[0]
        if len(idx):
            ax.annotate(str(int(anio)), (x[idx[-1]], v[idx[-1]]),
                        xytext=(7, 0), textcoords="offset points", va="center",
                        fontsize=8, color=col,
                        fontweight="bold" if int(anio) == ult else "normal")
        # b) valor sobre cada punto del año en curso
        if int(anio) == ult:
            for xi, vi in zip(x[idx], v[idx]):
                ax.annotate(f"{vi:,.1f}", (xi, vi), xytext=(0, 10),
                            textcoords="offset points", ha="center", fontsize=8,
                            fontweight="bold", color=col)

    # d) máximo histórico
    mx = t.stack().astype(float)
    a_mx, q_mx = mx.idxmax()
    v_mx = mx.max() / 1e6
    ax.plot([qs.index(q_mx)], [v_mx], marker="o", ms=9, mfc="none",
            mec=MUTED, mew=1.3, zorder=99)
    ax.annotate(f"máximo histórico\n{int(a_mx)} {q_mx} = {v_mx:,.1f} M L",
                (qs.index(q_mx), v_mx), xytext=(-12, 14),
                textcoords="offset points", ha="right", fontsize=7, color=MUTED)

    ax.set_xticks(x); ax.set_xticklabels(qs, fontsize=9, color=INK2)
    # Eje desde 15 M para que las líneas no queden apachurradas arriba. Si en
    # algún año el volumen bajara de ahí, el piso se ajusta solo (no recorta).
    piso_y = min(15.0, np.floor(float(mx.min()) / 1e6))
    ax.set_ylim(piso_y, float(mx.max()) / 1e6 * 1.06)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(5))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: f"{v:,.0f} M"))
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.grid(axis="y", color=GRID, lw=0.7); ax.set_axisbelow(True)
    ax.tick_params(labelsize=8, colors=MUTED, length=0)
    ax.set_xlim(-0.12, 3.35)

    # c) banda de variación del año en curso contra el anterior
    yb = y_bot + 0.030
    if ult - 1 in t.index:
        partes = []
        for q in qs:
            a, b = t.loc[ult, q], t.loc[ult - 1, q]
            if pd.isna(a) or pd.isna(b):
                partes.append((q, None, None))
            else:
                partes.append((q, a - b, 100 * (a / b - 1)))
        for i, (q, dv, pc) in enumerate(partes):
            xpos = 0.10 + i * 0.215
            if dv is None:
                fig.text(xpos, yb, f"{q}  —", fontsize=7.5, color=MUTED, va="center")
            else:
                fig.text(xpos, yb,
                         f"{q}  {'+' if dv >= 0 else MENOS}{abs(dv)/1e3:,.0f} K L  "
                         f"({_sg(pc)})", fontsize=7.5,
                         color=BUENO if dv >= 0 else MALO, va="center")
    # e) nota metodológica
    fig.text(0.055, y_bot + 0.010,
             "Solo trimestres completos. Se omiten 2021 Q1 (la base inicia el "
             "20 de marzo de 2021) y el trimestre en curso.",
             fontsize=6.5, color=MUTED, style="italic", va="center")
    return y_bot


def _meses(dfm) -> set:
    """Periodos mensuales con datos de margen (para validar comparaciones)."""
    return set(dfm[mg.COL_FECHA].dt.to_period("M").unique())


def _guion_no_comparables(filas):
    """W4 · en la fila de conciliación, 'nada que conciliar' se imprime como —
    (no 'n/a', que en las filas de estación significa 'sin base comparable')."""
    for f in filas:
        if str(f[0]).strip().upper().startswith("NO COMPARABLES"):
            for i, v in enumerate(f):
                if v == "n/a":
                    f[i] = "—"
    return filas


def _es_resumen(etq) -> bool:
    e = str(etq).strip().upper()
    return (e.startswith("TOTAL") or e.startswith("NO COMPARABLES")
            or e.startswith("ACUMULADO"))


def _tintes_var(df, cols_pct, umbral, col_idx):
    """
    v6·2 · el umbral se evalúa sobre el PORCENTAJE, pero el tinte se pinta en
    la columna de VALOR ABSOLUTO (col_idx apunta ahora a Var. 2025 / Var. 2024).
    Las columnas de porcentaje quedan sin color.
    """
    t = {}
    for i, (_, row) in enumerate(df.iterrows()):
        if _es_resumen(row["Etiqueta"]):
            continue
        for nombre, c in zip(cols_pct, col_idx):
            v = row.get(nombre)
            if pd.notna(v) and abs(v) >= umbral:
                t[(i, c)] = TPOS if v > 0 else TNEG
    return t


# ======================================================================
# PÁGINA 1 · Ventas del mes
# ======================================================================
def _p1(pdf, bd, dfm, per, per_base, txt):
    lbl = mg.etiqueta_periodo(per)
    mes_nom = tb.MES_NOMBRE[per.month].capitalize()
    fig = _pagina(f"Resultados de ventas · {mes_nom} {per.year}", "",
                  subtitulo_banda=(f"Grupo Treher    ·    base de comparación: "
                                   f"{tb.MES_NOMBRE[per.month]} {per.year-1} y "
                                   f"{tb.MES_NOMBRE[per.month]} {per.year-2}"))
    y = _titulares(fig, txt("p1.titular"), txt("p1.subtitulo"), y=0.888)

    a = tb._mes(bd, per)
    venta = a[cfg.COL_TOTAL_VENTA].sum(min_count=1)
    lts = a[cfg.COL_TOTAL_LTS].sum(min_count=1)
    b = tb._mes(bd, per - 12)
    v25, l25 = (b[cfg.COL_TOTAL_VENTA].sum(min_count=1),
                b[cfg.COL_TOTAL_LTS].sum(min_count=1))
    p_act, p_ant = venta / lts, (v25 / l25 if l25 else np.nan)
    cre = tb.crecimiento_comparable(bd, per)
    y = _tarjetas(fig, y, [
        ("VENTA", _M(venta), f"{_sg(100*(venta/v25-1))} vs {lbl}".replace(lbl, f"{per.year-1}")),
        ("VOLUMEN", f"{lts/1e6:,.2f} M L", _sg(100 * (lts / l25 - 1)) + f" vs {per.year-1}"),
        ("PRECIO PROMEDIO", f"${p_act:,.2f} /L",
         f"{'+' if p_act >= p_ant else MENOS}${abs(p_act-p_ant):,.2f} vs {per.year-1}"),
        ("ACUMULADO", f"{cre.iloc[0]['A']/1e6:,.1f} M L",
         _sg(cre.iloc[0]["Var25"]) + f" vs {per.year-1}"),
    ], destacada=0)

    # Tabla A · volumen
    vc = tb.volumen_combustible(bd, per)
    filas = [[r["Etiqueta"], _num(r["Litros"]), _pct(r["Mix"]), _sg(r["Var25"], 0, ""),
              _sg(r["Evol25"]), _sg(r["Var24"], 0, ""), _sg(r["Evol24"])]
             for _, r in vc.iterrows()]
    t = _tintes_var(vc, ["Evol25", "Evol24"], 4.0, [3, 5])
    relleno = {i: FUEL_BG[r["Etiqueta"]] for i, r in vc.iterrows()
               if r["Etiqueta"] in FUEL_BG}
    y = _tabla(fig, y, 0.105,
               [("Combustible", "l", 1.5), ("Litros", "r", 1.2), ("Mix", "r", .8),
                (f"Var. {per.year-1}", "r", 1.2), ("Evol. %", "r", .9),
                (f"Var. {per.year-2}", "r", 1.2), ("Evol. %", "r", .9)],
               filas, "VOLUMEN · litros", t, relleno_etq=relleno)

    # Tabla B · importe
    ic = tb.importe_combustible(bd, per)
    filas = [[r["Etiqueta"], _pesos(r["Importe"]), _pct(r["Mix"]),
              _pesos_var(r["Var25"]), _sg(r["Evol25"]),
              f"${r['Precio_ant']:,.2f}", f"${r['Precio_act']:,.2f}"]
             for _, r in ic.iterrows()]
    t = _tintes_var(ic, ["Evol25"], 4.0, [3])
    y = _tabla(fig, y, 0.105,
               [("Combustible", "l", 1.5), ("Importe", "r", 1.5), ("Mix", "r", .8),
                (f"Var. {per.year-1}", "r", 1.4), ("Evol. %", "r", .9),
                (f"Precio {per.year-1}", "r", 1.0), (f"Precio {per.year}", "r", 1.0)],
               filas, "IMPORTE · pesos", t, relleno_etq=relleno)

    # Gráfica: barras agrupadas de volumen por combustible (G3: nombre escrito)
    ax = fig.add_axes([0.10, y - 0.20, 0.80, 0.185])
    x = np.arange(len(cfg.PRODUCTOS)); w = 0.31
    v_act = [vc.set_index("Etiqueta").loc[p, "Litros"] / 1e6 for p in cfg.PRODUCTOS]
    v_ant = [(vc.set_index("Etiqueta").loc[p, "Litros"] -
              vc.set_index("Etiqueta").loc[p, "Var25"]) / 1e6 for p in cfg.PRODUCTOS]
    # C7 · la leyenda no puede sugerir que el negro identifica a 2026: se
    # rotulan los años directamente sobre el primer par de barras.
    ax.bar(x - w/2, v_ant, w, color="#C6CDD6")
    ax.bar(x + w/2, v_act, w, color=[FUEL[p] for p in cfg.PRODUCTOS])
    for xi, (va, vb) in enumerate(zip(v_ant, v_act)):
        ax.text(xi - w/2, va, f"{va:,.2f}", ha="center", va="bottom", fontsize=6.6,
                color=MUTED)
        ax.text(xi + w/2, vb, f"{vb:,.2f}", ha="center", va="bottom", fontsize=6.6,
                color=INK, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(cfg.PRODUCTOS, fontsize=8, color=INK2)
    ax.set_ylabel("millones de litros", fontsize=7, color=MUTED)
    # Años rotulados directamente sobre el primer par (sin leyenda de color)
    for dx, txt_a, col in ((-w/2, str(per.year - 1), MUTED),
                           (w/2, str(per.year), INK)):
        ax.text(dx, max(max(v_act), max(v_ant)) * 1.17, txt_a, ha="center",
                fontsize=7.4, fontweight="bold", color=col)
    ax.set_ylim(0, max(max(v_act), max(v_ant)) * 1.28)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.grid(axis="y", color=GRID, lw=0.7); ax.set_axisbelow(True)
    ax.tick_params(labelsize=6.8, colors=MUTED, length=0)
    y -= 0.215

    y = _lecturas(fig, y, [txt(f"p1.lectura.{i}") for i in (1, 2, 3, 4)],
                  [FUEL["Diésel"], FUEL["Premium"], FUEL["Regular"], SER1])
    # Espacio de análisis manual bajo la gráfica (vacío ⇒ no imprime nada).
    # Es la página más apretada del reporte: la consola avisa si se aprieta.
    y = _texto_libre(fig, y - 0.008, txt("ventas_mes.analisis"))
    _presupuesto("1 · ventas del mes", 0.905 - y)
    _pie(fig, 1)
    pdf.savefig(fig); plt.close(fig)


# ======================================================================
# PÁGINA 2 · Desempeño por estación
# ======================================================================
def _p2(pdf, bd, dfm, per, per_base, txt):
    lbl = mg.etiqueta_periodo(per)
    fig = _pagina("Desempeño por estación", f"{lbl}  ·  base: {mg.etiqueta_periodo(per-12)} y {mg.etiqueta_periodo(per-24)}")
    y = _titulares(fig, txt("p2.titular"), txt("p2.subtitulo"))

    ve = tb.volumen_estacion(bd, per)
    filas = [[r["Etiqueta"], _num(r["Litros"]), _pct(r["Mix"]), _sg(r["Var25"], 0, ""),
              _sg(r["Evol25"]), _sg(r["Var24"], 0, ""), _sg(r["Evol24"])]
             for _, r in ve.iterrows()]
    filas = _guion_no_comparables(filas)
    t = _tintes_var(ve, ["Evol25", "Evol24"], 8.0, [3, 5])
    neg = {i for i, r in ve.iterrows()
           if pd.notna(r["Evol25"]) and abs(r["Evol25"]) > 15
           and not _es_resumen(r["Etiqueta"])}
    # v6·4A · volumen + gráfica que ocupa TODO el espacio restante de la hoja
    ALTO_T = 0.293
    y = _tabla(fig, y, ALTO_T,
               [("Estación", "l", 1.6), ("Litros", "r", 1.2), ("Mix", "r", .8),
                (f"Var. {per.year-1} ({ve.attrs['panel25']} est.)", "r", 1.3),
                ("Evol. %", "r", .9),
                (f"Var. {per.year-2} ({ve.attrs['panel24']} est.)", "r", 1.3),
                ("Evol. %", "r", .9)],
               filas, "VOLUMEN POR ESTACIÓN · litros", t, negritas=neg)

    # Las causas de crecimiento y caída se movieron a la hoja 3, bajo la tabla
    # de IMPORTE POR ESTACIÓN.

    d = ve[~ve["Etiqueta"].map(_es_resumen) & ve["Var25"].notna()].sort_values("Var25")
    fig.text(0.055, y, f"VARIACIÓN DE VOLUMEN POR ESTACIÓN · miles de litros "
             f"vs. {mg.etiqueta_periodo(per-12)}", fontsize=9.5,
             fontweight="bold", color=INK, va="top")
    # Se expande hasta 24 pt sobre el pie; con más aire las etiquetas van a
    # 7.5 pt y horizontales si caben.
    piso = 0.045 + 24 / 72 / 11
    # Horizontales solo si de verdad caben; con nombres largos se encimarían.
    ancho_disp = 0.89 / max(len(d), 1) * 8.5 * 72          # puntos por columna
    horizontal = bool(len(d) and max(len(e) for e in d["Etiqueta"]) * 4.6 < ancho_disp)
    alto_etq = 0.020 if horizontal else 0.048
    ax = fig.add_axes([0.055, piso + alto_etq, 0.89,
                       max(0.10, y - 0.020 - piso - alto_etq)])
    rango = max(abs(d["Var25"].min()), abs(d["Var25"].max())) / 1e3
    ax.bar(range(len(d)), d["Var25"] / 1e3, width=0.62,
           color=[BUENO if v > 0 else MALO for v in d["Var25"]])
    for i, v in enumerate(d["Var25"] / 1e3):
        ax.text(i, v + (rango * 0.05 if v >= 0 else -rango * 0.05),
                f"{'+' if v >= 0 else MENOS}{abs(v):,.0f}", ha="center",
                va="bottom" if v >= 0 else "top", fontsize=7.5,
                fontweight="bold", color=INK)
    ax.set_xticks(range(len(d)))
    ax.set_xticklabels(d["Etiqueta"], fontsize=7.5, color=INK2,
                       rotation=0 if horizontal else 45,
                       ha="center" if horizontal else "right")
    ax.axhline(0, color=INK2, lw=0.9)
    ax.set_ylim(-rango * 1.35, rango * 1.35)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.set_yticks([])
    ax.tick_params(axis="x", length=0, pad=2)
    _presupuesto("2A · desempeño por estación (volumen)", 0.054 + 0.017 + ALTO_T)

    _pie(fig, 2)
    pdf.savefig(fig); plt.close(fig)


# ======================================================================
# PÁGINA 3 · Desempeño por estación · importe (v6·4B)
# ======================================================================
def _p2b(pdf, bd, dfm, per, per_base, txt):
    lbl = mg.etiqueta_periodo(per)
    fig = _pagina("Desempeño por estación",
                  f"Importe · {tb.MES_NOMBRE[per.month]} {per.year}")
    y = 0.905
    ie = tb.importe_estacion(bd, per)
    filas = [[r["Etiqueta"], _pesos(r["Importe"]), _pct(r["Mix"]),
              _pesos_var(r["Var25"]), _sg(r["Evol25"]), f"${r['Precio_act']:,.2f}"]
             for _, r in ie.iterrows()]
    t = _tintes_var(ie, ["Evol25"], 8.0, [3])
    alto = 0.028 + 0.0235 * len(filas)
    y = _tabla(fig, y, alto,
               [("Estación", "l", 1.6), ("Importe", "r", 1.5), ("Mix", "r", .8),
                (f"Var. {per.year-1}", "r", 1.4), ("Evol. %", "r", .9),
                ("Precio prom.", "r", 1.0)],
               filas, "IMPORTE POR ESTACIÓN · pesos", t)

    # Espacios de análisis (vacíos ⇒ no imprimen nada). Las causas conservan
    # su rótulo y su color; el bloque libre va sin rótulo.
    y -= 0.010
    y = _bloque_c(fig, y, "Causa del crecimiento", txt("p2.causa.1"), BUENO)
    y = _bloque_c(fig, y, "Causa de la caída", txt("p2.causa.2"), MALO)
    y = _texto_libre(fig, y, txt("desempeno_estacion.conclusiones"))
    _presupuesto("3 · desempeño por estación (importe)", 0.017 + alto + 0.010
                 + _alto_bloque_c(txt("p2.causa.1"))
                 + _alto_bloque_c(txt("p2.causa.2"))
                 + _alto_bloque(txt("desempeno_estacion.conclusiones")))
    _pie(fig, 3)
    pdf.savefig(fig); plt.close(fig)


# ======================================================================
# PÁGINA 3 · Variación por estación (gráfica a página completa)
# ======================================================================
def _p3_grafica(pdf, bd, dfm, per, per_base, txt):
    lbl = mg.etiqueta_periodo(per)
    fig = _pagina("Desempeño por estación", f"{lbl}  ·  base: {mg.etiqueta_periodo(per-12)} y {mg.etiqueta_periodo(per-24)}")
    fig.text(0.055, 0.905, "Variación de volumen por estación", fontsize=13,
             fontweight="bold", color=INK, va="top")
    fig.text(0.055, 0.881, f"Miles de litros contra el mismo mes de {per.year-1}. "
             "Solo estaciones con base comparable.", fontsize=10, color=INK2,
             va="top")

    ve = tb.volumen_estacion(bd, per)
    d = ve[~ve["Etiqueta"].map(_es_resumen) & ve["Var25"].notna()].sort_values("Var25")
    ax = fig.add_axes([0.20, 0.10, 0.74, 0.74])
    colores = [POS if v > 0 else NEG for v in d["Var25"]]
    ax.barh(range(len(d)), d["Var25"] / 1e3, color=colores, height=0.64)
    ax.set_yticks(range(len(d)))
    ax.set_yticklabels(d["Etiqueta"], fontsize=10.5, color=INK)
    rango = max(abs(d["Var25"].min()), abs(d["Var25"].max())) / 1e3
    for i, v in enumerate(d["Var25"] / 1e3):
        ax.text(v + (rango * 0.02 if v >= 0 else -rango * 0.02), i,
                f"{'+' if v >= 0 else MENOS}{abs(v):,.0f}", va="center",
                ha="left" if v >= 0 else "right", fontsize=9.5,
                fontweight="bold", color=INK)
    ax.set_xlabel(f"miles de litros vs. {mg.etiqueta_periodo(per-12)}",
                  fontsize=9.5, color=MUTED)
    ax.axvline(0, color=INK2, lw=1.1)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.grid(axis="x", color=GRID, lw=0.8); ax.set_axisbelow(True)
    ax.tick_params(labelsize=9, colors=MUTED, length=0)
    ax.set_xlim(-rango * 1.30, rango * 1.30)

    _pie(fig, "Fuente: BD. Se excluyen las estaciones sin base comparable "
              "contra el año anterior.", 3)
    pdf.savefig(fig); plt.close(fig)


# ======================================================================
# PÁGINA 3 · Desempeño acumulado
# ======================================================================
def _p3(pdf, bd, dfm, per, per_base, txt):
    fig = _pagina("Desempeño acumulado",
                  f"Enero {MENOS} {mg.etiqueta_periodo(per)}  ·  base: YTD año anterior")
    y = _titulares(fig, txt("p3.titular"), txt("p3.subtitulo"))

    va = tb.volumen_acumulado_estacion(bd, per)
    filas = [[r["Etiqueta"], _num(r["Litros"]), _pct(r["Mix"]), _sg(r["Var25"], 0, ""),
              _sg(r["Evol25"]), _sg(r["Var24"], 0, ""), _sg(r["Evol24"])]
             for _, r in va.iterrows()]
    filas = _guion_no_comparables(filas)
    t = _tintes_var(va, ["Evol25", "Evol24"], 8.0, [3, 5])
    y = _tabla(fig, y, 0.288,
               [("Estación", "l", 1.6), ("Litros", "r", 1.3), ("Mix", "r", .8),
                (f"Var. {per.year-1} ({va.attrs['panel25']} est.)", "r", 1.3),
                ("Evol. %", "r", .9),
                (f"Var. {per.year-2} ({va.attrs['panel24']} est.)", "r", 1.3),
                ("Evol. %", "r", .9)],
               filas, "VOLUMEN ACUMULADO POR ESTACIÓN · litros", t)

    # C4 · nota de comparabilidad (categoría C: si está vacía no se imprime)
    nota_c = txt("p3.nota")
    if nota_c:
        fig.text(0.055, y + 0.004, nota_c, fontsize=8, color=MUTED,
                 style="italic", va="top")
        y -= 0.020

    # v6·5 · la tabla CRECIMIENTO COMPARABLE se sustituye por la trayectoria
    # trimestral de seis años (lo que ninguna otra pieza del reporte muestra).
    concl = txt("acumulado.conclusiones")
    alto_concl = _alto_bloque(concl)
    _grafica_trimestral(fig, bd, y - 0.006, 0.052 + alto_concl)
    if concl:
        _texto_libre(fig, 0.046 + alto_concl, concl)
    _presupuesto("4 · desempeño acumulado", 0.054 + 0.017 + 0.288 + 0.22)
    _pie(fig, 4)
    pdf.savefig(fig); plt.close(fig)


# ======================================================================
# PÁGINA 4 · Rentabilidad
# ======================================================================
def _p4(pdf, bd, dfm, per, per_base, txt):
    lblb = mg.etiqueta_periodo(per_base)
    fig = _pagina("Rentabilidad", f"{mg.etiqueta_periodo(per)}  ·  base: {lblb}")
    y = _titulares(fig, txt("p4.titular"), txt("p4.subtitulo"))

    r = ej.margen_sobre_venta(bd, dfm, per)
    acum = (sum(ej.margen_sobre_venta(bd, dfm, pd.Period(f"{per.year}-{m:02d}"))
                ["margen_bruto"] for m in range(1, per.month + 1)))
    # C5 · toda tarjeta lleva su comparación (contra el mismo mes del año anterior)
    meses = _meses(dfm)
    yoy = per - 12
    r_y = ej.margen_sobre_venta(bd, dfm, yoy) if yoy in meses else None
    lbl_y = mg.etiqueta_periodo(yoy)
    if r_y:
        d_mb = _sg(100 * (r["margen_bruto"] / r_y["margen_bruto"] - 1)) + f" vs {lbl_y}"
        d_sv = f"vs {r_y['margen_sobre_venta_%']:,.2f}% en {lbl_y}"
        dmu = r["margen_unitario"] - r_y["margen_unitario"]
        d_mu = f"{'+' if dmu >= 0 else MENOS}${abs(dmu):,.3f} vs {lbl_y}"
        acum_y = sum(ej.margen_sobre_venta(bd, dfm,
                     pd.Period(f"{per.year-1}-{m:02d}"))["margen_bruto"]
                     for m in range(1, per.month + 1)
                     if pd.Period(f"{per.year-1}-{m:02d}") in meses)
        d_ac = (_sg(100 * (acum / acum_y - 1)) + f" vs {per.year-1}"
                if acum_y else f"ene{MENOS}{lbl_y.split()[0].lower()}")
    else:
        d_mb = d_sv = d_mu = d_ac = f"vs {lblb}"
    y = _tarjetas(fig, y, [
        ("MARGEN BRUTO", _M(r["margen_bruto"]), d_mb),
        ("MARGEN SOBRE VENTA", f"{r['margen_sobre_venta_%']:,.2f}%", d_sv),
        ("MARGEN UNITARIO", f"${r['margen_unitario']:,.3f} /L", d_mu),
        ("ACUMULADO", _M(acum), d_ac),
    ], destacada=0)

    # Cascada (waterfall) — protagonista
    dec = ej.descomposicion_margen(dfm, per, per_base).set_index("Concepto")
    base = dec.loc["Margen base", "Monto_$"]
    ef = [dec.loc["Efecto volumen", "Monto_$"], dec.loc["Efecto mix", "Monto_$"],
          dec.loc["Efecto margen unitario", "Monto_$"]]
    fin = dec.loc["Margen actual", "Monto_$"]
    ax = fig.add_axes([0.10, y - 0.208, 0.80, 0.172])
    etiquetas = [f"Margen\n{lblb}", "Efecto\nvolumen", "Efecto\nmix",
                 "Efecto margen\nunitario", f"Margen\n{mg.etiqueta_periodo(per)}"]
    vals = [base] + ef + [fin]
    # v6·2 · la cascada usa la paleta de desempeño (azul = suma, naranja = resta)
    colores = [INK, BUENO if ef[0] >= 0 else MALO, MUTED,
               BUENO if ef[2] >= 0 else MALO, INK]
    acumul = base
    for i, (v, c) in enumerate(zip(vals, colores)):
        if i in (0, 4):                       # columnas ancla (inicio y fin)
            ax.bar(i, v / 1e6, 0.60, color=c)
            ytxt, nivel = v / 1e6, v
        else:                                 # tramo entre acumulados
            ini = acumul
            acumul += v
            ax.bar(i, abs(v) / 1e6, 0.60, bottom=min(ini, acumul) / 1e6, color=c)
            ytxt, nivel = max(ini, acumul) / 1e6, acumul
        ax.text(i, ytxt, _M(v), ha="center", va="bottom", fontsize=7,
                fontweight="bold", color=INK)
        # Conector punteado al nivel del acumulado (sin él se lee como barras sueltas)
        if i < 4:
            ax.plot([i + 0.30, i + 0.70], [nivel / 1e6] * 2, ls=(0, (3, 2)),
                    lw=0.8, color=MUTED, zorder=1)
    # A2 · la última barra debe cerrar exactamente sobre el total final
    assert abs(acumul - fin) < 1, f"Cascada descuadrada: {acumul:,.0f} vs {fin:,.0f}"
    ax.set_xticks(range(5))
    ax.set_xticklabels(etiquetas, fontsize=7, color=INK2)
    ax.set_ylabel("millones de pesos", fontsize=7, color=MUTED)
    ax.set_ylim(0, max(base, fin) / 1e6 * 1.22)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.grid(axis="y", color=GRID, lw=0.7); ax.set_axisbelow(True)
    ax.tick_params(labelsize=6.8, colors=MUTED, length=0, pad=2)
    y -= 0.246                       # deja aire para las etiquetas de 2 líneas

    # La caja de conclusión automática se retiró: el único texto bajo la
    # cascada es el que escribe dirección.
    y -= 0.012
    y = _texto_libre(fig, y, txt("rentabilidad.analisis"))

    # v5·3 · EVOLUCIÓN MENSUAL (serie histórica: sin tintes de comparación)
    ev = tb.evolucion_mensual(bd, dfm, per.year, hasta=per)
    filas = [[r2["Mes"], _num(r2["Volumen"]), _pesos(r2["Ingreso"]),
              _pesos(r2["Margen"]), _pct(r2["Margen_pct"], 2)]
             for _, r2 in ev.iterrows()]
    _tabla(fig, y, 0.028 + 0.0205 * len(filas),
           [("Mes", "l", 1.6), ("Volumen (L)", "r", 1.3), ("Ingreso", "r", 1.5),
            ("Margen bruto", "r", 1.4), ("Margen bruto %", "r", 1.1)],
           filas, f"EVOLUCIÓN MENSUAL {per.year}")
    # Sin espacio de análisis bajo esta tabla (decisión de dirección).
    # D6 · presupuesto: la cascada + esta tabla ya llenan la hoja, así que
    # MARGEN POR ESTACIÓN pasa completa a la hoja siguiente (regla D2).
    _presupuesto("5 · rentabilidad",
                 0.054 + 0.103 + 0.246 + 0.012 + 0.017 + 0.028 + 0.0205 * len(filas)
                 + _alto_bloque(txt("rentabilidad.analisis")))
    _pie(fig, 5)
    pdf.savefig(fig); plt.close(fig)


# ======================================================================
# PÁGINA 5 · Rentabilidad (cont.) — margen por estación
# ======================================================================
def _p4b(pdf, bd, dfm, per, per_base, txt):
    """D2 · el bloque que no cabe entero pasa completo a una hoja nueva.
    D5 · hereda la banda de la sección y declara su base de comparación."""
    import textwrap
    fig = _pagina("Rentabilidad · por estación",
                  f"{mg.etiqueta_periodo(per)}  ·  base: {mg.etiqueta_periodo(per-1)}")
    y = 0.905
    nota = txt("p4.nota")
    if nota:                                   # se envuelve para no desbordar
        for linea in textwrap.wrap(nota, width=104)[:3]:
            fig.text(0.055, y, linea, fontsize=10, color=INK2, va="top")
            y -= 0.020
        y -= 0.010

    # Dos tablas: las 3 mayores alzas y las 3 mayores caídas contra el mes
    # anterior. El % se calcula dentro de cada grupo, nunca sobre el neto.
    alzas, bajas = tb.margen_alzas_bajas(bd, dfm, per, n=3)
    lblp = mg.etiqueta_periodo(per - 1)
    cols = [("Estación", "l", 1.7), ("Margen bruto", "r", 1.3),
            ("Margen $/L", "r", 1.0), ("Margen s/venta", "r", 1.1),
            (f"Variación vs {lblp}", "r", 1.3)]

    def _bloque(d, titulo, col_pct, tinte, y0):
        if d.empty:
            return y0
        filas = [[r2["Etiqueta"], _pesos(r2["Margen"]),
                  "—" if pd.isna(r2["MgL"]) else f"${r2['MgL']:,.3f}",
                  "—" if pd.isna(r2["Mg_venta"]) else _pct(r2["Mg_venta"], 2),
                  _pesos_var(r2["Delta"]), _pct(abs(r2["Pct_grupo_mov"]))]
                 for _, r2 in d.iterrows()]
        t = {(i, 4): tinte for i, r2 in d.iterrows()
             if not _es_resumen(r2["Etiqueta"])}
        h = 0.028 + 0.0235 * len(filas)
        _tabla(fig, y0, h, cols + [(col_pct, "r", 1.0)], filas, titulo, t)
        return y0 - h - 0.017 - 0.030

    y = _bloque(alzas, "MAYORES ALZAS DE MARGEN", "% de las alzas", TPOS, y)
    y = _bloque(bajas, "MAYORES CAÍDAS DE MARGEN", "% de las bajas", TNEG, y)

    # Espacio de análisis bajo las tablas (vacío ⇒ no imprime nada)
    _texto_libre(fig, y + 0.006, txt("margen_estacion.analisis"))
    _presupuesto("6 · rentabilidad por estación", 0.905 - y
                 + _alto_bloque(txt("margen_estacion.analisis")))
    _pie(fig, 6)
    pdf.savefig(fig); plt.close(fig)


# ======================================================================
# API pública
# ======================================================================
def generar_pdf(bd, dfm, per, per_base, textos: dict | None = None) -> bytes:
    """
    `textos`: {id_bloque: texto}. Los bloques B sin texto usan el borrador
    automático; los C sin texto se omiten por completo.
    """
    per = tb._p(per)
    per_base = tb._p(per_base)
    textos = textos or {}
    draft = bo.generar(bd, dfm, per, per_base)

    def txt(bid):
        v = str(textos.get(bid, "") or "").strip()
        if v:
            return v
        # Un campo MANUAL vacío se queda vacío. Sin esta guarda, bastaba con
        # que `borradores` generara su id para que reapareciera el automático.
        if cmt.CATEGORIA.get(bid) == "C":
            return ""
        return draft.get(bid, "")          # B: borrador · C: "" → se omite

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        _p1(pdf, bd, dfm, per, per_base, txt)          # 1 ventas del mes
        _p2(pdf, bd, dfm, per, per_base, txt)          # 2 desempeño · volumen
        _p2b(pdf, bd, dfm, per, per_base, txt)         # 3 desempeño · importe
        _p3(pdf, bd, dfm, per, per_base, txt)          # 4 acumulado
        _p4(pdf, bd, dfm, per, per_base, txt)          # 5 rentabilidad
        _p4b(pdf, bd, dfm, per, per_base, txt)         # 6 margen por estación
    return buf.getvalue()
