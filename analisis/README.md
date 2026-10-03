# analisis/

Notebooks de análisis puntuales: preguntas concretas que no forman parte del reporte mensual.

El reporte recurrente vive en `codigo/`; aquí van las investigaciones de una sola vez.

---

## Qué hay

| Notebook | Pregunta que responde |
|---|---|
| **`Analisis_15_16_septiembre.ipynb`** | ¿Las ventas del 15 y 16 de septiembre son anómalas? Compara cada año contra sus propios 12 mismos días de la semana previos. Filtrable por estación |
| **`Competencia_AVE_FENIX_Premium.ipynb`** | ¿Cómo responde el volumen de AVE FÉNIX al precio propio y al de la competencia? Separa el efecto del nivel de precios de la zona del de la posición competitiva |
| `Precios_competencia.ipynb` | Limpieza y preparación de los precios de la competencia |
| `Margenes.ipynb` | Exploración original de márgenes, anterior al paquete |
| `Modelo_precio__vs_litros.ipynb` | Notebook original del modelo precio-volumen. Su contenido ya vive en `treher_analytics/model.py` |

---

## Cómo se usan

Los notebooks importan el paquete desde la carpeta vecina:

```python
sys.path.insert(0, str(Path.cwd().parent / "codigo"))
from treher_analytics import data, config as cfg
```

**Hay que abrirlos desde esta carpeta** para que esa ruta funcione.

---

## Convenciones

- **Solo resultados, sin conclusiones.** Los notebooks muestran tablas y números; la interpretación va en `informes/`. Así el cálculo y el juicio quedan separados y se pueden revisar por separado.
- **Parámetros arriba.** Fechas, estaciones y métrica se controlan desde la primera celda, sin tocar el resto.
- **Nada de cálculos propios de negocio.** Si un notebook necesita una métrica que ya existe, la importa del paquete. Si la métrica es nueva y se va a reutilizar, su lugar es `treher_analytics/`.
