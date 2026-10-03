# codigo/

El programa. Aquí vive **toda** la lógica de negocio del proyecto: no hay cálculos sueltos en ningún otro lado.

```
codigo/
├── app.py                  dashboard interactivo (Streamlit)
├── requirements.txt        librerías necesarias
├── comentarios.json        textos del reporte, guardados por mes
├── Logo_ruta.npz           logo vectorizado que usa el PDF
└── treher_analytics/       el paquete
```

---

## El paquete `treher_analytics`

| Módulo | Qué hace |
|---|---|
| **`config.py`** | **Rutas, nombres de columnas y constantes. El único archivo que se edita para cambiar una ruta o un umbral.** |
| `data.py` | Carga y sanea `BD_Limpia.xlsx`. Detecta cierres, descarta errores imposibles y marca quincenas y festivos |
| `calendario.py` | Quincenas y días festivos de México, calculados por reglas para cualquier año |
| `metrics.py` | Métricas de volumen: rankings, mezcla, perfil por día de la semana, comparativas antes/después |
| `margenes.py` | Rentabilidad: lee la hoja `BD_MARGENES` y calcula márgenes unitarios y por estación |
| `ejecutivo.py` | Indicadores de dirección: descomposición del margen, contribución por estación |
| `tablas.py` | Las tablas del reporte ejecutivo, con el panel comparable y la reconciliación |
| `model.py` | Modelo precio-volumen y pronósticos |
| `borradores.py` | Redacta automáticamente los textos del reporte que luego dirección edita |
| `comentarios.py` | Catálogo de los textos del reporte y su guardado por periodo |
| `reporte_pdf.py` | Arma el PDF ejecutivo de 6 páginas |
| `viz.py` | Gráficas reutilizables |

---

## El dashboard

```bash
streamlit run app.py
```
O, más fácil, el `Abrir_Dashboard.bat` de la raíz.

Ocho pestañas: 🎯 Ejecutivo · 📊 Grupo · 🏪 Estación · 💰 Márgenes · 📈 Modelo precio-volumen · 🔮 Pronóstico robusto · 🤖 Pronóstico SARIMAX · 🩺 Cobertura/Cierres.

---

## Usarlo desde un notebook

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd().parent / "codigo"))

from treher_analytics import data, margenes as mg, tablas as tb

bd  = data.cargar_bd()        # carga y sanea la hoja BD
dfm = mg.cargar_margenes()    # carga la hoja BD_MARGENES
```

Los notebooks de `analisis/` ya traen esa línea.

---

## Los textos del reporte

`comentarios.json` guarda, mes por mes, lo que dirección escribe en el PDF. Tres categorías:

| | Comportamiento |
|---|---|
| 🟦 **Borrador** | Python propone un texto con los datos del mes; dirección lo edita o lo deja |
| 🟧 **Manual** | Llega vacío. **Si se deja vacío, ese bloque no aparece en el PDF** y lo de abajo sube |
| Automático | Lo calcula el PDF; no aparece en el formulario |

El texto respeta los saltos de línea y convierte `-` en viñetas.

---

## Reglas al tocar este código

1. **Las rutas nunca se escriben completas.** Se derivan de `config.py`, que se ubica a sí mismo. Una ruta tipo `C:\Users\...` rompe el proyecto para cualquier otra computadora.
2. **`config.py` está dos niveles debajo de la raíz.** Si el paquete cambia de lugar, hay que ajustar `parents[2]`.
3. **Un cierre no es una venta de cero.** Al agregar cualquier cálculo, excluir los días no operados.
4. **Litros por día, no totales mensuales.**
