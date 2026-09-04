# scout-pjn-notas

Automatiza la acción **"Dejar nota"** sobre los expedientes propios del letrado en
el portal **SCW** (Sistema de Consulta Web) del Poder Judicial de la Nación
(app JSF/JBoss Seam).

El robot entra a **Mis Expedientes → Lista de Expedientes Relacionados**, activa
el filtro **LETRADO** y el modo **Dejar nota**, y deja nota en **todos** los
expedientes de **todas** las páginas. Al terminar escribe un **registro con
marca temporal** de qué expedientes quedaron con nota y en qué fecha.

## Aviso legal / Descargo de responsabilidad

**Software libre de uso personal.** Se distribuye **TAL CUAL, sin garantía de
ningún tipo** (ver [LICENSE](LICENSE), licencia MIT). Cada persona lo usa **bajo
su propia y exclusiva responsabilidad**.

Esta herramienta **no tiene relación, patrocinio ni aval del Poder Judicial de la
Nación** ni de ningún organismo estatal. Solo automatiza, con las **credenciales
del propio usuario**, acciones que este puede realizar manualmente en el portal
SCW. El usuario es el **único responsable** del uso de sus credenciales y del
cumplimiento de los términos de uso del portal.

## ⚠️ Días de nota

El portal solo permite dejar nota los **martes y viernes**. El límite es **una
nota por expediente, por usuario, por día** (lo controla el servidor). Re-correr
el mismo día es **inofensivo**: los expedientes ya marcados devuelven
"ya tenía", sin duplicar nada.

## Uso (operativo)

**Forma rápida (recomendada):**
- **Windows:** doble click en `correr.bat` (o desde una terminal: `correr.bat`).
- **Linux / Raspberry Pi:** `./correr.sh`

**Equivalente directo:**
```powershell
# Windows (PowerShell)
.\.venv\Scripts\python.exe tests\dejar_notas.py
```
```bash
# Linux
.venv/bin/python tests/dejar_notas.py
```

Por defecto corre **headless** (sin ventana) y **silencioso**: solo imprime una
línea al empezar y **una conclusión** al terminar, con código de salida.

> Nota: el límite es **una nota por expediente y por día**. Si ya las dejaste hoy,
> una corrida nueva dirá `OK: dejé nota en 0 expediente(s); N ya tenían` — eso es
> correcto, no es un error.

Para correr en la **Raspberry Pi** (cron martes/viernes 09:30, OpenClaw, Ollama,
aviso por WhatsApp y subida del registro al VAULT) ver
**[RASPBERRY_PI.md](RASPBERRY_PI.md)**.

Salida posible:
- `>>> OK: dejé nota en N expediente(s); M ya tenían nota de hoy; 0 errores. Registro: ... <<<`  → exit 0
- `>>> ATENCIÓN: ... con PROBLEMA. Revisá el registro ... <<<`  → exit 2
- `>>> ERROR: no se procesó ningún expediente ... <<<`  → exit 1

El registro queda en `registros\notas_AAAA-MM-DD_HHMMSS.txt`.

Flags (para depurar, no hacen falta en el uso normal):
- `--visible`  muestra la ventana del navegador.
- `--verboso`  log detallado paso a paso.

## Setup (solo si clonás el repo de cero)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

Crear el archivo `.env` (NO se versiona) con las credenciales del PJN:

```
PJN_USER=tu_usuario
PJN_PASS=tu_contraseña
```

Si aparece captcha o segundo factor en el login, el robot **frena y avisa**:
logueate una vez a mano (la sesión queda en `profile/`) y reintentá.

## Diagnóstico (no operativo)

- `tests\smoke_test.py` — valida login + navegación hasta la lista (ventana visible).
- `tests\probe_notas.py --fase inspeccion` — releva selectores del flujo sin dejar nota.
- `tests\probe_notas.py --fase accion` — deja UNA nota (primer expediente) + reintento, para diagnóstico.

## Seguridad

El repositorio versiona **solo código**. Nunca se suben credenciales, sesión ni
datos: `.env`, `.venv/`, `profile/` (perfil de Playwright con la sesión),
`debug/` (capturas) y `registros/` (listan expedientes) están en `.gitignore`.

## Estructura

```
src/sesion.py          login/sesión SCW (perfil persistente propio, autocompleta del .env)
src/utils_pagina.py    utilidades (log, shot, overlay "Consulta en proceso", hash de contenido)
tests/dejar_notas.py   EL ROBOT: deja nota en todos los expedientes + registro
tests/probe_notas.py   sonda de diagnóstico del flujo "Dejar nota"
tests/smoke_test.py    smoke de login + navegación
requirements.txt       playwright, python-dotenv
```
