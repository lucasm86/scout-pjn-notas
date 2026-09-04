# build.spec - Empaqueta la app en un único .exe con PyInstaller.
#
#   .\.venv\Scripts\pyinstaller.exe build.spec --noconfirm
#
# Requisitos previos (una vez):
#   PLAYWRIGHT_BROWSERS_PATH=0  playwright install chromium
#   (así el Chromium queda DENTRO del paquete y se embebe en el .exe)
#
# Resultado: dist/ScoutPJN-DejarNotas.exe (~150-250 MB, onefile).
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = [], [], []

# Playwright + Chromium embebido (driver node + .local-browsers).
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
    "rutas", "credenciales", "acerca", "agendar", "sesion",
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
    upx=False,               # UPX puede corromper el Chromium embebido: desactivado.
    runtime_tmpdir=None,
    console=False,           # app windowed: sin consola. La salida va a app.log.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
