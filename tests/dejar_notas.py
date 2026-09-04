r"""
dejar_notas.py - Robot: deja nota en TODOS los expedientes de "Lista de
Expedientes Relacionados" (todas las páginas) y escribe un registro con marca
temporal de qué expedientes quedaron con nota y en qué fecha.

Reusa lo relevado por la sonda (probe_notas.py): login/sesión, navegación,
activación de LETRADO + modo "Dejar nota", localización del lápiz por fila y
lectura de '.ui-messages' para clasificar el resultado.

Hecho conocido (relevado): cada "Confirmar" hace una RECARGA TOTAL y vuelve a la
página 1. Por eso el robot reprocesa por NÚMERO de expediente (estable) y
re-navega de página en cada vuelta. Dejar nota es IDEMPOTENTE (re-correr da
"ya tenía"), así que re-ejecutar es seguro.

Límite del portal: una nota por expediente/usuario/día (martes y viernes son los
"días de nota"). Si no es día de nota, el robot lo reflejará en el registro.

Uso:
    .\.venv\Scripts\python.exe tests\dejar_notas.py
"""
import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

from playwright.sync_api import sync_playwright

import utils_pagina
import rutas
from utils_pagina import log, shot, _asegurar_sin_overlay
from sesion import abrir_contexto, cargar_credenciales

# Reuso íntegro de lo ya probado por la sonda.
from probe_notas import (
    _llegar_a_lista, _activar_letrado, _activar_dejar_nota,
    _ubicar_visible, _localizar_lapiz,
    JS_INVENTARIO, PAT_EXPEDIENTE, JS_MENSAJES,
)

REG_DIR = rutas.dir_registros()

# Regex del mensaje de BLOQUEO (ya tenía nota hoy).
RE_BLOQUEO = re.compile(r"mas de una vez al d[ií]a|ya se ha dejado nota", re.I)

# JS: ¿hay lápices de 'Dejar nota' en la tabla? (para saber si el modo sigue activo)
JS_HAY_LAPICES = r"""
() => [...document.querySelectorAll('a')]
  .some(a => /dejar nota/i.test(a.textContent || '') && a.querySelector('i.fa-pencil'))
"""

# JS: números de página disponibles en el paginador (incluye la actual).
JS_PAGINAS = r"""
() => {
  const cont = document.querySelector('[id$="divPagesAct"]');
  if (!cont) return [1];
  const s = new Set([1]);
  cont.querySelectorAll('a, span').forEach(e => {
    const t = (e.innerText || '').trim();
    if (/^\d+$/.test(t)) s.add(parseInt(t));
  });
  return [...s].sort((a, b) => a - b);
}
"""


def _set_expedientes(page):
    inv = page.evaluate(JS_INVENTARIO, PAT_EXPEDIENTE)
    return set(f["expediente"] for f in inv)


def _asegurar_modo(page):
    """Tras una recarga el modo suele persistir; si por algún motivo se perdió
    (no hay lápices), lo re-activo. Solo toco LETRADO como último recurso."""
    if page.evaluate(JS_HAY_LAPICES):
        return True
    log("Modo 'Dejar nota' no activo (sin lápices); re-activando...")
    _activar_dejar_nota(page)
    if page.evaluate(JS_HAY_LAPICES):
        return True
    _activar_letrado(page)
    _activar_dejar_nota(page)
    return page.evaluate(JS_HAY_LAPICES)


def _link_pagina(cont, P):
    """Locator del link de la página P dentro del contenedor del paginador."""
    l = cont.get_by_role("link", name=str(P), exact=True)
    if l.count() > 0:
        return l.first
    l = cont.locator(f"a:text-is('{P}')")
    if l.count() > 0:
        return l.first
    l = cont.locator("a").filter(has_text=re.compile(rf"^\s*{P}\s*$"))
    if l.count() > 0:
        return l.first
    return None


def _navegar_pagina(page, P):
    """Va a la página P. Si no hay link hacia P, asume que P es la página actual.
    Verifica el cambio comparando el conjunto de expedientes. Devuelve bool."""
    cont = page.locator('[id$="divPagesAct"]')
    if cont.count() == 0:
        return P == 1
    link = _link_pagina(cont.first, P)
    if link is None:
        return True  # no hay link hacia P -> ya estamos en P (es la actual)
    s0 = _set_expedientes(page)
    try:
        _asegurar_sin_overlay(page)
        link.click()
    except Exception as e:
        log(f"  click de paginación a {P} falló: {e}")
        return False
    fin = time.time() + 12
    while time.time() < fin:
        if _set_expedientes(page) != s0:
            return True
        page.wait_for_timeout(400)
    return False


def _procesar_expediente(page, expe):
    """Deja nota en un expediente: lápiz -> cartel -> Confirmar -> lee mensaje.
    Devuelve {estado, mensaje}. estado in {DEJADA, DEJADA_SIN_MSG, YA_TENIA,
    SIN_LAPIZ, SIN_CARTEL, ERROR}."""
    _asegurar_sin_overlay(page)
    lapiz = _localizar_lapiz(page, expe)
    if not lapiz:
        return {"estado": "SIN_LAPIZ", "mensaje": ""}
    try:
        lapiz.click()
    except Exception as e:
        return {"estado": "ERROR", "mensaje": f"click lápiz: {e}"}
    page.wait_for_timeout(1200)

    confirmar = _ubicar_visible(page, "Confirmar")
    if not confirmar:
        shot(page, f"robot_sin_cartel")
        return {"estado": "SIN_CARTEL", "mensaje": ""}
    try:
        confirmar.click()
    except Exception as e:
        return {"estado": "ERROR", "mensaje": f"click Confirmar: {e}"}

    # Confirmar dispara recarga TOTAL: esperamos a que vuelva la lista.
    page.wait_for_timeout(2500)
    _asegurar_sin_overlay(page)
    try:
        msgs = page.evaluate(JS_MENSAJES)
    except Exception:
        msgs = []
    texto = msgs[0]["txt"] if msgs else ""

    if RE_BLOQUEO.search(texto):
        estado = "YA_TENIA"
    elif texto:
        estado = "DEJADA"
    else:
        estado = "DEJADA_SIN_MSG"
    return {"estado": estado, "mensaje": texto}


def _escribir_registro(resultados, ahora):
    REG_DIR.mkdir(exist_ok=True)
    fecha = ahora.strftime("%Y-%m-%d")
    ruta = REG_DIR / f"notas_{ahora:%Y-%m-%d_%H%M%S}.txt"

    dejadas = [r for r in resultados if r["estado"] in ("DEJADA", "DEJADA_SIN_MSG")]
    ya = [r for r in resultados if r["estado"] == "YA_TENIA"]
    prob = [r for r in resultados if r["estado"] in ("SIN_LAPIZ", "SIN_CARTEL", "ERROR", "NO_NAVEGO", "SIMULACRO_SIN_LAPIZ")]

    L = []
    L.append("Registro de 'Dejar nota' - scout-pjn-notas")
    L.append(f"Corrida: {ahora:%Y-%m-%d %H:%M:%S}")
    L.append(f"Total procesados: {len(resultados)}  |  nota dejada ahora: {len(dejadas)}  "
             f"|  ya tenían nota de hoy: {len(ya)}  |  con problema: {len(prob)}")
    L.append("")
    L.append("Detalle (expediente | página | resultado | fecha):")
    for i, r in enumerate(resultados, 1):
        L.append(f"  [{i:02d}] {r['expediente']:18} | pág {r['pagina']} | {r['estado']:14} | {fecha}")
    if prob:
        L.append("")
        L.append("Con problema (revisar):")
        for r in prob:
            L.append(f"  {r['expediente']} -> {r['estado']}  {r.get('mensaje', '')[:90]}")
    ruta.write_text("\n".join(L) + "\n", encoding="utf-8")
    return ruta


def _correr(ctx, page, user, pwd, resultados, simulacro=False):
    """Hace el trabajo y llena `resultados`. Devuelve sin más si algo no se pudo
    asegurar (sesión / LETRADO / modo); la conclusión la arma main().

    Si `simulacro=True`: hace login, navega, activa LETRADO + 'Dejar nota' y mapea
    los expedientes, pero NO deja notas (nunca hace click en 'Confirmar'). Solo
    verifica que el lápiz de cada expediente esté localizable. Sirve para probar
    que el flujo headless funciona sin efectos reales."""
    destino = _llegar_a_lista(ctx, page, user, pwd)
    if not destino:
        return
    if not _activar_letrado(destino):
        return
    if not _activar_dejar_nota(destino)[0]:
        return

    # --- Mapeo: descubrir páginas y expedientes de cada una ---
    paginas = destino.evaluate(JS_PAGINAS)
    log(f"Páginas detectadas: {paginas}")
    objetivos = []  # [(expediente, pagina)]
    for P in paginas:
        if not _navegar_pagina(destino, P):
            log(f"No pude ir a la página {P} en el mapeo; la salteo.")
            continue
        exps = [f["expediente"] for f in destino.evaluate(JS_INVENTARIO, PAT_EXPEDIENTE)]
        log(f"  Página {P}: {len(exps)} expedientes.")
        for e in exps:
            objetivos.append((e, P))
    log(f"Total a procesar: {len(objetivos)} expedientes.")

    if simulacro:
        # --- SIMULACRO: verifico el lápiz de cada expediente SIN dejar nota ---
        log("=== SIMULACRO (no deja notas: solo verifica) ===")
        procesados = set()
        for (expe, P) in objetivos:
            if expe in procesados:
                continue
            _asegurar_modo(destino)
            if not _navegar_pagina(destino, P):
                resultados.append({"expediente": expe, "pagina": P,
                                   "estado": "NO_NAVEGO", "mensaje": ""})
                procesados.add(expe)
                continue
            _asegurar_sin_overlay(destino)
            hay = _localizar_lapiz(destino, expe) is not None
            estado = "SIMULACRO_OK" if hay else "SIMULACRO_SIN_LAPIZ"
            resultados.append({"expediente": expe, "pagina": P,
                               "estado": estado, "mensaje": ""})
            procesados.add(expe)
            log(f"  [{expe}] pág{P} -> {estado}")
        shot(destino, "robot_simulacro_fin")
        return

    # --- Proceso: por número de expediente, re-navegando en cada vuelta ---
    log("=== PROCESANDO (deja nota real) ===")
    procesados = set()
    for (expe, P) in objetivos:
        if expe in procesados:
            continue
        _asegurar_modo(destino)
        if not _navegar_pagina(destino, P):
            log(f"  [{expe}] no pude volver a la página {P}; lo marco NO_NAVEGO.")
            resultados.append({"expediente": expe, "pagina": P,
                               "estado": "NO_NAVEGO", "mensaje": ""})
            procesados.add(expe)
            continue
        res = _procesar_expediente(destino, expe)
        res.update({"expediente": expe, "pagina": P})
        resultados.append(res)
        procesados.add(expe)
        extra = f" ({res['mensaje'][:55]})" if res["mensaje"] else ""
        log(f"  [{expe}] pág{P} -> {res['estado']}{extra}")
    shot(destino, "robot_fin")


def ejecutar(visible=False, verboso=False, simulacro=False):
    """Corre el robot completo y DEVUELVE el código de salida (0/1/2), sin
    llamar a sys.exit. Así lo puede invocar tanto el CLI (main() de acá) como el
    entrypoint main.py de la app. Códigos:
      0 -> OK (notas dejadas / ya tenían, sin errores)
      1 -> no se procesó ningún expediente (login/captcha/no es día de nota)
      2 -> se procesó pero hubo expedientes con problema.
    Con `simulacro=True` NO deja notas: valida login+navegación+mapeo (ver _correr)."""
    utils_pagina.SILENCIOSO = not verboso
    ahora = datetime.now()
    modo = "SIMULACRO, no deja notas" if simulacro else "deja notas reales"
    print(f"[{ahora:%Y-%m-%d %H:%M}] SCW: {modo} "
          f"({'visible' if visible else 'headless'})... tarda unos minutos.", flush=True)

    user, pwd = cargar_credenciales()
    resultados = []
    ruta = None

    with sync_playwright() as p:
        ctx = abrir_contexto(p, headless=not visible)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            _correr(ctx, page, user, pwd, resultados, simulacro=simulacro)
        except Exception as e:
            log(f"EXCEPCIÓN: {type(e).__name__}: {e}")
            try:
                shot(page, "robot_excepcion")
            except Exception:
                pass
        finally:
            if resultados:
                ruta = _escribir_registro(resultados, ahora)
            ctx.close()

    # --- Conclusión + código de salida ---
    if simulacro:
        oks = [r for r in resultados if r["estado"] == "SIMULACRO_OK"]
        malos = [r for r in resultados if r["estado"] in ("SIMULACRO_SIN_LAPIZ", "NO_NAVEGO")]
        if not resultados:
            print(">>> SIMULACRO ERROR: no se llegó a la lista (revisá login/captcha en "
                  "headless; capturas en debug/). NO se dejó ninguna nota. <<<", flush=True)
            return 1
        if malos:
            print(f">>> SIMULACRO ATENCIÓN: {len(oks)} expediente(s) OK, {len(malos)} con "
                  f"problema (lápiz no ubicable). Registro: {ruta}. NO se dejó ninguna nota. <<<",
                  flush=True)
            return 2
        print(f">>> SIMULACRO OK: login+navegación headless funcionan; {len(oks)} expediente(s) "
              f"listos para dejar nota. NO se dejó ninguna nota. Registro: {ruta} <<<", flush=True)
        return 0

    dejadas = [r for r in resultados if r["estado"] in ("DEJADA", "DEJADA_SIN_MSG")]
    ya = [r for r in resultados if r["estado"] == "YA_TENIA"]
    prob = [r for r in resultados if r["estado"] in ("SIN_LAPIZ", "SIN_CARTEL", "ERROR", "NO_NAVEGO")]

    if not resultados:
        print(">>> ERROR: no se procesó ningún expediente (revisá login/navegación; "
              "¿captcha/2FA, o no es día de nota?). Capturas en debug/. <<<", flush=True)
        return 1
    if prob:
        print(f">>> ATENCIÓN: {len(dejadas)} nota(s) dejada(s), {len(ya)} ya tenían, "
              f"{len(prob)} con PROBLEMA. Revisá el registro: {ruta} (y debug/). <<<", flush=True)
        return 2
    print(f">>> OK: dejé nota en {len(dejadas)} expediente(s); {len(ya)} ya tenían nota de hoy; "
          f"0 errores. Registro: {ruta} <<<", flush=True)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Deja nota en TODOS los expedientes de 'Lista de Expedientes Relacionados' (SCW/PJN).")
    ap.add_argument("--visible", action="store_true",
                    help="muestra la ventana del navegador (debug). Por defecto: headless.")
    ap.add_argument("--verboso", action="store_true",
                    help="log detallado paso a paso. Por defecto: silencioso.")
    ap.add_argument("--simulacro", action="store_true",
                    help="NO deja notas: solo valida login+navegación+mapeo (dry-run).")
    args = ap.parse_args()
    sys.exit(ejecutar(visible=args.visible, verboso=args.verboso, simulacro=args.simulacro))


if __name__ == "__main__":
    main()
