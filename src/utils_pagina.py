"""
utils_pagina.py - Utilidades de página recicladas de scout-pjn-2.

  log()                   -> logging con prefijo (sangría uniforme).
  shot()                  -> screenshot numerado a debug/ + log de la URL.
  _asegurar_sin_overlay() -> resuelve el modal "Consulta en proceso" de
                             PrimeFaces (div.ui-widget-overlay) que durante cada
                             AJAX a veces queda colgado e intercepta los clicks
                             siguientes.
  _firma_hoja()           -> verificación por hash de contenido de página
                             (se agrega tras decidir el tema de acoplamiento).

Adaptado: rutas relativas a la raíz de scout-pjn-notas (carpeta debug/ propia).
"""
import hashlib
import time
from pathlib import Path

import rutas

# --- Rutas del proyecto ---
ROOT = Path(__file__).parent.parent
# Congelado en .exe, la raíz es un temp efímero (y a veces no escribible): las
# capturas de debug van a la carpeta de datos estable. En desarrollo es ROOT/debug.
DEBUG_DIR = rutas.dir_datos() / "debug"

_step_counter = {"n": 0}

# Si True, log() no imprime (modo silencioso del robot). shot() sigue guardando
# las capturas en debug/, solo se silencia su línea de log.
SILENCIOSO = False


def log(msg: str):
    if SILENCIOSO:
        return
    print(f"  {msg}", flush=True)


def shot(page, name: str):
    """Screenshot numerado a debug/ + log de la URL actual."""
    _step_counter["n"] += 1
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    fname = DEBUG_DIR / f"{_step_counter['n']:02d}_{name}.png"
    try:
        page.screenshot(path=str(fname), full_page=True)
        log(f"[shot] {fname.name}  <-  URL: {page.url}")
    except Exception as e:
        log(f"[shot] FALLÓ captura {name}: {e}  (URL: {page.url})")


def _asegurar_sin_overlay(page, timeout_s=10):
    """PrimeFaces muestra un modal 'Consulta en proceso' (div.ui-widget-overlay)
    durante cada AJAX; tras una acción a veces queda colgado e intercepta los
    clicks siguientes. Espera a que se cierre y, si persiste, lo oculta."""
    fin = time.time() + timeout_s
    while time.time() < fin:
        try:
            if page.locator("div.ui-widget-overlay:visible").count() == 0:
                return
        except Exception:
            return
        page.wait_for_timeout(300)
    # Quedó colgado: ocultar overlay + diálogo de 'procesando' para poder seguir.
    try:
        page.evaluate("""() => {
            document.querySelectorAll('.ui-widget-overlay').forEach(e => { e.style.display = 'none'; });
            document.querySelectorAll('div[id$="dialog_modal"], .ui-dialog').forEach(d => {
                if (/proces|consulta|espere/i.test(d.innerText || '')) d.style.display = 'none';
            });
        }""")
        log("  (overlay 'consulta en proceso' colgado -> lo oculté para continuar)")
    except Exception:
        pass


def _firma_hoja(page, selector):
    """Verificación por hash de contenido: devuelve (hash_md5, n_filas) de la
    región indicada por `selector`, o None si no existe.

    Sirve para confirmar que un postback AJAX (JSF/PrimeFaces) realmente cambió
    el contenido antes de avanzar, y para detectar loops de paginado (misma
    firma = misma hoja).

    Adaptación respecto del scout: allá la firma estaba atada a la tabla de
    actuaciones vía JS_FILAS. Acá conservo la MISMA lógica de hash (md5 de los
    textos de las filas, unidos por '||', + cantidad de filas) pero
    PARAMETRIZADA por `selector`, porque la tabla/región destino de este
    proyecto todavía no está relevada. No arrastra JS_FILAS."""
    try:
        datos = page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (!el) return null;
                const filas = el.querySelectorAll('tbody > tr, tr');
                const base = [...filas].map(
                    tr => (tr.innerText || '').replace(/\\s+/g, ' ').trim()
                ).join('||');
                return {base, n: filas.length};
            }""",
            selector,
        )
    except Exception:
        return None
    if not datos:
        return None
    h = hashlib.md5(datos["base"].encode("utf-8", "ignore")).hexdigest()
    return (h, datos["n"])
