"""
main.py - Entrypoint único de la app "Scout PJN - Dejar notas".

Modos (según los argumentos):
  (sin flags)  -> abre la ventana de CONFIGURACIÓN (doble clic del colega).
  --run        -> corre el robot HEADLESS (lo dispara el Programador de tareas
                  los martes y viernes; sin ventana). Sale con el código del robot.
  --ahora      -> corre el robot AHORA y VISIBLE (prueba a demanda).
  --simulacro  -> corre HEADLESS pero NO deja notas: valida login+navegación
                  (mismo camino que la corrida agendada). Agregá --ver para mirarlo.
  --check      -> autotest: arranca el Chromium embebido y confirma que funciona
                  (sin tocar el portal). Sirve para validar el .exe en una máquina
                  limpia.

Diseño: a diferencia del plan original ("si ya está configurado, corre el
robot"), el doble clic SIEMPRE abre la ventana. Así el colega puede reprobar el
login, cambiar la hora o correr a demanda. Las corridas automáticas las dispara
la tarea agendada con --run, no el doble clic.
"""
import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).parent
# src/ y tests/ al path para importar los módulos del proyecto y el robot.
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "tests"))

import rutas


def _preparar_frozen():
    """Ajustes que solo aplican cuando corremos empaquetados en .exe."""
    if not rutas.esta_congelado():
        return
    # 1) Chromium embebido: Playwright busca los browsers DENTRO del paquete
    #    (así se instalan en el build con PLAYWRIGHT_BROWSERS_PATH=0).
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
    # 2) Sin consola (app windowed), sys.stdout/err son None y cualquier print()
    #    del robot rompería. Redirigimos toda la salida a un log en la carpeta de
    #    datos, que además sirve para diagnosticar corridas agendadas.
    try:
        log = open(rutas.dir_datos() / "app.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = log
        sys.stderr = log
    except Exception:
        pass


_preparar_frozen()


def _correr_robot(visible: bool, simulacro: bool = False) -> int:
    from dejar_notas import ejecutar
    return ejecutar(visible=visible, verboso=False, simulacro=simulacro)


def _check() -> int:
    """Autotest del empaquetado (no toca el portal): confirma que arranca el
    Chromium embebido y que el almacén seguro (keyring) responde."""
    lineas = []
    ok = True

    # 1) Chromium embebido.
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            navegador = p.chromium.launch(headless=True)
            navegador.new_page().goto("about:blank")
            navegador.close()
        lineas.append("✅ Chromium embebido OK.")
    except Exception as e:
        lineas.append(f"❌ Chromium NO arrancó: {type(e).__name__}: {e}")
        ok = False

    # 2) Almacén de credenciales (keyring / Credential Manager).
    try:
        import credenciales
        credenciales.esta_configurado()  # ejercita el backend, no expone nada
        lineas.append("✅ Almacén de credenciales OK.")
    except Exception as e:
        lineas.append(f"❌ Almacén de credenciales falló: {type(e).__name__}: {e}")
        ok = False

    msg = "\n".join(lineas)
    print(msg, flush=True)
    # En modo windowed no hay consola: mostramos también un cartel.
    # (SCOUT_SIN_CARTEL=1 lo omite, para poder autotestear sin bloquear.)
    if os.environ.get("SCOUT_SIN_CARTEL") == "1":
        return 0 if ok else 1
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        (messagebox.showinfo if ok else messagebox.showerror)("Autotest del navegador", msg)
        r.destroy()
    except Exception:
        pass
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="Scout PJN - Dejar notas")
    ap.add_argument("--run", action="store_true",
                    help="corre el robot headless (modo agendado, sin ventana).")
    ap.add_argument("--ahora", action="store_true",
                    help="corre el robot ahora, visible (prueba a demanda).")
    ap.add_argument("--simulacro", action="store_true",
                    help="corre headless SIN dejar notas (valida login/navegación).")
    ap.add_argument("--ver", action="store_true",
                    help="con --simulacro: muestra la ventana del navegador.")
    ap.add_argument("--check", action="store_true",
                    help="autotest: confirma que el Chromium embebido funciona.")
    args = ap.parse_args()

    if args.check:
        sys.exit(_check())
    if args.simulacro:
        sys.exit(_correr_robot(visible=args.ver, simulacro=True))
    if args.run:
        sys.exit(_correr_robot(visible=False))
    if args.ahora:
        sys.exit(_correr_robot(visible=True))

    from ventana_config import abrir
    abrir()


if __name__ == "__main__":
    main()
