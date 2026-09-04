#!/usr/bin/env bash
# Runner Linux / Raspberry Pi para el robot de notas (headless, silencioso).
# Uso manual:  ./correr.sh
# Cron:        30 9 * * 2,5  /ruta/a/scout-pjn-notas/correr.sh
# Propaga el código de salida del robot (0 OK / 2 atención / 1 error).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
exec "$DIR/.venv/bin/python" "$DIR/tests/dejar_notas.py" "$@"
