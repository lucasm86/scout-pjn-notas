# Correr en Raspberry Pi (Linux) + OpenClaw

Guía para dejar el robot andando en una Raspberry Pi siempre encendida,
disparado por un agente OpenClaw vía cron los **martes y viernes 09:30** (hora de
Argentina), con aviso por WhatsApp y subida del registro al VAULT.

El código es Python + Playwright: corre igual en Linux/ARM. Lo único delicado es
el navegador Chromium en ARM, resuelto abajo con un fallback.

## 1. Traer el proyecto a la Pi

```bash
git clone https://github.com/lucasm86/scout-pjn-notas.git
cd scout-pjn-notas
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
chmod +x correr.sh   # por si el bit ejecutable no vino del clone
```

## 2. Chromium (el punto delicado en ARM)

Opción A — probar el Chromium de Playwright:
```bash
.venv/bin/python -m playwright install --with-deps chromium
```

Opción B — si A falla en la Pi, usar el Chromium del sistema:
```bash
sudo apt update && sudo apt install -y chromium
which chromium   # anotá la ruta (suele ser /usr/bin/chromium)
```
y declarar esa ruta en el `.env` (el robot la toma automáticamente):
```
CHROMIUM_PATH=/usr/bin/chromium
```

## 3. Credenciales (.env, NO se versiona)

```
PJN_USER=tu_usuario
PJN_PASS=tu_contraseña
# opcional en ARM:
# CHROMIUM_PATH=/usr/bin/chromium
```

## 4. Zona horaria de la Pi

```bash
sudo timedatectl set-timezone America/Argentina/Buenos_Aires
```

## 5. Primera corrida manual (¡importante!)

Probá una vez a mano para confirmar que loguea headless en la Pi:
```bash
./correr.sh
```
Esperá la línea final `>>> OK: ...`. Si el login pidiera captcha o segundo
factor, el robot frena y avisa; en ese caso hay que loguearse UNA vez con ventana
(en una Pi con escritorio: `./correr.sh --visible`) para dejar la sesión en
`profile/`, y después ya corre headless.

## 6. Prompt para el agente OpenClaw

Pegale esto a tu agente OpenClaw (cambiá `<RUTA>` por la ruta real del proyecto
en la Pi, p.ej. `/home/pi/scout-pjn-notas`):

> Programá una tarea recurrente por cron: **martes y viernes a las 09:30 hora de
> Argentina** (`30 9 * * 2,5`). Usá tu modelo local de **Ollama** para esta tarea.
> En cada disparo:
>
> 1. Ejecutá en esta Raspberry Pi el comando: `<RUTA>/correr.sh`
>    Corre headless, tarda unos minutos, imprime UNA línea de conclusión y
>    devuelve un código de salida.
> 2. Interpretá el resultado:
>    - exit 0, línea que empieza con `>>> OK:` → todo bien.
>    - exit 2, `>>> ATENCIÓN:` → algún expediente con problema.
>    - exit 1, `>>> ERROR:` → no se pudo (login/captcha, o no es día de nota).
> 3. Avisame por **WhatsApp**:
>    - exit 0: `✅ PJN notas OK — <línea de conclusión>`
>    - exit ≠ 0: `⚠️ PJN notas con problema (cod <N>) — <línea de conclusión>`
> 4. El robot deja un archivo nuevo en `<RUTA>/registros/notas_*.txt` (la línea de
>    conclusión incluye su ruta tras `Registro:`). Subí ese archivo al **VAULT**,
>    a la carpeta de registros de notas del PJN.
>
> No reintentes más de una vez; si falla, avisame igual por WhatsApp con el detalle.

## Notas

- El robot es idempotente: si por algo corre dos veces el mismo día, la segunda
  da "ya tenían nota" sin duplicar nada.
- El portal solo permite dejar nota los días de nota (martes y viernes). Si se
  dispara otro día, el robot lo refleja en la conclusión.
- `registros/`, `.env`, `profile/` y `debug/` no se versionan: son datos/credenciales.
