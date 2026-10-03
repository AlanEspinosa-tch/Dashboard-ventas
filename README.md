# Análisis de Ventas · Grupo Treher

Herramienta de análisis de ventas de combustible de las 13 estaciones del grupo: dashboard interactivo, reporte ejecutivo mensual en PDF y análisis extraordinarios.

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
├── BD_Limpia.xlsx             ← FUENTE DE DATOS (hojas BD y BD_MARGENES)
├── agrupacion.xlsx            ← catálogo auxiliar de agrupación
├── VENTAS MENSUALES.pbix      ← tablero de Power BI (lee BD_Limpia.xlsx)
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
