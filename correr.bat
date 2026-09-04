@echo off
REM Runner Windows simple para el robot de notas (headless, silencioso).
REM Uso: doble click, o desde una terminal:  correr.bat
"%~dp0.venv\Scripts\python.exe" "%~dp0tests\dejar_notas.py" %*
echo.
pause
