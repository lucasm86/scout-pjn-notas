"""
credenciales.py - Guardado seguro de credenciales del PJN y de la configuración.

- La CONTRASEÑA va al almacén seguro del sistema operativo vía `keyring`:
  en Windows es el Credential Manager (backend WinVaultKeyring); en Linux/RPi
  usa el backend nativo disponible. Nunca queda en texto plano en disco.
- Lo NO secreto (qué usuario está configurado, a qué hora corre) va a un JSON
  simple en la carpeta de datos (ver rutas.py).

Diseño: cada instalación es de UN colega en SU máquina de Windows, así que hay
un único usuario "activo" por instalación (el que quedó configurado). El CUIL
identifica la credencial dentro del almacén.
"""
import json

import keyring

from rutas import archivo_config

# Nombre del "servicio" bajo el que se guarda la credencial en el almacén.
SERVICIO = "scout-pjn-notas"


# --------------------------- Contraseña (segura) ---------------------------

def guardar_credencial(user: str, pwd: str) -> None:
    """Guarda/actualiza la contraseña del `user` (CUIL) en el almacén seguro."""
    keyring.set_password(SERVICIO, user, pwd)


def leer_password(user: str):
    """Devuelve la contraseña guardada para `user`, o None si no hay."""
    return keyring.get_password(SERVICIO, user)


def borrar_credencial(user: str) -> None:
    """Borra la contraseña de `user` del almacén (si existe)."""
    try:
        keyring.delete_password(SERVICIO, user)
    except keyring.errors.PasswordDeleteError:
        pass


# --------------------------- Config (no secreta) ---------------------------

def leer_config() -> dict:
    """Lee el config.json. Devuelve {} si no existe o está corrupto."""
    ruta = archivo_config()
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def guardar_config(cfg: dict) -> None:
    """Escribe el config.json (usuario configurado, hora, etc.)."""
    archivo_config().write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --------------------------- API de alto nivel -----------------------------

def guardar_todo(user: str, pwd: str, hora: str) -> None:
    """Guarda credencial + config en un solo paso (lo que hace 'Guardar')."""
    guardar_credencial(user, pwd)
    guardar_config({"pjn_user": user, "hora": hora})


def usuario_configurado():
    """CUIL del usuario configurado, o None si todavía no se configuró."""
    return leer_config().get("pjn_user") or None


def hora_configurada():
    """Hora 'HH:MM' elegida para las corridas, o None."""
    return leer_config().get("hora") or None


def esta_configurado() -> bool:
    """True si hay un usuario configurado Y su contraseña está en el almacén."""
    user = usuario_configurado()
    return bool(user) and leer_password(user) is not None


def cargar():
    """Devuelve (user, pwd) del usuario configurado, o None si falta algo.
    Es la fuente de credenciales que usa el robot en modo desatendido."""
    user = usuario_configurado()
    if not user:
        return None
    pwd = leer_password(user)
    if not pwd:
        return None
    return user, pwd
