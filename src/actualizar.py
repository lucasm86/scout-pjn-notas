r"""
actualizar.py - Autoactualización contra GitHub Releases (sin dependencias).

Flujo:
  1) hay_actualizacion(): consulta releases/latest y compara con APP_VERSION.
  2) descargar_y_verificar(): baja el .exe nuevo y valida su SHA256.
  3) aplicar_y_relanzar(): un .bat espera a que cierre este proceso, reemplaza el
     .exe y relanza. (El .exe en ejecución está bloqueado; por eso el swap lo hace
     un proceso externo que sobrevive a este.)

Notas de diseño:
  - Todo falla en SILENCIO si no hay internet: nunca debe frenar una corrida.
  - El .exe se baja con urllib, así que NO recibe "Mark of the Web": el relanzado
    no dispara SmartScreen (clave para la corrida agendada desatendida).
  - Solo tiene sentido congelado (.exe). En dev, aplicar_y_relanzar no hace nada.
"""
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import acerca
import rutas

API_LATEST = "https://api.github.com/repos/lucasm86/scout-pjn-notas/releases/latest"
EXE_NOMBRE = "ScoutPJN-DejarNotas.exe"
SHA_NOMBRE = EXE_NOMBRE + ".sha256"


# ------------------------------ versiones ------------------------------

def _tupla(v: str):
    """'v1.2.0' -> (1, 2, 0). Robusto ante sufijos raros."""
    partes = []
    for p in v.strip().lstrip("vV").split("."):
        dig = "".join(c for c in p if c.isdigit())
        partes.append(int(dig) if dig else 0)
    return tuple(partes) or (0,)


def _mas_nueva(remota: str, local: str) -> bool:
    return _tupla(remota) > _tupla(local)


# ------------------------------ red ------------------------------------

def _req(url: str):
    return urllib.request.Request(url, headers={
        "User-Agent": "scout-pjn-notas-updater",
        "Accept": "application/vnd.github+json",
    })


def hay_actualizacion():
    """Devuelve {'tag','exe_url','sha_url'} si hay versión más nueva, o None.
    Falla en silencio (None) ante cualquier problema de red."""
    try:
        with urllib.request.urlopen(_req(API_LATEST), timeout=10) as r:
            data = json.load(r)
    except Exception:
        return None

    tag = data.get("tag_name") or ""
    if not tag or not _mas_nueva(tag, acerca.APP_VERSION):
        return None

    exe_url = sha_url = None
    for a in data.get("assets", []):
        nombre = a.get("name", "")
        if nombre == EXE_NOMBRE:
            exe_url = a.get("browser_download_url")
        elif nombre == SHA_NOMBRE:
            sha_url = a.get("browser_download_url")
    if not exe_url:
        return None
    return {"tag": tag, "exe_url": exe_url, "sha_url": sha_url}


def _descargar(url: str, destino: Path, on_linea=None):
    with urllib.request.urlopen(_req(url), timeout=30) as r, open(destino, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        leido = 0
        ultimo = -1
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            leido += len(chunk)
            if total and on_linea:
                pct = leido * 100 // total
                if pct != ultimo and pct % 10 == 0:
                    ultimo = pct
                    on_linea(f"Descargando actualización... {pct}%")


def descargar_y_verificar(info, on_linea=None):
    """Baja el .exe nuevo y valida su SHA256 (si el release lo publica).
    Devuelve (ok, ruta_nuevo_exe, mensaje)."""
    carpeta = rutas.dir_datos() / "update"
    carpeta.mkdir(parents=True, exist_ok=True)
    nuevo = carpeta / EXE_NOMBRE.replace(".exe", ".new.exe")

    try:
        _descargar(info["exe_url"], nuevo, on_linea)
    except Exception as e:
        return False, None, f"No se pudo descargar la actualización: {type(e).__name__}: {e}"

    if info.get("sha_url"):
        try:
            with urllib.request.urlopen(_req(info["sha_url"]), timeout=10) as r:
                esperado = r.read().decode("utf-8", "replace").split()[0].lower()
        except Exception:
            esperado = None
        if esperado:
            real = hashlib.sha256(nuevo.read_bytes()).hexdigest().lower()
            if real != esperado:
                try:
                    nuevo.unlink()
                except OSError:
                    pass
                return False, None, ("La actualización no coincide con su checksum "
                                     "(SHA256). Se descartó por seguridad.")
    return True, str(nuevo), f"Actualización {info['tag']} descargada y verificada."


# ------------------------------ swap -----------------------------------

_BAT = r"""@echo off
setlocal
set "TARGET={target}"
set "NEW={new}"
set /a N=0
:retry
move /y "%NEW%" "%TARGET%" >nul 2>&1
if not errorlevel 1 goto done
set /a N+=1
if %N% geq 120 goto fin
ping -n 2 127.0.0.1 >nul
goto retry
:done
start "" "%TARGET%" {args}
:fin
del "%~f0" >nul 2>&1
"""


def aplicar_y_relanzar(nuevo_exe: str, args_relanzar):
    """Reemplaza el .exe en ejecución por `nuevo_exe` y relanza con
    `args_relanzar` (lista). Devuelve (ok, mensaje). El que llama debe salir
    (sys.exit) inmediatamente después para liberar el .exe."""
    if not rutas.esta_congelado():
        return False, "El reemplazo automático solo funciona en el .exe."

    target = sys.executable
    carpeta = rutas.dir_datos() / "update"
    carpeta.mkdir(parents=True, exist_ok=True)
    bat = carpeta / "aplicar_update.bat"
    contenido = _BAT.format(
        target=target, new=nuevo_exe, args=" ".join(args_relanzar),
    )
    bat.write_text(contenido, encoding="ascii", errors="replace")

    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | \
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(["cmd", "/c", str(bat)], creationflags=flags, close_fds=True)
    return True, "Aplicando actualización y reiniciando..."
