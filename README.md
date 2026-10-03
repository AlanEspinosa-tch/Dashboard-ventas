# Dashboard de Análisis de Ventas y Reportes Automatizados

Herramienta integral desarrollada para el análisis de ventas de combustible y márgenes en una red de 13 estaciones de servicio. Integra un dashboard interactivo y la generación automatizada de reportes ejecutivos en PDF a partir de datos transaccionales diarios.

## Objetivo del Proyecto
Centralizar el análisis de volumen (litros) y rentabilidad, construyendo una única fuente de verdad (Single Source of Truth) que alimente tableros interactivos, reportes en PDF y libretas de análisis extraordinarios sin duplicar cálculos.

## Diseño Analítico y Reglas de Negocio (Mi contribución principal)
El valor central de este proyecto radica en la estructuración de la lógica de datos y las reglas matemáticas implementadas para asegurar la precisión de los KPIs:
*   **Normalización de Métricas:** Análisis basado estrictamente en promedios de "litros por día" en lugar de totales mensuales, aislando el desempeño real del efecto calendario (meses de 28 vs. 31 días).
*   **Tratamiento de Valores Faltantes:** Implementación de reglas de exclusión para días sin operación. Los promedios jamás se diluyen con "ceros falsos", y las sumas se ponderan con los días reales operados.
*   **Comparabilidad Justa:** Lógica matemática para asegurar que las comparaciones de crecimiento entre periodos utilicen únicamente las estaciones que estuvieron activas en ambos intervalos.
*   **Arquitectura de Datos Centralizada:** Diseño de un módulo central que concentra toda la lógica matemática. Ninguna cifra se calcula dos veces, evitando contradicciones entre el dashboard y los PDFs ejecutivos.

## Implementación Técnica
*Nota de transparencia: La definición de las reglas de negocio, validación matemática y arquitectura general fueron desarrollados por mí. La sintaxis del código en Python, la configuración de la interfaz y la exportación de PDFs fueron implementadas con el apoyo de herramientas de Inteligencia Artificial para acelerar el desarrollo.*

*   **Lenguaje:** Python.
*   **Interfaz Interactiva:** Framework de visualización (Streamlit / despliegue local mediante scripts `.bat`).
*   **Procesamiento:** Consolidación de orígenes de datos (Excel `BD_Limpia`) y estandarización de rutas relativas para portabilidad del proyecto.





# Análisis de Ventas · Grupo Treher

Herramienta de análisis de ventas de combustible de las 13 estaciones del grupo: dashboard interactivo, reporte ejecutivo mensual en PDF y análisis extraordinarios.

### REGLA DE NEGOCIO NO NEGOCIABLE: Todos los promedios se hacen en múltiplos de 7, esto por la estacionalidad semanal descubrida
---

## Para empezar

| Quiero… | Hago esto |
|---|---|
| **Ver el dashboard** | Doble clic en `Abrir_Dashboard.bat` |
| **Generar el reporte del mes** | Dashboard → pestaña 🎯 Ejecutivo → botón "Generar PDF" |
| **Leer un análisis ya hecho** | Carpeta `informes/` |
| **Hacer un análisis nuevo** | Carpeta `analisis/` |
| **Cambiar una ruta o una constante** | `codigo/treher_analytics/config.py` |

> La primera vez, instalar las librerías:
> `pip install -r codigo/requirements.txt`

---

## Qué hay en cada carpeta

```
00.Analisis de ventas/
│
├── README.md                  ← este archivo
├── Abrir_Dashboard.bat        ← lanzador del dashboard
│
├── BD_Limpia.xlsx             ← FUENTE DE DATOS (hojas BD y BD_MARGENES), obviamente no lo subí
├── agrupacion.xlsx            ← catálogo auxiliar de agrupación , tampoco lo subí
├── VENTAS MENSUALES.pbix      ← tablero de Power BI (lee BD_Limpia.xlsx) y este si 
│
├── codigo/                    ← el programa: paquete + dashboard
├── analisis/                  ← notebooks de análisis puntuales
├── informes/                  ← bitácoras y reportes entregables
└── _archivo/                  ← versiones viejas, nada en uso
```

Cada carpeta tiene su propio `README.md` con el detalle.

---

## Los datos

**`BD_Limpia.xlsx` es la única fuente.** Dos hojas:

| Hoja | Contenido |
|---|---|
| `BD` | Ventas diarias por estación y combustible: litros, precio e importe |
| `BD_MARGENES` | Márgenes diarios por estación y combustible |

**Vive en la raíz a propósito**, porque el tablero de Power BI apunta a esta ruta. Si se mueve, hay que reapuntar el `.pbix`.

### Regla que no se rompe

**Un día en que una estación no operó NO es una venta de cero.** Se excluye del cálculo. Los promedios jamás se diluyen con ceros falsos, las sumas siempre se acompañan de los días operados, y las comparaciones entre periodos usan solo estaciones presentes en ambos.

Esta regla está implementada en `codigo/treher_analytics/data.py` y es la base de que las cifras sean confiables.

---

## Cómo está construido

El flujo es siempre el mismo:

```
BD_Limpia.xlsx
      │
      ▼
codigo/treher_analytics/   ← toda la lógica de negocio vive aquí
      │
      ├──► dashboard (Streamlit)        consulta interactiva
      ├──► reporte ejecutivo (PDF)      entregable mensual
      └──► notebooks de analisis/       análisis puntuales
```

**Ninguna cifra se calcula dos veces.** El dashboard, el PDF y los notebooks llaman a las mismas funciones del paquete, así que no pueden contradecirse entre sí.

---

## Mantenimiento mensual

1. Actualizar `BD_Limpia.xlsx` con el mes cerrado (hojas `BD` y `BD_MARGENES`).
2. Abrir el dashboard y revisar la pestaña 🩺 **Cobertura/Cierres**: confirma que no falten días ni estaciones.
3. Ir a 🎯 **Ejecutivo**, escribir los textos del mes y generar el PDF.
4. Guardar el PDF en `informes/`.

---

## Convenciones del proyecto

- **Todo en litros por día**, nunca en totales del mes. Febrero tiene 28 días y marzo 31: comparar totales mezcla el calendario con el negocio.
- **Las rutas son relativas**, calculadas desde la ubicación del propio archivo. El proyecto se puede mover de carpeta o de computadora sin tocar nada.
- **Las constantes viven en un solo lugar**: `codigo/treher_analytics/config.py`.
