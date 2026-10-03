"""
Modelo de sensibilidad precio-volumen: regresión log-log + estacionalidad
de Fourier, con diagnósticos y un score de confiabilidad (semáforo).

Mejoras respecto al notebook original:
  - La estacionalidad anual usa el DÍA CALENDARIO (día del año), no un
    contador secuencial 't'. Con cierres y huecos, 't/365' desfasaba la
    fase estacional; 'dia_año/365.25' la mantiene anclada al calendario.
  - Solo modela días realmente operados (litros y precio > 0, no NaN).
  - Guarda de historia mínima: estaciones de vida corta se omiten en vez
    de producir coeficientes basura.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import jarque_bera
from statsmodels.stats.diagnostic import acorr_breusch_godfrey, het_breuschpagan
from statsmodels.stats.stattools import durbin_watson

from . import calendario
from . import config as cfg

K_FOURIER = 4  # número de armónicos anuales


# ----------------------------------------------------------------------
# DIAGNÓSTICOS
# ----------------------------------------------------------------------
def _tests_residuos(modelo) -> dict:
    res = modelo.resid
    exog = modelo.model.exog
    _, bg_p, _, _ = acorr_breusch_godfrey(modelo, nlags=7)
    _, bp_p, _, _ = het_breuschpagan(res, exog)
    _, jb_p = jarque_bera(res)
    return {
        "DW": float(durbin_watson(res)),
        "bg_p": float(bg_p),
        "bp_p": float(bp_p),
        "jb_p": float(jb_p),
    }


def _tests_operativos(y, y_hat, periodo_estacional: int = 7) -> dict:
    """
    Compara el modelo contra benchmarks ingenuos: la MEDIA y el NAIVE ESTACIONAL
    ("este día = el mismo día de la semana pasada", shift de 7). Es una vara más
    exigente que la persistencia simple, porque ya trae el patrón semanal.
    """
    y = pd.Series(y).reset_index(drop=True)
    y_hat = pd.Series(y_hat).reset_index(drop=True)
    naive = y.shift(periodo_estacional)              # mismo día, semana anterior
    mask = naive.notna()                             # se ignoran los primeros 7
    rmse_modelo = np.sqrt(np.mean((y[mask] - y_hat[mask]) ** 2))
    rmse_naive = np.sqrt(np.mean((y[mask] - naive[mask]) ** 2))
    rmse_media = np.sqrt(np.mean((y[mask] - y[mask].mean()) ** 2))
    denom = rmse_naive if rmse_naive else 1e-9
    return {
        "rmse_ok": (rmse_modelo < rmse_naive) and (rmse_modelo < rmse_media),
        "mejora_vs_naive_pct": (1 - rmse_modelo / denom) * 100,
        "placebo_ok": rmse_modelo < rmse_media,
    }


def _score(t_fourier_p, t_res, t_op, lambda_signif) -> int:
    """Score 0-100 de confiabilidad. Misma lógica que el notebook, compacta."""
    s = 0
    if t_fourier_p < 0.05:
        s += 25
    if 1.5 < t_res["DW"] < 2.5:
        s += 8
    if t_res["bg_p"] > 0.05:
        s += 10
    if t_res["bp_p"] > 0.05:
        s += 8
    if t_res["jb_p"] > 0.05:
        s += 6
    if lambda_signif:
        s += 13
    if t_op["rmse_ok"]:
        s += 20
    if t_op["placebo_ok"] and t_op["mejora_vs_naive_pct"] > 5:
        s += 10
    return min(s, 100)


def semaforo(score: int) -> str:
    if score >= 80:
        return "🟢"
    if score >= 60:
        return "🟡"
    if score >= 40:
        return "🟠"
    return "🔴"


# ----------------------------------------------------------------------
# MODELO POR ESTACIÓN
# ----------------------------------------------------------------------
def _diseno_modelo(df: pd.DataFrame, col_lts: str, col_precio: str):
    """
    Construye la matriz de diseño del modelo precio-volumen para un producto:
    ln(litros) ~ ln(precio) + tendencia + quincena + festivo + día de semana +
    Fourier anual. Devuelve (X, y, fourier_cols, n_obs). Si no hay historia
    suficiente, X/y/fourier_cols son None (pero n_obs se reporta).
    """
    temp = df[[col_lts, col_precio, "Dia_semana", "Dia_año",
               "Quincena", "Festivo"]].dropna()
    temp = temp[(temp[col_lts] > 0) & (temp[col_precio] > 0)]
    if len(temp) < cfg.MIN_DIAS_HISTORIA:
        return None, None, None, len(temp)

    temp = temp.copy()
    temp["ln_lts"] = np.log(temp[col_lts])
    temp["ln_precio"] = np.log(temp[col_precio])
    temp["t_c"] = np.arange(len(temp)) - len(temp) / 2          # tendencia centrada
    for k in range(1, K_FOURIER + 1):                            # estacionalidad anual
        ang = 2 * np.pi * k * temp["Dia_año"] / 365.25
        temp[f"sin_{k}"] = np.sin(ang)
        temp[f"cos_{k}"] = np.cos(ang)
    fourier_cols = [c for c in temp.columns if c.startswith(("sin_", "cos_"))]

    dummies = pd.get_dummies(temp["Dia_semana"], prefix="D", drop_first=True).astype(int)
    cal = temp[["Quincena", "Festivo"]].astype(int)
    X = pd.concat([temp[["ln_precio", "t_c"]], cal, dummies, temp[fourier_cols]], axis=1)
    X = sm.add_constant(X.astype(float))
    y = temp["ln_lts"].astype(float)
    return X, y, fourier_cols, len(temp)


def residuos_modelo(bd: pd.DataFrame, estacion: str) -> dict:
    """
    Devuelve, por producto, los residuos y valores ajustados del modelo
    (mismo diseño que `modelo_precio_volumen`) para graficar diagnósticos.
    """
    df = bd[bd[cfg.COL_ESTACION] == estacion].sort_values(cfg.COL_FECHA)
    out = {}
    for prod in cfg.PRODUCTOS:
        X, y, _, _ = _diseno_modelo(df, cfg.LTS[prod], cfg.PRECIO[prod])
        if X is None:
            continue
        m = sm.OLS(y, X).fit()
        out[prod] = {
            "resid": pd.Series(m.resid).reset_index(drop=True),
            "fitted": pd.Series(m.fittedvalues).reset_index(drop=True),
        }
    return out


def modelo_precio_volumen(bd: pd.DataFrame, estacion: str) -> pd.DataFrame:
    """
    Ajusta, por producto, ln(litros) ~ ln(precio) + tendencia + día_semana
    + Fourier anual. Devuelve elasticidad, tendencia, estacionalidad y un
    semáforo de confiabilidad.
    """
    df = (
        bd[bd[cfg.COL_ESTACION] == estacion]
        .sort_values(cfg.COL_FECHA)
        .copy()
    )
    if df.empty:
        raise ValueError(f"No hay datos para la estación {estacion!r}")

    resultados = {}
    for prod in cfg.PRODUCTOS:
        col_lts, col_precio = cfg.LTS[prod], cfg.PRECIO[prod]
        X, y, fourier_cols, n_obs = _diseno_modelo(df, col_lts, col_precio)

        # Guarda de historia mínima.
        if X is None:
            resultados[prod] = {
                "Semáforo": "⚪", "Score": np.nan,
                "Elasticidad_precio": np.nan, "p_value_precio": np.nan,
                "Crec_anual_%": np.nan, "R²": np.nan,
                "N_obs": n_obs, "Nota": "Historia insuficiente",
            }
            continue

        ols = sm.OLS(y, X).fit()
        t_res = _tests_residuos(ols)

        # Errores robustos según diagnóstico (autocorrelación / heterocedasticidad).
        if t_res["bg_p"] < 0.05:
            modelo = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 7})
        elif t_res["bp_p"] < 0.05:
            modelo = sm.OLS(y, X).fit(cov_type="HC3")
        else:
            modelo = ols

        # Test conjunto "todos los términos de Fourier = 0". Cada restricción
        # se separa con coma (NO con ' = ', que encadenaría igualdades y daría
        # una hipótesis de rango deficiente).
        f_test = modelo.f_test(", ".join(f"{c} = 0" for c in fourier_cols))
        t_res = _tests_residuos(modelo)
        t_op = _tests_operativos(y, modelo.fittedvalues)
        lambda_t = modelo.params["t_c"]
        lambda_signif = modelo.pvalues["t_c"] < 0.05

        # (B) Elasticidad ROBUSTA con RLM-Huber: pesa menos los días atípicos
        # sin borrarlos. Si difiere mucho de la OLS, hay outliers influyentes.
        rlm = sm.RLM(y, X, M=sm.robust.norms.HuberT()).fit()
        elast_ols = modelo.params["ln_precio"]
        elast_rob = rlm.params["ln_precio"]
        divergencia = abs(elast_ols - elast_rob)
        sensible = divergencia > 0.3 * abs(elast_ols) if elast_ols else False

        score = _score(float(f_test.pvalue), t_res, t_op, lambda_signif)

        resultados[prod] = {
            "Semáforo": semaforo(score),
            "Score": score,
            "Elasticidad_precio": round(elast_ols, 3),
            "Elasticidad_robusta": round(elast_rob, 3),
            "Sensible_a_outliers": "⚠️ sí" if sensible else "no",
            "p_value_precio": round(modelo.pvalues["ln_precio"], 4),
            "Crec_anual_%": round(365 * lambda_t * 100, 2),
            "Efecto_quincena_%": round((np.exp(modelo.params["Quincena"]) - 1) * 100, 1),
            "Efecto_festivo_%": round((np.exp(modelo.params["Festivo"]) - 1) * 100, 1),
            "R²": round(modelo.rsquared, 3),
            "DW": round(t_res["DW"], 2),
            "BG_p (autocorr.)": round(t_res["bg_p"], 4),
            "BP_p (heteroced.)": round(t_res["bp_p"], 4),
            "JB_p (normalidad)": round(t_res["jb_p"], 4),
            "p_fourier": round(float(f_test.pvalue), 4),
            "Mejora_vs_naive_%": round(t_op["mejora_vs_naive_pct"], 1),
            "N_obs": n_obs,
            "Nota": "",
        }

    return pd.DataFrame(resultados).T.rename_axis("Producto")


# ----------------------------------------------------------------------
# PRONÓSTICO
# ----------------------------------------------------------------------
def _features(frame: pd.DataFrame) -> pd.DataFrame:
    """Matriz de diseño a partir de un frame con las columnas base."""
    X = pd.DataFrame(index=frame.index)
    X["ln_precio"] = np.log(frame["precio"].astype(float))
    X["t_c"] = frame["t_c"].astype(float)
    X["Quincena"] = frame["Quincena"].astype(int)
    X["Festivo"] = frame["Festivo"].astype(int)
    for k in range(1, K_FOURIER + 1):
        ang = 2 * np.pi * k * frame["Dia_año"] / 365.25
        X[f"sin_{k}"] = np.sin(ang)
        X[f"cos_{k}"] = np.cos(ang)
    dummies = pd.get_dummies(
        pd.Categorical(frame["Dia_semana"], categories=range(7)),
        prefix="D", drop_first=True,
    ).astype(int)
    dummies.index = frame.index
    return pd.concat([X, dummies], axis=1)


def _banda_empirica(resid):
    """Cuantiles 2.5 / 50 / 97.5 de los residuos (en log) para la banda."""
    return np.percentile(np.asarray(resid), [2.5, 50, 97.5])


def pronostico(bd: pd.DataFrame, estacion: str, producto: str = "Diésel",
               dias: int = 30, precio: float | None = None) -> pd.DataFrame:
    """
    Pronostica litros diarios futuros para una estación-producto.

    Ajuste ROBUSTO (RLM-Huber): los días extremos pesan menos, así no inflan
    el nivel esperado de los días altos. La banda 95% es EMPÍRICA (cuantiles
    de los residuos) → asimétrica y robusta a colas pesadas; no supone
    normalidad ni usa smearing. El precio futuro se mantiene en el último
    observado salvo que se indique `precio` (escenarios de pricing).

    Devuelve: Fecha, Tipo (Histórico/Pronóstico), Litros, Esperado, LI, LS.
    """
    col_lts, col_precio = cfg.LTS[producto], cfg.PRECIO[producto]
    df = bd[bd[cfg.COL_ESTACION] == estacion].sort_values(cfg.COL_FECHA).copy()
    h = df[[cfg.COL_FECHA, col_lts, col_precio, "Dia_semana", "Dia_año",
            "Quincena", "Festivo"]].dropna()
    h = h[(h[col_lts] > 0) & (h[col_precio] > 0)].reset_index(drop=True)

    if len(h) < cfg.MIN_DIAS_HISTORIA:
        raise ValueError(f"{estacion}/{producto}: historia insuficiente para pronosticar.")

    n = len(h)
    h["t_c"] = np.arange(n) - n / 2
    h["precio"] = h[col_precio]
    X = sm.add_constant(_features(h).astype(float))
    y = np.log(h[col_lts].astype(float))
    modelo = sm.RLM(y, X, M=sm.robust.norms.HuberT()).fit()

    # Banda 95% empírica a partir de los residuos robustos (en log).
    q_lo, q_md, q_hi = _banda_empirica(modelo.resid)

    # --- Fechas futuras y su calendario ---
    ult_fecha = h[cfg.COL_FECHA].max()
    fechas_fut = pd.date_range(ult_fecha + pd.Timedelta(days=1), periods=dias, freq="D")
    cal = calendario.marcar(pd.Series(fechas_fut))
    precio_fut = float(precio) if precio else float(h[col_precio].iloc[-1])

    fut = pd.DataFrame({
        cfg.COL_FECHA: fechas_fut,
        "Dia_semana": fechas_fut.weekday,
        "Dia_año": fechas_fut.dayofyear,
        "Quincena": cal["Quincena"].values,
        "Festivo": cal["Festivo"].values,
        "t_c": np.arange(n, n + dias) - n / 2,
        "precio": precio_fut,
    })
    Xf = sm.add_constant(_features(fut).astype(float), has_constant="add")
    Xf = Xf.reindex(columns=X.columns, fill_value=0)

    # Predicción puntual (log) + banda empírica asimétrica.
    yhat_fut = np.asarray(modelo.predict(Xf))
    fc = pd.DataFrame({
        cfg.COL_FECHA: fechas_fut,
        "Tipo": "Pronóstico",
        "Litros": np.exp(yhat_fut + q_md),
        "Esperado": np.exp(yhat_fut + q_md),
        "LI": np.exp(yhat_fut + q_lo),
        "LS": np.exp(yhat_fut + q_hi),
    })

    # Banda histórica (in-sample) con los mismos cuantiles, para vigilar si los
    # días recientes se comportaron como se espera.
    yhat_in = np.asarray(modelo.fittedvalues)
    hist = pd.DataFrame({
        cfg.COL_FECHA: h[cfg.COL_FECHA].values,
        "Tipo": "Histórico",
        "Litros": h[col_lts].values,                       # real
        "Esperado": np.exp(yhat_in + q_md),
        "LI": np.exp(yhat_in + q_lo),
        "LS": np.exp(yhat_in + q_hi),
    })
    return pd.concat([hist, fc], ignore_index=True)


# ----------------------------------------------------------------------
# PRONÓSTICO SARIMAX (regresión con errores ARIMA)
# ----------------------------------------------------------------------
def pronostico_sarimax(bd: pd.DataFrame, estacion: str, producto: str = "Diésel",
                       dias: int = 30, precio: float | None = None,
                       order: tuple = (1, 0, 1)) -> pd.DataFrame:
    """
    Igual de interpretable que el OLS (conserva precio, tendencia, día de
    semana, Fourier, quincena y festivos como regresores exógenos) pero
    además modela la AUTOCORRELACIÓN de los residuos con un proceso ARMA.
    Eso da mejor precisión de corto plazo y bandas más honestas.

    Devuelve el mismo formato que `pronostico` (Fecha, Tipo, Litros, LI, LS).
    En df.attrs['resumen'] guarda elasticidad, efectos y AIC (interpretabilidad).
    """
    col_lts, col_precio = cfg.LTS[producto], cfg.PRECIO[producto]
    df = (bd[bd[cfg.COL_ESTACION] == estacion]
          .sort_values(cfg.COL_FECHA).set_index(cfg.COL_FECHA))

    # Rejilla diaria continua (SARIMAX necesita frecuencia regular).
    idx = pd.date_range(df.index.min(), df.index.max(), freq="D")
    lts = df[col_lts].reindex(idx)
    precio_hist = df[col_precio].reindex(idx).ffill().bfill()

    if lts.notna().sum() < cfg.MIN_DIAS_HISTORIA:
        raise ValueError(f"{estacion}/{producto}: historia insuficiente para pronosticar.")

    n = len(idx)
    y = np.log(lts.where(lts > 0))          # NaN en días cerrados (Kalman los maneja)
    y.index.freq = "D"

    def _exog(fechas, precio_vals, t_idx):
        f = pd.DataFrame({
            cfg.COL_FECHA: fechas,
            "Dia_semana": pd.DatetimeIndex(fechas).weekday,
            "Dia_año": pd.DatetimeIndex(fechas).dayofyear,
            # Tendencia escalada (÷ n) para estabilidad numérica de la MLE.
            "t_c": (np.asarray(t_idx, float) - n / 2) / n,
            "precio": precio_vals,
        })
        cal = calendario.marcar(pd.Series(pd.DatetimeIndex(fechas)))
        f["Quincena"] = cal["Quincena"].values
        f["Festivo"] = cal["Festivo"].values
        X = _features(f)
        X.index = pd.DatetimeIndex(fechas)
        return X

    Xh = _exog(idx, precio_hist.values, np.arange(n))

    modelo = sm.tsa.SARIMAX(
        y, exog=Xh, order=order,
        enforce_stationarity=True, enforce_invertibility=True,
    ).fit(disp=False, maxiter=300, method="lbfgs")

    # Smearing sobre residuos en escala log (días observados).
    pred_in = modelo.get_prediction()
    ins = pred_in.predicted_mean
    resid_log = (y - ins).dropna()
    smear = float(np.mean(np.exp(resid_log)))
    ci_in = pred_in.conf_int(alpha=0.05)

    # --- Futuro ---
    fechas_fut = pd.date_range(idx.max() + pd.Timedelta(days=1), periods=dias, freq="D")
    precio_fut = float(precio) if precio else float(precio_hist.iloc[-1])
    Xf = _exog(fechas_fut, np.full(dias, precio_fut), np.arange(n, n + dias))

    fcast = modelo.get_forecast(steps=dias, exog=Xf)
    media = fcast.predicted_mean.values
    ci = fcast.conf_int(alpha=0.05).values

    fc = pd.DataFrame({
        cfg.COL_FECHA: fechas_fut, "Tipo": "Pronóstico",
        "Litros": np.exp(media) * smear,
        "Esperado": np.exp(media) * smear,
        "LI": np.exp(ci[:, 0]) * smear,
        "LS": np.exp(ci[:, 1]) * smear,
    })
    op = lts.dropna()
    op = op[op > 0]
    # Banda histórica (in-sample) para vigilancia de los días recientes.
    esp = np.exp(ins.reindex(op.index)) * smear
    li_in = np.exp(ci_in.iloc[:, 0].reindex(op.index)) * smear
    ls_in = np.exp(ci_in.iloc[:, 1].reindex(op.index)) * smear
    hist = pd.DataFrame({
        cfg.COL_FECHA: op.index, "Tipo": "Histórico",
        "Litros": op.values, "Esperado": esp.values,
        "LI": li_in.values, "LS": ls_in.values,
    })
    salida = pd.concat([hist, fc], ignore_index=True)
    # OJO: los coeficientes exógenos del SARIMAX NO se interpretan como
    # elasticidad (el ARMA absorbe la persistencia y distorsiona el signo).
    # La interpretación económica vive en el modelo OLS. Aquí solo ajuste.
    salida.attrs["resumen"] = {
        "AIC": round(float(modelo.aic), 1),
        "Orden_ARMA": str(order),
        "Días_historia": int(y.notna().sum()),
    }
    return salida


# ----------------------------------------------------------------------
# PROYECCIÓN DEL MES SIGUIENTE
# ----------------------------------------------------------------------
def proyeccion_mes_siguiente(bd: pd.DataFrame, estacion: str, producto: str = "Diésel",
                             motor: str = "sarimax", precio: float | None = None) -> pd.DataFrame:
    """
    Proyecta el total de litros del PRÓXIMO mes calendario completo, sumando
    el pronóstico diario, y lo compara contra el mismo mes del año anterior
    (YoY, dato real). `motor`: 'sarimax' (default) u 'ols'.
    """
    ult = bd[bd[cfg.COL_ESTACION] == estacion][cfg.COL_FECHA].max()
    mes_sig = ult.to_period("M") + 1
    fin_mes_sig = mes_sig.to_timestamp(how="end").normalize()
    dias = (fin_mes_sig - ult).days

    fn = pronostico_sarimax if motor == "sarimax" else pronostico
    fc = fn(bd, estacion, producto, dias=dias, precio=precio)
    fut = fc[fc["Tipo"] == "Pronóstico"].copy()
    en_mes = fut[fut[cfg.COL_FECHA].dt.to_period("M") == mes_sig]

    # YoY: mismo mes del año pasado (dato real operado)
    g = bd[bd[cfg.COL_ESTACION] == estacion]
    prev = g[(g[cfg.COL_FECHA].dt.to_period("M") == (mes_sig - 12)) & g["Operó"]]
    lts_yoy = prev[cfg.LTS[producto]].sum(min_count=1)
    total = en_mes["Litros"].sum()

    return pd.DataFrame([{
        "Mes_proyectado": str(mes_sig),
        "Producto": producto,
        "Motor": motor.upper(),
        "Litros_proyectados": total,
        "Banda_inferior": en_mes["LI"].sum(),
        "Banda_superior": en_mes["LS"].sum(),
        "Mismo_mes_año_pasado": lts_yoy,
        "Var_YoY_%": 100 * (total / lts_yoy - 1) if lts_yoy and not np.isnan(lts_yoy) else np.nan,
    }])


# ----------------------------------------------------------------------
# BACKTEST: ¿quién pronostica mejor, OLS o SARIMAX?
# ----------------------------------------------------------------------
def backtest(bd: pd.DataFrame, estacion: str, producto: str = "Diésel",
             h: int = 30) -> pd.DataFrame:
    """
    Reserva los últimos `h` días, entrena ambos motores con el resto y
    compara su error contra lo que realmente pasó (RMSE y MAPE).
    Justifica objetivamente cuál usar.
    """
    g = bd[bd[cfg.COL_ESTACION] == estacion]
    corte = g[cfg.COL_FECHA].max() - pd.Timedelta(days=h)
    bd_train = bd[bd[cfg.COL_FECHA] <= corte]

    real = (g[(g[cfg.COL_FECHA] > corte) & g["Operó"]]
            [[cfg.COL_FECHA, cfg.LTS[producto]]].dropna()
            .rename(columns={cfg.LTS[producto]: "real"}))
    if real.empty:
        raise ValueError("Sin datos reales en el periodo de prueba.")

    filas = []
    for nombre, fn in [("OLS", pronostico), ("SARIMAX", pronostico_sarimax)]:
        try:
            fc = fn(bd_train, estacion, producto, dias=h + 5)
            pred = fc[fc["Tipo"] == "Pronóstico"][[cfg.COL_FECHA, "Litros"]]
            m = real.merge(pred, on=cfg.COL_FECHA, how="inner")
            err = m["Litros"] - m["real"]
            rmse = float(np.sqrt((err ** 2).mean()))
            mape = float((err.abs() / m["real"]).mean() * 100)
            filas.append({"Modelo": nombre, "RMSE": rmse, "MAPE_%": mape,
                          "Días_evaluados": len(m)})
        except Exception as e:
            filas.append({"Modelo": nombre, "RMSE": np.nan, "MAPE_%": np.nan,
                          "Días_evaluados": 0, "Nota": str(e)[:40]})
    return pd.DataFrame(filas)


# ----------------------------------------------------------------------
# VIGILANCIA OUT-OF-SAMPLE: el modelo NO ve los días que evalúa
# ----------------------------------------------------------------------
def vigilancia_oos(bd: pd.DataFrame, estacion: str, producto: str = "Diésel",
                   dias: int = 14) -> pd.DataFrame:
    """
    Banda de vigilancia VERDADERAMENTE fuera de muestra: se entrena el modelo
    EXCLUYENDO los últimos `dias` días y se predicen esos días con su banda 95%.
    Así una anomalía reciente no puede "jalar" el ajuste hacia sí misma y
    enmascararse — la alerta es honesta en condiciones operativas.

    (Mejora sobre la versión in-sample: ataca el enmascaramiento, no solo la
    leve subestimación de la banda.)
    """
    df = bd[bd[cfg.COL_ESTACION] == estacion].sort_values(cfg.COL_FECHA)
    X, y, _, n = _diseno_modelo(df, cfg.LTS[producto], cfg.PRECIO[producto])
    if X is None or n - dias < cfg.MIN_DIAS_HISTORIA:
        raise ValueError(f"{estacion}/{producto}: historia insuficiente para vigilancia OOS.")

    X_tr, y_tr = X.iloc[:-dias], y.iloc[:-dias]   # entrenamiento SIN los últimos días
    X_te, y_te = X.iloc[-dias:], y.iloc[-dias:]   # días a vigilar (no vistos)

    m = sm.RLM(y_tr, X_tr, M=sm.robust.norms.HuberT()).fit()
    q_lo, q_md, q_hi = _banda_empirica(m.resid)
    yhat_te = np.asarray(m.predict(X_te))

    fechas = df.loc[X_te.index, cfg.COL_FECHA].values
    real = np.exp(y_te.values)
    esp = np.exp(yhat_te + q_md)
    li = np.exp(yhat_te + q_lo)
    ls = np.exp(yhat_te + q_hi)
    fuera = (real < li) | (real > ls)

    out = pd.DataFrame({
        cfg.COL_FECHA: fechas, "Real": real, "Esperado": esp,
        "LI": li, "LS": ls,
    })
    out["Desv_%"] = ((out["Real"] / out["Esperado"] - 1) * 100).round(1)
    out["Estado"] = np.where(fuera, "🔴 fuera", "✅ dentro")
    return out


# ----------------------------------------------------------------------
# BACKTEST ROLLING (walk-forward): varias ventanas, no un solo corte
# ----------------------------------------------------------------------
def backtest_rolling(bd: pd.DataFrame, estacion: str, producto: str = "Diésel",
                     h: int = 14, n_folds: int = 4, paso: int = 14,
                     motores=("Robusto", "SARIMAX")) -> pd.DataFrame:
    """
    Validación temporal en múltiples ventanas deslizantes (rolling origin):
    para cada fold se entrena hasta el origen y se pronostican `h` días fuera de
    muestra. Devuelve, por motor, media y desviación de RMSE/MAPE y la
    COBERTURA del intervalo 95% (¿qué % de días reales cayó dentro de la banda?
    — debería rondar 95% si la banda es honesta).
    """
    col_lts = cfg.LTS[producto]
    g = bd[bd[cfg.COL_ESTACION] == estacion]
    max_fecha = g[g["Operó"]][cfg.COL_FECHA].max()
    fns = {"Robusto": pronostico, "SARIMAX": pronostico_sarimax}

    filas = []
    for nombre in motores:
        fn = fns[nombre]
        rmse_l, mape_l, cov_l = [], [], []
        for k in range(n_folds):
            fin_test = max_fecha - pd.Timedelta(days=k * paso)
            ini_test = fin_test - pd.Timedelta(days=h - 1)
            bd_train = bd[bd[cfg.COL_FECHA] < ini_test]
            train_st = bd_train[(bd_train[cfg.COL_ESTACION] == estacion) & bd_train["Operó"]]
            if train_st.empty:
                continue
            try:
                dias_fc = (fin_test - train_st[cfg.COL_FECHA].max()).days + 1
                if dias_fc < 1:
                    continue
                fc = fn(bd_train, estacion, producto, dias=dias_fc)
                pred = fc[fc["Tipo"] == "Pronóstico"][[cfg.COL_FECHA, "Litros", "LI", "LS"]]
                real = (g[(g[cfg.COL_FECHA] >= ini_test) & (g[cfg.COL_FECHA] <= fin_test)
                          & g["Operó"]][[cfg.COL_FECHA, col_lts]].dropna()
                        .rename(columns={col_lts: "real"}))
                mm = real.merge(pred, on=cfg.COL_FECHA, how="inner")
                if mm.empty:
                    continue
                err = mm["Litros"] - mm["real"]
                rmse_l.append(float(np.sqrt((err ** 2).mean())))
                mape_l.append(float((err.abs() / mm["real"]).mean() * 100))
                cov_l.append(float(((mm["real"] >= mm["LI"]) &
                                    (mm["real"] <= mm["LS"])).mean() * 100))
            except Exception:
                continue
        if rmse_l:
            filas.append({
                "Modelo": nombre,
                "RMSE_medio": np.mean(rmse_l), "RMSE_std": np.std(rmse_l),
                "MAPE_%_medio": np.mean(mape_l), "MAPE_%_std": np.std(mape_l),
                "Cobertura_95_%": np.mean(cov_l), "Folds": len(rmse_l),
            })
        else:
            filas.append({"Modelo": nombre, "RMSE_medio": np.nan, "RMSE_std": np.nan,
                          "MAPE_%_medio": np.nan, "MAPE_%_std": np.nan,
                          "Cobertura_95_%": np.nan, "Folds": 0})
    return pd.DataFrame(filas)
