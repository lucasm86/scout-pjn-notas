r"""
smoke_test.py - Validación de la cadena base de scout-pjn-notas.

OBJETIVO ÚNICO: abrir el perfil propio, quedar logueado en SCW, navegar a
"Lista de Expedientes Relacionados" y confirmar la llegada por texto visible.
NADA MÁS.

El smoke NO toca "Dejar nota", NO activa el filtro LETRADO, NO clickea ningún
lápiz y NO lee la lista de expedientes. Solo loguea, navega y confirma.

Ventana visible (headless=False). Saca screenshots a debug/ en cada hito.

Uso:
    .\.venv\Scripts\python.exe tests\smoke_test.py
"""
import re
import sys
import time
from pathlib import Path

# Consola Windows en UTF-8 para evitar mojibake en acentos/ñ.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# src/ al path para importar los módulos reciclados.
SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

import utils_pagina
from utils_pagina import log, shot, _asegurar_sin_overlay
from sesion import abrir_contexto, asegurar_sesion, cargar_credenciales

ETIQUETA_CONSULTAS = "Consultas"   # en /inicio: abre la app SCW en pestaña nueva
ETIQUETA_MENU = "Mis Expedientes"  # dentro de SCW
ETIQUETA_DESTINO = "Lista de Expedientes Relacionados"


def _ruta_ultimo_shot(name: str) -> Path:
    """Reconstruye la ruta del último screenshot tomado con shot()."""
    return utils_pagina.DEBUG_DIR / f"{utils_pagina._step_counter['n']:02d}_{name}.png"


def _abrir_scw(ctx, page):
    """Desde /inicio abre la app SCW haciendo click en "Consultas" (en este
    portal abre una pestaña nueva, igual que en el scout). Devuelve la página
    SCW (o la misma si no abrió pestaña), o None si no encuentra "Consultas".

    'Mis Expedientes' no vive en /inicio sino dentro de SCW: este es el salto
    que falta para llegar al destino."""
    _asegurar_sin_overlay(page)
    consultas = page.get_by_text(ETIQUETA_CONSULTAS, exact=True)
    if consultas.count() == 0:
        shot(page, "smoke_sin_consultas")
        log(f"No encontré '{ETIQUETA_CONSULTAS}' en /inicio. URL: {page.url}")
        return None

    log(f"Click en '{ETIQUETA_CONSULTAS}' (abre la app SCW en pestaña nueva)...")
    scw = page
    try:
        with ctx.expect_page(timeout=20000) as info:
            consultas.first.click()
        scw = info.value
        scw.wait_for_load_state("domcontentloaded")
        log(f"Pestaña SCW abierta. URL: {scw.url}")
    except PWTimeout:
        log("No abrió pestaña nueva tras 'Consultas': asumo navegación en la misma.")
    try:
        scw.wait_for_load_state("networkidle", timeout=15000)
    except PWTimeout:
        pass
    _asegurar_sin_overlay(scw)
    shot(scw, "smoke_scw")
    return scw


def _navegar_a_destino(ctx, page):
    """Abre el menú "Mis Expedientes" y entra a "Lista de Expedientes
    Relacionados" usando localizadores por TEXTO. Devuelve (page_destino,
    estado): estado en {'ok','sin_menu','sin_item'}. page_destino puede ser una
    pestaña nueva o la misma página."""
    _asegurar_sin_overlay(page)

    # --- Abrir el menú "Mis Expedientes" ---
    menu = page.get_by_text(ETIQUETA_MENU, exact=True)
    if menu.count() == 0:
        shot(page, "smoke_sin_menu")
        log(f"No encontré el menú '{ETIQUETA_MENU}' por texto. URL: {page.url}")
        return None, "sin_menu"

    log(f"Abriendo menú '{ETIQUETA_MENU}'...")
    try:
        menu.first.click()
    except Exception as e:
        log(f"Click en '{ETIQUETA_MENU}' falló ({e}); pruebo hover.")
        try:
            menu.first.hover()
        except Exception:
            pass
    page.wait_for_timeout(1000)
    _asegurar_sin_overlay(page)

    # --- Localizar el item "Lista de Expedientes Relacionados" ---
    item = page.get_by_text(ETIQUETA_DESTINO, exact=True)
    if item.count() == 0:
        # El submenú podría ser hover-only: reintento pasando el mouse por encima.
        log("No apareció el item todavía; reintento con hover sobre el menú.")
        try:
            menu.first.hover()
        except Exception:
            pass
        page.wait_for_timeout(800)
        item = page.get_by_text(ETIQUETA_DESTINO, exact=True)

    if item.count() == 0:
        shot(page, "smoke_sin_item")
        log(f"No encontré '{ETIQUETA_DESTINO}' tras abrir el menú. URL: {page.url}")
        return None, "sin_item"

    # --- Entrar al destino. Puede abrir pestaña nueva o navegar en la misma. ---
    log(f"Entrando a '{ETIQUETA_DESTINO}'...")
    destino = page
    try:
        with ctx.expect_page(timeout=6000) as info:
            item.first.click()
        destino = info.value
        destino.wait_for_load_state("domcontentloaded")
        log(f"Abrió pestaña nueva. URL: {destino.url}")
    except PWTimeout:
        log("No abrió pestaña nueva: asumo navegación en la misma página.")

    try:
        destino.wait_for_load_state("networkidle", timeout=10000)
    except PWTimeout:
        pass
    _asegurar_sin_overlay(destino)
    return destino, "ok"


def _confirmar_llegada(page, timeout_s=20):
    """Confirma la llegada SOLO por presencia de texto visible del encabezado
    de la pantalla (no por URL ni por 'algo cargó'). Prefiere un encabezado
    semántico; si no, cualquier ocurrencia visible exacta del texto.
    Devuelve (confirmada: bool, metodo: str, n_visibles: int)."""
    patron = re.compile(re.escape(ETIQUETA_DESTINO), re.I)
    fin = time.time() + timeout_s
    while time.time() < fin:
        # 1) Encabezado semántico (lo más único/estable).
        try:
            h = page.get_by_role("heading", name=patron)
            if h.count() > 0 and h.first.is_visible():
                return True, "heading", h.count()
        except Exception:
            pass
        # 2) Cualquier ocurrencia visible del texto exacto.
        try:
            t = page.get_by_text(ETIQUETA_DESTINO, exact=True)
            visibles = sum(1 for i in range(t.count()) if t.nth(i).is_visible())
            if visibles > 0:
                return True, "texto_visible", visibles
        except Exception:
            pass
        page.wait_for_timeout(500)
    return False, "no_encontrado", 0


def main():
    print("=== SMOKE TEST scout-pjn-notas ===", flush=True)
    user, pwd = cargar_credenciales()

    with sync_playwright() as p:
        ctx = abrir_contexto(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        estado = "(sin correr)"
        scw_status = "(sin correr)"
        nav_status = "(sin correr)"
        confirmada = False
        metodo = "-"
        n_visibles = 0
        ruta_final = None
        destino = page

        try:
            # --- 1) Sesión, con chequeo de estado EXPLÍCITO por valor ---
            print("\n--- Asegurando sesión ---", flush=True)
            estado = asegurar_sesion(page, user, pwd)

            if estado == "logueado":
                log("Sesión OK: logueado. Sigo a la navegación.")
            elif estado == "captcha":
                shot(page, "smoke_freno_captcha")
                print("\n>>> FRENO: apareció un CAPTCHA en el login. "
                      "No lo resuelvo ni lo salteo. Logueate a mano una vez "
                      "(queda en profile/) y reintentá. <<<", flush=True)
                return
            elif estado == "segundo_factor":
                shot(page, "smoke_freno_2fa")
                print("\n>>> FRENO: apareció un SEGUNDO FACTOR (2FA) en el login. "
                      "No lo salteo. Completalo a mano una vez y reintentá. <<<", flush=True)
                return
            else:  # 'fallo' o cualquier otro valor inesperado
                shot(page, "smoke_freno_sesion")
                print(f"\n>>> FRENO: no se pudo asegurar la sesión "
                      f"(estado='{estado}'). Revisá los screenshots en debug/. <<<", flush=True)
                return

            # --- 2) Entrar a la app SCW por "Consultas" (pestaña nueva) ---
            print("\n--- Abriendo la app SCW (click en 'Consultas') ---", flush=True)
            scw = _abrir_scw(ctx, page)
            if scw is None:
                scw_status = "sin_consultas"
                print("\n>>> FRENO: no encontré 'Consultas' en /inicio para entrar a SCW. "
                      "Revisá el screenshot. <<<", flush=True)
                return
            scw_status = "ok"

            # --- 3) Navegación por texto dentro de SCW hasta el destino ---
            print("\n--- Navegando en SCW: Mis Expedientes -> Lista de Expedientes Relacionados ---", flush=True)
            destino, nav_status = _navegar_a_destino(ctx, scw)
            if nav_status != "ok":
                print(f"\n>>> FRENO: no pude llegar al destino (nav='{nav_status}'). "
                      f"Revisá el screenshot y la URL logueada arriba. <<<", flush=True)
                return

            # --- 4) Confirmación ESTRICTA por texto del encabezado ---
            print("\n--- Confirmando llegada por texto visible ---", flush=True)
            confirmada, metodo, n_visibles = _confirmar_llegada(destino, timeout_s=20)
            shot(destino, "smoke_final")
            ruta_final = _ruta_ultimo_shot("smoke_final")

            if not confirmada:
                log(f"No apareció el texto '{ETIQUETA_DESTINO}'. URL actual: {destino.url}")
                print(f"\n>>> FRENO: llegué a navegar pero NO pude confirmar la "
                      f"pantalla por texto. No sigo a ciegas. Mirá {ruta_final}. <<<", flush=True)
                return

            log(f"Llegada confirmada por '{metodo}' ({n_visibles} coincidencia/s visible/s).")

        except Exception as e:
            log(f"EXCEPCIÓN: {type(e).__name__}: {e}")
            try:
                shot(destino, "smoke_excepcion")
                ruta_final = _ruta_ultimo_shot("smoke_excepcion")
            except Exception:
                pass
            print(">>> El smoke cortó por excepción. Revisá debug/. <<<", flush=True)
        finally:
            # --- 4) Reporte final ---
            print("\n=== REPORTE SMOKE ===", flush=True)
            print(f"  Estado de sesión devuelto : {estado}", flush=True)
            print(f"  App SCW (vía Consultas)   : {scw_status}", flush=True)
            print(f"  Navegación al destino     : {nav_status}", flush=True)
            print(f"  Llegada confirmada (texto): {confirmada}  "
                  f"(método: {metodo}, visibles: {n_visibles})", flush=True)
            print(f"  Screenshot final          : {ruta_final}", flush=True)
            try:
                print(f"  URL final                 : {destino.url}", flush=True)
            except Exception:
                pass
            print("  (El smoke no tocó 'Dejar nota', LETRADO, lápices ni leyó la lista.)", flush=True)
            ctx.close()


if __name__ == "__main__":
    main()
