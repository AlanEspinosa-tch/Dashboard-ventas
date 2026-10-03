@echo off
chcp 65001 >nul
title Dashboard Treher - NO CERRAR mientras lo uses

echo ============================================================
echo   DASHBOARD DE VENTAS - GRUPO TREHER
echo ------------------------------------------------------------
echo   Espera unos segundos: el navegador se abrira solo.
echo   Para CERRAR el dashboard: cierra esta ventana.
echo ============================================================
echo.

rem Este .bat vive en la raiz del proyecto; el codigo esta en "codigo\"
cd /d "%~dp0codigo"

rem Lanzar Streamlit con el Python instalado
python -m streamlit run app.py

rem Si algo falla, la ventana no se cierra de golpe
echo.
echo (Si ves un error arriba, toma captura y compartelo.)
pause
