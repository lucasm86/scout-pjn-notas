r"""
agendar.py - Crea/actualiza/borra la tarea del Programador de tareas de Windows
que dispara el robot los MARTES y VIERNES a la hora elegida.

Usa `schtasks` (nativo de Windows). La tarea corre bajo el usuario interactivo
actual: es robusta (corre aunque la app esté cerrada) sin tener que guardar la
contraseña de Windows, a cambio de requerir que la sesión de Windows esté
iniciada a la hora agendada (aceptable para el uso de escritorio de los colegas).

En Linux/Raspberry Pi esto no aplica (se usa cron); las funciones avisan en vez
de fallar silenciosamente.
"""
import platform
import subprocess
import sys
from pathlib import Path

import rutas

# Nombre de la tarea en el Programador. Único y reconocible.
NOMBRE_TAREA = "ScoutPjnNotas"


def _es_windows() -> bool:
    return platform.system() == "Windows"


def _comando_disparo() -> str:
    """Comando que la tarea ejecutará: el robot en modo agendado (headless).
    - Congelado: el propio .exe con --run.
    - Desarrollo: pythonw main.py --run (pythonw = sin consola)."""
    if rutas.esta_congelado():
        return f'"{sys.executable}" --run'
    main_py = Path(__file__).parent.parent / "main.py"
    py = sys.executable
    # Preferimos pythonw.exe (sin ventana de consola) si está disponible.
    pyw = Path(py).with_name("pythonw.exe")
    ejecutable = str(pyw) if pyw.exists() else py
    return f'"{ejecutable}" "{main_py}" --run'


def _run(args):
    """Corre schtasks capturando salida. Devuelve (returncode, salida)."""
    try:
        p = subprocess.run(
            args, capture_output=True, text=True,
            encoding="cp850", errors="replace",
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 1, "No se encontró schtasks (¿no es Windows?)."


def crear_o_actualizar(hora: str):
    """Crea (o reemplaza) la tarea: MARTES y VIERNES a `hora` ('HH:MM').
    Devuelve (ok: bool, mensaje: str)."""
    if not _es_windows():
        return False, ("El agendado automático solo está soportado en Windows. "
                       "En Linux/Raspberry Pi usá cron (ver RASPBERRY_PI.md).")
    if not _validar_hora(hora):
        return False, f"Hora inválida: {hora!r}. Usá formato HH:MM (24h)."

    args = [
        "schtasks", "/Create",
        "/TN", NOMBRE_TAREA,
        "/TR", _comando_disparo(),
        "/SC", "WEEKLY",
        "/D", "TUE,FRI",
        "/ST", hora,
        "/F",  # reemplaza si ya existe
    ]
    rc, salida = _run(args)
    if rc != 0:
        return False, f"❌ No se pudo agendar la tarea:\n{salida.strip()}"

    # schtasks crea la tarea con "no iniciar/parar en batería". Lo revertimos para
    # que corra también con batería (los flags de energía no se pueden setear por
    # schtasks: van por el módulo ScheduledTasks de PowerShell).
    okb, _ = permitir_bateria()
    if okb:
        return True, (f"✅ Tarea agendada: martes y viernes a las {hora}. "
                      f"Corre también con batería.")
    return True, (f"✅ Tarea agendada: martes y viernes a las {hora}. "
                  f"(No pude habilitar la corrida con batería; correrá solo enchufada.)")


def permitir_bateria():
    """Habilita en la tarea correr con batería y no detenerse al pasar a batería.
    Devuelve (ok, salida). Usa el módulo ScheduledTasks de PowerShell."""
    if not _es_windows():
        return False, "Solo Windows."
    ps = (
        f"$ErrorActionPreference='Stop'; "
        f"$s = Get-ScheduledTask -TaskName '{NOMBRE_TAREA}'; "
        f"$s.Settings.DisallowStartIfOnBatteries = $false; "
        f"$s.Settings.StopIfGoingOnBatteries = $false; "
        f"Set-ScheduledTask -TaskName '{NOMBRE_TAREA}' -Settings $s.Settings | Out-Null"
    )
    rc, salida = _run([
        "powershell", "-NoProfile", "-NonInteractive", "-Command", ps
    ])
    return rc == 0, salida


def borrar():
    """Borra la tarea si existe. Devuelve (ok, mensaje)."""
    if not _es_windows():
        return False, "Solo Windows."
    rc, salida = _run(["schtasks", "/Delete", "/TN", NOMBRE_TAREA, "/F"])
    if rc == 0:
        return True, "Tarea eliminada."
    return False, f"No se pudo eliminar (¿no existía?):\n{salida.strip()}"


def existe() -> bool:
    """True si la tarea ya está creada en el Programador."""
    if not _es_windows():
        return False
    rc, _ = _run(["schtasks", "/Query", "/TN", NOMBRE_TAREA])
    return rc == 0


def _validar_hora(hora: str) -> bool:
    """Valida 'HH:MM' en 24h."""
    try:
        h, m = hora.split(":")
        return 0 <= int(h) <= 23 and 0 <= int(m) <= 59 and len(m) == 2
    except (ValueError, AttributeError):
        return False
