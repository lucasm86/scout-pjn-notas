"""
navegador.py - Gestión del Chromium de Playwright BAJO DEMANDA.

A partir de v1.1 el .exe NO trae el navegador embebido (pesaba ~250 MB). En su
lugar, la primera vez que hace falta, se descarga el Chromium a la ubicación
estándar de Playwright (%LOCALAPPDATA%\\ms-playwright), una sola vez. Queda ahí
aunque se actualice el .exe.

Este módulo sabe: (a) si el Chromium está instalado y (b) cómo instalarlo
invocando el driver (node) que SÍ va embebido en el paquete.
"""
import subprocess
import sys
from pathlib import Path


def _sin_ventana() -> int:
    """Flag para que el subproceso no abra una consola en Windows."""
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def chromium_instalado() -> bool:
    """True si el ejecutable de Chromium ya está descargado y disponible."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:
        # Si ni siquiera podemos calcular la ruta, lo tratamos como ausente.
        return False


def _comando_install():
    """Comando (lista) + env para correr 'install chromium' con el driver
    embebido de Playwright. Funciona tanto en dev como dentro del .exe."""
    from playwright._impl._driver import compute_driver_executable, get_driver_env
    drv = compute_driver_executable()
    env = get_driver_env()
    # Según la versión, devuelve un path o una tupla (node, cli.js).
    if isinstance(drv, (list, tuple)):
        return [*drv, "install", "chromium"], env
    return [drv, "install", "chromium"], env


def instalar_chromium(on_linea=None):
    """Descarga e instala Chromium. Devuelve (ok: bool, mensaje: str).
    `on_linea(str)` (opcional) recibe cada línea de salida para mostrar progreso."""
    try:
        cmd, env = _comando_install()
    except Exception as e:
        return False, f"No pude ubicar el instalador de Playwright: {type(e).__name__}: {e}"

    try:
        proc = subprocess.Popen(
            cmd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=_sin_ventana(),
        )
        for linea in proc.stdout:
            linea = linea.rstrip()
            if linea and on_linea:
                on_linea(linea)
        proc.wait()
    except Exception as e:
        return False, f"Error al descargar Chromium: {type(e).__name__}: {e}"

    if proc.returncode == 0 and chromium_instalado():
        return True, "✅ Navegador instalado correctamente."
    return False, f"❌ La descarga del navegador falló (código {proc.returncode})."
