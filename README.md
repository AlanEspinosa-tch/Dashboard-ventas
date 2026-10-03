# Dashboard de Análisis de Ventas y Reportes Automatizados

Herramienta integral desarrollada para el análisis de ventas de combustible y márgenes en una red de 13 estaciones de servicio. Integra un dashboard interactivo y la generación automatizada de reportes ejecutivos en PDF a partir de datos transaccionales diarios.

## 🎯 Objetivo del Proyecto
Centralizar el análisis de volumen (litros) y rentabilidad, construyendo una única fuente de verdad (Single Source of Truth) que alimente tableros interactivos, reportes en PDF y libretas de análisis extraordinarios sin duplicar cálculos.

## 🧠 Diseño Analítico y Reglas de Negocio (Mi contribución principal)
El valor central de este proyecto radica en la estructuración de la lógica de datos y las reglas matemáticas implementadas para asegurar la precisión de los KPIs:
*   **Normalización de Métricas:** Análisis basado estrictamente en promedios de "litros por día" en lugar de totales mensuales, aislando el desempeño real del efecto calendario (meses de 28 vs. 31 días).
*   **Tratamiento de Valores Faltantes:** Implementación de reglas de exclusión para días sin operación. Los promedios jamás se diluyen con "ceros falsos", y las sumas se ponderan con los días reales operados.
*   **Comparabilidad Justa:** Lógica matemática para asegurar que las comparaciones de crecimiento entre periodos utilicen únicamente las estaciones que estuvieron activas en ambos intervalos.
*   **Arquitectura de Datos Centralizada:** Diseño de un módulo central que concentra toda la lógica matemática. Ninguna cifra se calcula dos veces, evitando contradicciones entre el dashboard y los PDFs ejecutivos.

## 💻 Implementación Técnica
*Nota de transparencia: La definición de las reglas de negocio, validación matemática y arquitectura general fueron desarrollados por mí. La sintaxis del código en Python, la configuración de la interfaz y la exportación de PDFs fueron implementadas con el apoyo de herramientas de Inteligencia Artificial para acelerar el desarrollo.*

*   **Lenguaje:** Python.
*   **Interfaz Interactiva:** Framework de visualización (Streamlit / despliegue local mediante scripts `.bat`).
*   **Procesamiento:** Consolidación de orígenes de datos (Excel `BD_Limpia`) y estandarización de rutas relativas para portabilidad del proyecto.
