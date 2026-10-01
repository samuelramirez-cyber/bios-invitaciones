@echo off
setlocal

echo ============================================================
echo   Generador de Invitaciones - Lanzador de Demo
echo ============================================================
echo.

rem --- 1. Verificar que Python 3.x este disponible en el PATH ---
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] No se encontro "python" en el PATH.
    echo         Instala Python 3.x desde https://www.python.org/downloads/
    echo         y marca "Add Python to PATH" durante la instalacion.
    echo.
    pause
    exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Se detecto una version de Python incompatible ^(se requiere 3.x^).
    python --version
    echo.
    pause
    exit /b 1
)

echo [OK] Python detectado:
python --version
echo.

rem --- 2. Instalar/actualizar dependencias de requirements.txt ---
echo Instalando dependencias de requirements.txt (esto puede tardar un poco la primera vez)...
python -m pip install -r requirements.txt --disable-pip-version-check --quiet
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la instalacion de dependencias. Revisa tu conexion a internet
    echo         o corre manualmente: python -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
echo [OK] Dependencias listas.
echo.

rem --- 3. Iniciar el lanzador de la demo (webhook + interfaz + tunel ngrok) ---
echo Iniciando la demo... (Ctrl+C en esta ventana la detiene por completo)
echo.
python tools\demo_launcher.py

echo.
echo ============================================================
echo   Demo finalizada.
echo ============================================================
pause
