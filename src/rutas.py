"""
rutas.py - Un único lugar que decide DÓNDE viven los datos de la app
(perfil de Playwright, registros, configuración).

Motivo: cuando esto se empaquete con PyInstaller --onefile, el ejecutable se
descomprime en una carpeta TEMPORAL y efímera (sys._MEIPASS). Si guardáramos el
`profile/` ahí, la sesión logueada se perdería en cada corrida. Por eso, cuando
corremos "congelados" (frozen), los datos van a %LOCALAPPDATA%\\scout-pjn-notas,
que es estable y por-usuario de Windows.

En desarrollo (corriendo con `python main.py`) usamos la raíz del repo, para que
todo siga exactamente igual que hoy (mismo profile/, mismos registros/).
"""
import os
import sys
from pathlib import Path

APP = "scout-pjn-notas"


def esta_congelado() -> bool:
    """True si corremos dentro del .exe de PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def dir_datos() -> Path:
    """Carpeta base estable donde guardar datos por-usuario.
    - Congelado (.exe): %LOCALAPPDATA%\\scout-pjn-notas
    - Desarrollo:       raíz del repo (comportamiento actual)."""
    if esta_congelado():
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP
    else:
        base = Path(__file__).parent.parent  # raíz del repo
    base.mkdir(parents=True, exist_ok=True)
    return base


def dir_perfil() -> str:
    """Carpeta del perfil persistente de Playwright (sesión logueada)."""
    p = dir_datos() / "profile"
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def dir_registros() -> Path:
    """Carpeta donde el robot escribe los registros de cada corrida."""
    p = dir_datos() / "registros"
    p.mkdir(parents=True, exist_ok=True)
    return p


def archivo_config() -> Path:
    """Config NO secreta (usuario configurado, hora de corrida)."""
    return dir_datos() / "config.json"
