"""
Generadores de borradores — categoría B (Python propone, dirección confirma).

REGLAS DURAS (no negociables):
  · Nunca usar verbos causales ("por", "debido a", "influenciado por"). Los
    generadores solo describen MAGNITUD, ORDEN y CONTEO. El "por qué" es
    categoría C: conocimiento humano que no está en la base.
  · Siempre respetar estaciones comparables: nunca contar una estación sin
    base en el periodo anterior.
  · Funcionan para cualquier mes.
  · Respetan el límite de caracteres de su bloque.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as cfg
from . import ejecutivo as ej
from . import margenes as mg
from . import tablas as tb

MES = tb.MES_NOMBRE


def _lista(nombres) -> str:
    nombres = list(nombres)
    if not nombres:
        return ""
    if len(nombres) == 1:
        return nombres[0]
    return ", ".join(nombres[:-1]) + " y " + nombres[-1]


def _M(x):
    return f"${x/1e6:,.1f} M"


def _ML(x):
    return f"{x/1e6:,.2f} M"


def _K(x):
    return f"{x/1e3:,.0f} K"


def _cap(texto, limite):
    """Nunca entrega un borrador que exceda su límite."""
    return texto if len(texto) <= limite else texto[:limite - 1].rstrip() + "…"


# ----------------------------------------------------------------------
# PÁGINA 1 · ventas del mes
# ----------------------------------------------------------------------
def p1_titular(bd, per) -> str:
    per = tb._p(per)
    a = tb._mes(bd, per)
    venta = a[cfg.COL_TOTAL_VENTA].sum(min_count=1)
    lts = a[cfg.COL_TOTAL_LTS].sum(min_count=1)
    # ¿Es el mes más alto de la serie para ese mismo mes calendario?
    hist = (bd[bd[cfg.COL_FECHA].dt.month == per.month]
            .groupby(bd[cfg.COL_FECHA].dt.year)[cfg.COL_TOTAL_VENTA].sum())
    cola = ""
    if len(hist) > 1 and venta >= hist.max():
        cola = f": el mejor {MES[per.month]} de la serie"
    return _cap(f"{MES[per.month].capitalize()} cerró en {_M(venta)} y "
                f"{_ML(lts)} de litros{cola}.", 72)


def p1_subtitulo(bd, per) -> str:
    per = tb._p(per)
    t = tb.volumen_combustible(bd, per)
    f = t[t["Etiqueta"] != "TOTAL"].dropna(subset=["Var25"])
    if f.empty:
        return ""
    mayor = f.loc[f["Var25"].idxmax()]
    menor = f.loc[f["Var25"].idxmin()]
    if mayor["Var25"] <= 0:
        return _cap(f"Los tres combustibles retroceden frente a "
                    f"{MES[per.month]} de {per.year-1}.", 96)
    return _cap(f"El {mayor['Etiqueta'].lower()} encabeza el crecimiento en "
                f"volumen; {menor['Etiqueta'].lower()} retrocede "
                f"{abs(menor['Evol25']):.1f}% frente a {per.year-1}.", 96)


def p1_lecturas(bd, per) -> list[str]:
    per = tb._p(per)
    vol = tb.volumen_combustible(bd, per).set_index("Etiqueta")
    imp = tb.importe_combustible(bd, per).set_index("Etiqueta")
    out = []
    for p in cfg.PRODUCTOS:
        v, i = vol.loc[p], imp.loc[p]
        if pd.isna(v["Var25"]):
            out.append(_cap(f"{p}: {v['Litros']:,.0f} litros, "
                            f"{v['Mix']:.1f}% del volumen del mes.", 130))
            continue
        signo = "suma" if v["Var25"] >= 0 else "pierde"
        out.append(_cap(
            f"{p} {signo} {_K(abs(v['Var25']))} litros ({v['Evol25']:+.1f}%) "
            f"y su precio pasa de ${i['Precio_ant']:,.2f} a "
            f"${i['Precio_act']:,.2f}/L.", 130))
    tot_v, tot_i = vol.loc["TOTAL"], imp.loc["TOTAL"]
    t24 = (f"; contra {per.year-2} el volumen queda {tot_v['Evol24']:+.1f}%"
           if pd.notna(tot_v["Evol24"]) else "")
    out.append(_cap(f"El grupo cierra {tot_v['Evol25']:+.1f}% en litros y "
                    f"{tot_i['Evol25']:+.1f}% en pesos{t24}.", 130))
    return out


# ----------------------------------------------------------------------
# PÁGINA 2 · desempeño por estación
# ----------------------------------------------------------------------
def _delta_estaciones(bd, per):
    """Δ litros por estación, solo entre estaciones comparables."""
    per = tb._p(per)
    comp = tb.comparables(bd, per, per - 12)
    a = tb._mes(bd, per).groupby(cfg.COL_ESTACION)[cfg.COL_TOTAL_LTS].sum(min_count=1)
    b = tb._mes(bd, per - 12).groupby(cfg.COL_ESTACION)[cfg.COL_TOTAL_LTS].sum(min_count=1)
    return (a - b).reindex(sorted(comp)).dropna()


def p2_titular(bd, per, top: int = 3) -> str:
    per = tb._p(per)
    d = _delta_estaciones(bd, per).sort_values(ascending=False)
    ganan = d[d > 0]
    if ganan.empty:
        return _cap(f"Ninguna estación comparable creció en {MES[per.month]}.", 72)
    n = min(top, len(ganan))
    cob = ganan.head(n).sum() / ganan.sum() * 100
    verbo = "explican" if n > 1 else "explica"
    return _cap(f"{_lista(list(ganan.head(n).index))} {verbo} el {cob:.0f}% "
                f"del crecimiento del mes.", 72)


def p2_subtitulo(bd, per, peores: int = 2) -> str:
    per = tb._p(per)
    d = _delta_estaciones(bd, per).sort_values()
    caen, tot = int((d < 0).sum()), len(d)
    if tot == 0:
        return ""
    if caen == 0:
        return _cap(f"Las {tot} estaciones comparables venden más litros que en "
                    f"{MES[per.month]} de {per.year-1}.", 96)
    s = (f"{'Una' if caen == 1 else caen} de las {tot} estaciones comparables "
         f"vende{'' if caen == 1 else 'n'} menos que en {MES[per.month]} de "
         f"{per.year-1}")
    # Añade los líderes de la caída solo si el texto completo cabe en 110.
    for k in range(min(peores, caen), 0, -1):
        extra = (f"; {_lista(list(d.head(k).index))} "
                 f"lidera{'' if k == 1 else 'n'} la caída")
        if len(s + extra) + 1 <= 96:
            s += extra
            break
    return _cap(s + ".", 96)


# ----------------------------------------------------------------------
# PÁGINA 3 · desempeño acumulado
# ----------------------------------------------------------------------
def p3_titular(bd, per) -> str:
    c = tb.crecimiento_comparable(bd, per)
    tot, mm = c.iloc[0]["Var25"], c.iloc[1]["Var25"]
    verbo = "crece" if tot >= 0 else "retrocede"
    if abs(tot - mm) < 0.15:                     # ambas cifras coinciden
        return _cap(f"El acumulado {verbo} {abs(tot):.1f}% y lo comparable lo "
                    f"confirma.", 72)
    verbo_c = "crece" if mm >= 0 else "retrocede"
    if verbo == verbo_c:
        return _cap(f"El acumulado {verbo} {abs(tot):.1f}% y lo comparable "
                    f"{abs(mm):.1f}%.", 72)
    return _cap(f"El acumulado {verbo} {abs(tot):.1f}%, pero lo comparable "
                f"{verbo_c} {abs(mm):.1f}%.", 72)


def p3_subtitulo(bd, per) -> str:
    per = tb._p(per)
    c = tb.crecimiento_comparable(bd, per)
    tot, mm = c.iloc[0]["Var25"], c.iloc[1]["Var25"]
    n_ex = int(c.iloc[0]["N"] - c.iloc[1]["N"])
    v24, n_comp = c.iloc[1]["Var24"], int(c.iloc[1]["N"])
    if abs(tot - mm) < 0.15:
        # El panel de 2024 suele cubrir a todas: la lectura correcta es la del
        # grupo, no la del panel de 2025 (decisión "panel por año").
        return _cap(f"Las {n_comp} estaciones comparables crecen al mismo ritmo; "
                    f"contra {per.year-2} el grupo queda {v24:+.1f}%.", 96)
    plural = "estación" if n_ex == 1 else "estaciones"
    return _cap(f"{abs(tot-mm):.1f} puntos vienen de {n_ex} {plural} sin base "
                f"comparable; contra {per.year-2} quedan {v24:+.1f}%.", 96)


# ----------------------------------------------------------------------
# PÁGINA 4 · rentabilidad
# ----------------------------------------------------------------------
def p4_titular(bd, dfm, per) -> str:
    per = tb._p(per)
    r = ej.margen_sobre_venta(bd, dfm, per)
    prev = ej.margen_sobre_venta(bd, dfm, per - 1)
    verbo = "cayó a" if r["margen_bruto"] < prev["margen_bruto"] else "cerró en"
    return _cap(f"El margen bruto {verbo} {_M(r['margen_bruto'])}: de cada $100 "
                f"vendidos quedan ${r['margen_sobre_venta_%']:,.2f}.", 72)


def p4_subtitulo(bd, dfm, per, per_base) -> str:
    r = ej.margen_sobre_venta(bd, dfm, per)
    rb = ej.margen_sobre_venta(bd, dfm, per_base)
    d = r["margen_bruto"] - rb["margen_bruto"]
    lbl = mg.etiqueta_periodo(tb._p(per_base))
    mas = "más" if r["litros"] >= rb["litros"] else "menos"
    return _cap(f"En {lbl.lower()} quedaban ${rb['margen_sobre_venta_%']:,.2f}. "
                f"Vendimos {mas} litros que entonces y el margen queda "
                f"{_M(abs(d))} abajo.", 96)


def p4_nota(bd, dfm, per, per_base) -> str:
    per = tb._p(per)
    me = tb.margen_estacion(bd, dfm, per)
    me = me[me["Etiqueta"] != "TOTAL"]
    top = me.iloc[0]
    contrib = ej.contribucion_variacion(dfm, per, per - 1)
    peor = contrib.iloc[0]
    d_grupo = contrib["Δ_margen_$"].sum()

    if top["Etiqueta"] == peor["Estación"]:
        txt = (f"{top['Etiqueta']} concentra el {top['Pct_grupo']:.1f}% del "
               f"margen del grupo y explica el "
               f"{abs(peor['%_de_la_variación']):.0f}% de la variación del mes.")
    else:
        txt = (f"{top['Etiqueta']} concentra el {top['Pct_grupo']:.1f}% del "
               f"margen del grupo; {peor['Estación']} explica el "
               f"{abs(peor['%_de_la_variación']):.0f}% de la variación del mes.")

    # "Sentido contrario" solo si su signo difiere del movimiento del grupo.
    op = contrib[np.sign(contrib["Δ_margen_$"]) == -np.sign(d_grupo)]
    op = op[op["Estación"] != peor["Estación"]]
    if not op.empty:
        m0 = op.iloc[0]
        txt += (f" {m0['Estación']} se mueve en sentido contrario "
                f"({m0['Δ_margen_$']:+,.0f}).")
    return _cap(txt, 220)


# ----------------------------------------------------------------------
# Registro de borradores por ID de bloque
# ----------------------------------------------------------------------
def generar(bd, dfm, per, per_base) -> dict:
    """Devuelve {id_bloque: borrador} para todos los bloques categoría B."""
    lecturas = p1_lecturas(bd, per)
    d = {
        "p1.titular": p1_titular(bd, per),
        "p1.subtitulo": p1_subtitulo(bd, per),
        "p2.titular": p2_titular(bd, per),
        "p2.subtitulo": p2_subtitulo(bd, per),
        "p3.titular": p3_titular(bd, per),
        "p3.subtitulo": p3_subtitulo(bd, per),
        "p4.titular": p4_titular(bd, dfm, per),
        "p4.subtitulo": p4_subtitulo(bd, dfm, per, per_base),
        # p4.nota pasó a manual: ya no se genera borrador (la función p4_nota
        # se conserva por si se quiere volver a activar).
    }
    for i, t in enumerate(lecturas, start=1):
        d[f"p1.lectura.{i}"] = t
    return d
