"""
main.py - Entrypoint único de la app "Scout PJN - Dejar notas".

Modos (según los argumentos):
  (sin flags)  -> abre la ventana de CONFIGURACIÓN (doble clic del colega).
  --run        -> corre el robot HEADLESS (lo dispara el Programador de tareas
                  los martes y viernes; sin ventana). Sale con el código del robot.
  --ahora      -> corre el robot AHORA y VISIBLE (prueba a demanda).
  --simulacro  -> corre HEADLESS pero NO deja notas: valida login+navegación
                  (mismo camino que la corrida agendada). Agregá --ver para mirarlo.

Diseño: a diferencia del plan original ("si ya está configurado, corre el
robot"), el doble clic SIEMPRE abre la ventana. Así el colega puede reprobar el
login, cambiar la hora o correr a demanda. Las corridas automáticas las dispara
la tarea agendada con --run, no el doble clic.
"""
import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).parent
# src/ y tests/ al path para importar los módulos del proyecto y el robot.
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "tests"))


def _correr_robot(visible: bool, simulacro: bool = False) -> int:
    from dejar_notas import ejecutar
    return ejecutar(visible=visible, verboso=False, simulacro=simulacro)


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
    args = ap.parse_args()

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
