"""
Configuración central: rutas, nombres de columnas y constantes.

Todo el resto del paquete importa los nombres desde aquí. Si la base
cambia un encabezado, se ajusta en UN solo lugar y no se rompe nada.
"""

from pathlib import Path

# ----------------------------------------------------------------------
# RUTAS
# ----------------------------------------------------------------------
# Raíz del proyecto: "00.Analisis de ventas".
# Este archivo vive en  <raíz>/codigo/treher_analytics/config.py,
# así que la raíz son DOS niveles arriba. Si el paquete se mueve de sitio,
# hay que ajustar este número y nada más.
CARPETA_ANALISIS = Path(__file__).resolve().parents[2]

RUTA_BD = CARPETA_ANALISIS / "BD_Limpia.xlsx"
HOJA_BD = "BD"

# Base de márgenes (cobertura 2025+, 12 estaciones — fuente independiente).
# Ahora vive en BD_Limpia.xlsx, hoja BD_MARGENES (antes: MARGENES..xlsx/Concentrado).
RUTA_MARGENES = CARPETA_ANALISIS / "BD_Limpia.xlsx"
HOJA_MARGENES = "BD_MARGENES"

# Carpeta donde se guardan reportes y figuras exportadas.
CARPETA_SALIDA = CARPETA_ANALISIS / "informes" / "salidas"

# ----------------------------------------------------------------------
# COLUMNAS (tal como vienen en la hoja BD)
# ----------------------------------------------------------------------
COL_ANIO = "Año"
COL_MES = "Mes"
COL_MES_LETRA = "Mes Letra"
COL_ESTACION = "Estación"
COL_FECHA = "Fecha"

# Litros por producto
LTS = {
    "Diésel": "Diésel (Lts)",
    "Premium": "Premium (Lts)",
    "Regular": "Regular (Lts)",
}

# Precios por producto
PRECIO = {
    "Diésel": "Precio D",
    "Premium": "Precio P",
    "Regular": "Precio R",
}

# Importes por producto
IMPORTE = {
    "Diésel": "Importe Diésel",
    "Premium": "Importe Premium",
    "Regular": "Importe Regular",
}

COL_TOTAL_LTS = "Total LTS"
COL_TOTAL_VENTA = "Total venta ($)"

# Listas útiles
PRODUCTOS = list(LTS.keys())  # ["Diésel", "Premium", "Regular"]
COLS_LTS = list(LTS.values())
COLS_PRECIO = list(PRECIO.values())

# Colores consistentes por producto en todas las gráficas
COLOR = {
    "Diésel": "#2C2C2A",
    "Premium": "#A32D2D",
    "Regular": "#185FA5",
    "Total": "#0F6E56",
}

# ----------------------------------------------------------------------
# REGLAS DE NEGOCIO
# ----------------------------------------------------------------------
# Mínimo de días operados para entrar en el MODELO econométrico.
# Se exige ~1 año porque la estacionalidad anual de Fourier no es estimable
# con menos: una estación de pocos meses produce coeficientes sin sentido.
MIN_DIAS_HISTORIA = 365

# ----------------------------------------------------------------------
# OUTLIERS — solo se descarta lo FÍSICAMENTE IMPOSIBLE (error de captura).
# Los picos reales de negocio (quincena, puentes, desabasto del competidor)
# NO se tocan: el modelo y la detección usan estadística robusta para eso.
# ----------------------------------------------------------------------
# Banda de precio plausible ($/lt). La gasolina/diésel en MX ronda 20-30;
# fuera de [10, 60] es casi seguro un error (ej. 290 en vez de 29, o 2.9).
PRECIO_PLAUSIBLE = (10.0, 60.0)

# Un volumen mayor a FACTOR_VOL_OUTLIER veces la mediana de SU PROPIA estación
# se trata como error de dígito. 15× es muy superior a cualquier pico real
# (un puente sube ~2-4×), así que no borra estacionalidad legítima.
FACTOR_VOL_OUTLIER = 15.0

# ----------------------------------------------------------------------
# COMPARABILIDAD ("mismas estaciones")
# ----------------------------------------------------------------------
# Una estación deja de ser comparable solo si tuvo un cierre MATERIAL en
# alguno de los periodos: al menos este número de días cerrados. Un paro
# corto (ej. 12 días de IXTAZACUALA) no debe sacar a toda la estación de la
# base comparable; un cierre largo (COMBULUB, 126 días) o una alta/baja sí.
DIAS_CIERRE_MATERIAL = 30
# Base de la descomposición de margen (cascada): último mes con margen estable
# antes del ciclo de precios. NO usar enero (da efecto volumen negativo y
# contradice la página de ventas).
BASE_CASCADA = "2026-02"
# Además, en ventanas cortas (un mes) se descalifica si el cierre supera esta
# fracción del periodo, aunque no llegue a los 30 días.
FRACCION_CIERRE_MATERIAL = 0.20

# Techo absoluto de litros/día por combustible: ninguna estación vende más.
# El máximo real en 5.5 años de historia es ~54,000 L/día; 80,000 da holgura
# para crecimiento pero atrapa volcados/errores (ej. saldos de apertura).
VOL_MAX_PLAUSIBLE = 80_000.0

# Nombres de días (lunes=0)
DIAS_SEMANA = {
    0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves",
    4: "Viernes", 5: "Sábado", 6: "Domingo",
}
