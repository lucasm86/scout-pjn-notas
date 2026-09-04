# build.spec - Empaqueta la app en un único .exe con PyInstaller.
#
#   .\.venv\Scripts\pyinstaller.exe build.spec --noconfirm
#
# Desde v1.1 el .exe NO trae el navegador embebido: Chromium se descarga bajo
# demanda la primera vez (ver src/navegador.py) a %LOCALAPPDATA%\ms-playwright.
# Por eso el .exe pesa ~50 MB en vez de ~350 MB.
#
# Resultado: dist/ScoutPJN-DejarNotas.exe (onefile, windowed).
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = [], [], []

# Playwright (driver node) + keyring.
for paquete in ("playwright", "keyring"):
    d, b, h = collect_all(paquete)
    datas += d
    binaries += b
    hiddenimports += h

# keyring descubre sus backends por metadata/entry-points: hay que copiarla.
datas += copy_metadata("keyring")

# Backend de Windows de keyring (Credential Manager) + su dependencia ctypes:
# se importan dinámicamente, PyInstaller no los ve solo.
hiddenimports += [
    "keyring.backends.Windows",
    "keyring.backends.fail",
    "win32ctypes.core",
    "win32ctypes.pywin32.win32cred",
    "win32ctypes.pywin32.pywintypes",
]

# Nuestros módulos viven en src/ y tests/ y se importan por ruta (no como paquete).
hiddenimports += [
    "rutas", "credenciales", "acerca", "agendar", "sesion", "navegador",
    "utils_pagina", "ventana_config", "dejar_notas", "probe_notas", "smoke_test",
]

a = Analysis(
    ["main.py"],
    pathex=["src", "tests"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)


# Los navegadores de Playwright (.local-browsers) NO van en el .exe. PyInstaller
# los junta al analizar el paquete aunque no los pidamos, así que los sacamos del
# TOC final. Esto hace el build reproducible sin importar si el paquete tiene o no
# browsers instalados en disco.
def _sin_browsers(toc):
    return [e for e in toc if ".local-browsers" not in str(e).replace("\\", "/").lower()]


a.datas = _sin_browsers(a.datas)
a.binaries = _sin_browsers(a.binaries)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ScoutPJN-DejarNotas",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX puede corromper binarios: desactivado.
    runtime_tmpdir=None,
    console=False,           # app windowed: sin consola. La salida va a app.log.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
