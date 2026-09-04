r"""
probe_notas.py - SONDA de diagnóstico del flujo "Dejar nota" en SCW.

NO es el robot final. Objetivo: descubrir el mecanismo real de "Dejar nota" en
"Lista de Expedientes Relacionados", ejecutándolo de verdad en UN solo
expediente y reportando el comportamiento.

Se corre en DOS fases (la acción real está separada a propósito):

  --fase inspeccion  (default, NO deja ninguna nota):
      login -> navegar -> activar LETRADO -> activar "Dejar nota" (entra al modo,
      no deja nota) -> inventario de filas + HTML crudo de una fila y del lápiz
      -> relevar paginación. Sirve para descubrir los selectores reales.

  --fase accion  (deja UNA nota real en el primer expediente + reintento):
      se cablea recién después de ver el relevamiento de inspección.

Reusa lo probado: asegurar_sesion() y la navegación del smoke (por texto).
Ventana visible (headless=False). Screenshot en cada hito con shot().

Uso:
    .\.venv\Scripts\python.exe tests\probe_notas.py --fase inspeccion
"""
import argparse
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

import utils_pagina
from utils_pagina import log, shot, _asegurar_sin_overlay
from sesion import abrir_contexto, asegurar_sesion, cargar_credenciales

# Reuso del camino de navegación ya validado por el smoke (por texto visible).
from smoke_test import _abrir_scw, _navegar_a_destino, _confirmar_llegada

ETIQUETA_LETRADO = "LETRADO"
ETIQUETA_DEJAR_NOTA = "Dejar nota"
ETIQUETA_QUITAR_NOTA = "Quitar filtro dejar nota"

# Patrón de número de expediente, ej. "AAA 123456/2020", "BBB 7890/2019" (ficticios).
PAT_EXPEDIENTE = r"[A-Z]{2,5}\s*\d{3,}/\d{4}"

# JS: mapea las filas que tienen un nº de expediente en su primera celda y los
# controles (a/button/img/input) de cada fila, con sus atributos estables.
JS_INVENTARIO = r"""
(patron) => {
  const pat = new RegExp(patron);
  const rows = [...document.querySelectorAll('tr')];
  const out = [];
  for (const tr of rows) {
    const cells = [...tr.children];
    if (!cells.length) continue;
    const c0 = (cells[0].innerText || '').replace(/\s+/g, ' ').trim();
    const m = c0.match(pat);
    if (!m) continue;
    const controles = [...tr.querySelectorAll('a, button, img, input[type=image]')]
      .map(e => ({
        tag: e.tagName,
        id: e.id || null,
        cls: (typeof e.className === 'string' ? e.className : null) || null,
        title: e.title || e.getAttribute('aria-label') || e.getAttribute('alt') || null,
        src: e.getAttribute('src') || null,
        href: e.getAttribute('href') ? e.getAttribute('href').slice(0, 70) : null,
        onclick: e.getAttribute('onclick') ? true : false,
        txt: (e.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 30)
      }));
    out.push({
      expediente: m[0].replace(/\s+/g, ' '),
      trId: tr.id || null,
      nCeldas: cells.length,
      nControles: controles.length,
      controles
    });
  }
  return out;
}
"""

# JS: devuelve el outerHTML de la PRIMERA fila cuyo nº de expediente coincide.
JS_HTML_FILA = r"""
(expe) => {
  const rows = [...document.querySelectorAll('tr')];
  for (const tr of rows) {
    const c0 = (tr.children[0] ? tr.children[0].innerText : '').replace(/\s+/g, ' ').trim();
    if (c0.includes(expe)) return tr.outerHTML;
  }
  return null;
}
"""

# JS: releva la paginación al pie (contenedores típicos + controles número/Siguiente).
JS_PAGINACION = r"""
() => {
  const sels = ['.ui-paginator', '[id*="paginator"]', '[id*="Pages"]',
                '[id*="pages"]', '[class*="paginat"]'];
  const contenedores = [];
  for (const s of sels) {
    document.querySelectorAll(s).forEach(el => {
      contenedores.push({
        selectorProbado: s, id: el.id || null,
        cls: (typeof el.className === 'string' ? el.className : null),
        html: el.outerHTML.slice(0, 900)
      });
    });
  }
  const navs = [...document.querySelectorAll('a, button, span')]
    .filter(e => /^(\d{1,3}|siguiente|anterior|primero|último|ultimo|»|«|>|<|próx|prox)$/i
                  .test((e.innerText || '').trim()))
    .map(e => ({
      tag: e.tagName, id: e.id || null,
      cls: (typeof e.className === 'string' ? e.className : null),
      txt: (e.innerText || '').trim(), title: e.title || null,
      onclick: e.getAttribute('onclick') ? true : false
    }))
    .slice(0, 40);
  return {contenedores, controlesNumOSiguiente: navs};
}
"""


# JS: estado de la fila de un expediente (celdas + el lápiz 'Dejar nota'), para
# comparar antes/después de confirmar.
JS_ESTADO_FILA = r"""
(expe) => {
  const rows = [...document.querySelectorAll('tr')];
  for (const tr of rows) {
    const c0 = (tr.children[0] ? tr.children[0].innerText : '').replace(/\s+/g, ' ').trim();
    if (c0.includes(expe)) {
      const a = [...tr.querySelectorAll('a')]
        .find(x => /dejar nota/i.test(x.textContent || ''));
      return {
        encontrada: true,
        celdas: [...tr.children].map(td => (td.innerText || '').replace(/\s+/g, ' ').trim()),
        pencilClase: a ? a.className : null,
        pencilOuter: a ? a.outerHTML.replace(/\s+/g, ' ').slice(0, 260) : null,
        trLargo: tr.outerHTML.length
      };
    }
  }
  return {encontrada: false};
}
"""

# JS: junta mensajes/growl/alertas visibles (para detectar 'éxito').
JS_MENSAJES = r"""
() => {
  const out = [];
  const sels = ['.ui-growl', '.ui-messages', '.ui-message', '.alert',
                '[id*="messages"]', '[class*="growl"]', '[class*="mensaje"]'];
  for (const s of sels) {
    document.querySelectorAll(s).forEach(e => {
      const t = (e.innerText || '').replace(/\s+/g, ' ').trim();
      if (t) out.push({sel: s, txt: t.slice(0, 200)});
    });
  }
  return out;
}
"""


def _ubicar(scope, etiqueta):
    """Ubica un control por TEXTO/rol, sin inventar IDs. Prioridad: botón por
    nombre, texto exacto, texto parcial. Devuelve un locator o None."""
    pat = re.compile(re.escape(etiqueta), re.I)
    cand = scope.get_by_role("button", name=pat)
    if cand.count() > 0:
        return cand.first
    cand = scope.get_by_text(etiqueta, exact=True)
    if cand.count() > 0:
        return cand.first
    cand = scope.get_by_text(pat)
    if cand.count() > 0:
        return cand.first
    return None


def _volcar(nombre, data):
    """Guarda un JSON/HTML en debug/ (ignorado por git) y devuelve la ruta."""
    utils_pagina.DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    ruta = utils_pagina.DEBUG_DIR / nombre
    if isinstance(data, str):
        ruta.write_text(data, encoding="utf-8")
    else:
        ruta.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return ruta


def _llegar_a_lista(ctx, page, user, pwd):
    """Login (chequeo explícito) + navegación a 'Lista de Expedientes
    Relacionados'. Devuelve la página destino o None."""
    log("--- Asegurando sesión ---")
    estado = asegurar_sesion(page, user, pwd)
    if estado == "logueado":
        log("Sesión OK: logueado.")
    elif estado == "captcha":
        shot(page, "probe_freno_captcha")
        print(">>> FRENO: CAPTCHA en el login. No lo salteo. Logueate a mano y reintentá. <<<", flush=True)
        return None
    elif estado == "segundo_factor":
        shot(page, "probe_freno_2fa")
        print(">>> FRENO: SEGUNDO FACTOR (2FA) en el login. No lo salteo. <<<", flush=True)
        return None
    else:
        shot(page, "probe_freno_sesion")
        print(f">>> FRENO: no pude asegurar sesión (estado='{estado}'). Revisá debug/. <<<", flush=True)
        return None

    log("--- Navegando a 'Lista de Expedientes Relacionados' ---")
    scw = _abrir_scw(ctx, page)
    if scw is None:
        print(">>> FRENO: no pude abrir SCW desde 'Consultas'. <<<", flush=True)
        return None
    destino, nav = _navegar_a_destino(ctx, scw)
    if nav != "ok":
        print(f">>> FRENO: no llegué al destino (nav='{nav}'). <<<", flush=True)
        return None
    confirmada, metodo, n = _confirmar_llegada(destino, timeout_s=20)
    shot(destino, "probe_lista")
    if not confirmada:
        print(">>> FRENO: no confirmé la pantalla 'Lista de Expedientes Relacionados'. <<<", flush=True)
        return None
    log(f"En 'Lista de Expedientes Relacionados' (confirmado por {metodo}).")
    return destino


def _activar_letrado(page):
    """Paso 2: clickea el botón 'LETRADO'. Devuelve True/False."""
    log("--- Activando filtro de rol 'LETRADO' ---")
    _asegurar_sin_overlay(page)
    btn = _ubicar(page, ETIQUETA_LETRADO)
    if not btn:
        shot(page, "probe_sin_letrado")
        log(f"No encontré el control '{ETIQUETA_LETRADO}'. URL: {page.url}")
        return False
    log(f"Click en '{ETIQUETA_LETRADO}'...")
    btn.click()
    page.wait_for_timeout(1200)
    _asegurar_sin_overlay(page)
    shot(page, "probe_letrado")
    return True


def _activar_dejar_nota(page):
    """Paso 3: clickea 'Dejar nota' (entra al MODO, no deja nota). Verifica que
    el botón pase a 'Quitar filtro dejar nota'. Devuelve (ok, texto_verificado)."""
    log("--- Activando el MODO 'Dejar nota' (no deja nota todavía) ---")
    _asegurar_sin_overlay(page)
    btn = _ubicar(page, ETIQUETA_DEJAR_NOTA)
    if not btn:
        shot(page, "probe_sin_dejar_nota")
        log(f"No encontré el botón '{ETIQUETA_DEJAR_NOTA}'. URL: {page.url}")
        return False, False
    log(f"Click en '{ETIQUETA_DEJAR_NOTA}'...")
    btn.click()
    page.wait_for_timeout(1500)
    _asegurar_sin_overlay(page)
    shot(page, "probe_modo_dejar_nota")
    # Verificación: ¿apareció 'Quitar filtro dejar nota'?
    verif = page.get_by_text(ETIQUETA_QUITAR_NOTA, exact=False).count() > 0
    log(f"¿El botón pasó a '{ETIQUETA_QUITAR_NOTA}'?: {verif}")
    return True, verif


def fase_inspeccion(ctx, page, user, pwd):
    destino = _llegar_a_lista(ctx, page, user, pwd)
    if not destino:
        return

    if not _activar_letrado(destino):
        print(">>> FRENO en LETRADO. Revisá el screenshot. <<<", flush=True)
        return

    # Inventario ANTES de entrar al modo (para medir el delta = la columna lápiz).
    inv_antes = destino.evaluate(JS_INVENTARIO, PAT_EXPEDIENTE)
    log(f"Filas con expediente ANTES de 'Dejar nota': {len(inv_antes)}  "
        f"(controles/fila: {[f['nControles'] for f in inv_antes][:6]}...)")

    ok, verif = _activar_dejar_nota(destino)
    if not ok:
        print(">>> FRENO en 'Dejar nota'. Revisá el screenshot. <<<", flush=True)
        return

    # --- Paso 4: INVENTARIO + HTML crudo ---
    print("\n=== INVENTARIO (modo 'Dejar nota' activo) ===", flush=True)
    inv_desp = destino.evaluate(JS_INVENTARIO, PAT_EXPEDIENTE)
    ruta_inv = _volcar("inventario_filas.json", inv_desp)
    log(f"Filas con expediente DESPUÉS de 'Dejar nota': {len(inv_desp)}")
    log(f"Inventario completo volcado a: {ruta_inv}")

    print("\n--- Expedientes detectados (en orden de aparición) ---", flush=True)
    for i, f in enumerate(inv_desp):
        marca = " <- PRIMERO" if i == 0 else ""
        print(f"  [{i:02d}] {f['expediente']}  (trId={f['trId']}, controles={f['nControles']}){marca}", flush=True)

    # Delta de controles por fila (la columna 'lápiz' que aparece con el modo).
    print("\n--- DELTA de controles por fila (antes -> después) ---", flush=True)
    mapa_antes = {f["expediente"]: f["nControles"] for f in inv_antes}
    for f in inv_desp[:6]:
        a = mapa_antes.get(f["expediente"], "?")
        print(f"  {f['expediente']}: {a} -> {f['nControles']}", flush=True)

    # Controles de la PRIMERA fila (acá debería verse el lápiz y sus atributos).
    if inv_desp:
        print("\n--- Controles de la PRIMERA fila (candidatos a lápiz) ---", flush=True)
        for c in inv_desp[0]["controles"]:
            print(f"  {c['tag']:6} id={c['id']} cls={c['cls']} title={c['title']} "
                  f"src={c['src']} txt={c['txt']!r}", flush=True)

        # HTML crudo de una fila de ejemplo (la primera).
        expe0 = inv_desp[0]["expediente"]
        html_fila = destino.evaluate(JS_HTML_FILA, expe0)
        if html_fila:
            ruta_html = _volcar("fila_ejemplo.html", html_fila)
            log(f"\nHTML crudo de la fila '{expe0}' volcado a: {ruta_html}")
            print("\n--- HTML CRUDO de la fila de ejemplo (recortado a 1500 chars) ---", flush=True)
            print(html_fila[:1500], flush=True)

    # --- Paso 8: PAGINACIÓN (solo describir, NO avanzar) ---
    print("\n=== PAGINACIÓN (relevamiento, sin avanzar) ===", flush=True)
    pag = destino.evaluate(JS_PAGINACION)
    ruta_pag = _volcar("paginacion.json", pag)
    log(f"Relevamiento de paginación volcado a: {ruta_pag}")
    print(f"  Contenedores candidatos: {len(pag['contenedores'])}", flush=True)
    for c in pag["contenedores"]:
        print(f"    - {c['selectorProbado']}  id={c['id']}  cls={c['cls']}", flush=True)
    print(f"  Controles número/Siguiente: {len(pag['controlesNumOSiguiente'])}", flush=True)
    for n in pag["controlesNumOSiguiente"]:
        print(f"    - {n['tag']} txt={n['txt']!r} id={n['id']} cls={n['cls']}", flush=True)

    shot(destino, "probe_inspeccion_fin")
    print("\n>>> INSPECCIÓN OK. NO dejé ninguna nota. Revisá el inventario y el "
          "HTML para definir el selector del lápiz, y después corro --fase accion. <<<", flush=True)


def _ubicar_visible(scope, etiqueta):
    """Como _ubicar pero exige que el control sea VISIBLE (para el botón
    'Confirmar' del diálogo modal, evitando matches ocultos)."""
    pat = re.compile(re.escape(etiqueta), re.I)
    for cand in (scope.get_by_role("button", name=pat),
                 scope.get_by_role("link", name=pat),
                 scope.get_by_text(etiqueta, exact=True)):
        for i in range(cand.count()):
            try:
                if cand.nth(i).is_visible():
                    return cand.nth(i)
            except Exception:
                continue
    return None


def _localizar_lapiz(page, expe):
    """Localiza el lápiz 'Dejar nota' de la fila del expediente `expe`, de forma
    ESTABLE: fila por el texto del número (primera celda), lápiz por su nombre
    accesible 'Dejar nota' dentro de esa fila. Devuelve el locator o None."""
    fila = page.locator("tr").filter(has_text=expe)
    if fila.count() == 0:
        return None
    lapiz = fila.first.get_by_role("link", name=re.compile("Dejar nota", re.I))
    return lapiz.first if lapiz.count() > 0 else None


def _dejar_nota_una_vez(page, expe, etiqueta_paso):
    """Clickea el lápiz del expediente, espera el cartel de confirmación y
    clickea 'Confirmar'. Devuelve un dict con lo observado. NO compara estados:
    de eso se encarga el llamador."""
    obs = {"cartel_texto": None, "habia_cartel": False, "confirmo": False}
    _asegurar_sin_overlay(page)
    lapiz = _localizar_lapiz(page, expe)
    if not lapiz:
        log(f"[{etiqueta_paso}] No ubiqué el lápiz de {expe}.")
        shot(page, f"probe_{etiqueta_paso}_sin_lapiz")
        obs["sin_lapiz"] = True
        return obs

    log(f"[{etiqueta_paso}] Click en el lápiz de {expe}...")
    lapiz.click()
    page.wait_for_timeout(1500)
    shot(page, f"probe_{etiqueta_paso}_cartel")

    cartel = page.get_by_text(re.compile(r"confirma.*dejar nota", re.I))
    if cartel.count() > 0:
        obs["habia_cartel"] = True
        try:
            obs["cartel_texto"] = cartel.first.inner_text().strip()
        except Exception:
            pass
        log(f"[{etiqueta_paso}] Cartel: {obs['cartel_texto']!r}")
    else:
        log(f"[{etiqueta_paso}] NO apareció el cartel '¿Confirma dejar nota...?'.")

    confirmar = _ubicar_visible(page, "Confirmar")
    if not confirmar:
        log(f"[{etiqueta_paso}] No encontré un 'Confirmar' visible.")
        shot(page, f"probe_{etiqueta_paso}_sin_confirmar")
        return obs

    log(f"[{etiqueta_paso}] Click en 'Confirmar'...")
    # Marcador para detectar recarga total vs AJAX parcial.
    page.evaluate("() => { window.__probeMarker = 'vivo'; }")
    confirmar.click()
    page.wait_for_timeout(2500)
    _asegurar_sin_overlay(page)
    obs["confirmo"] = True
    obs["recarga_total"] = page.evaluate("() => (window.__probeMarker || null) === null")
    return obs


def fase_accion(ctx, page, user, pwd):
    destino = _llegar_a_lista(ctx, page, user, pwd)
    if not destino:
        return
    if not _activar_letrado(destino):
        print(">>> FRENO en LETRADO. <<<", flush=True)
        return
    ok, _ = _activar_dejar_nota(destino)
    if not ok:
        print(">>> FRENO en 'Dejar nota'. <<<", flush=True)
        return

    inv = destino.evaluate(JS_INVENTARIO, PAT_EXPEDIENTE)
    if not inv:
        shot(destino, "probe_accion_sin_filas")
        print(">>> FRENO: no hay filas con expediente. <<<", flush=True)
        return
    expe = inv[0]["expediente"]
    print(f"\n=== ACCIÓN REAL sobre el PRIMER expediente: {expe} ===", flush=True)
    log(f"Carátula (contexto): {inv[0].get('expediente')} | celdas de referencia ya en debug/")

    # --- Estado ANTES ---
    estado_antes = destino.evaluate(JS_ESTADO_FILA, expe)
    scroll_antes = destino.evaluate("() => window.scrollY")

    # --- Paso 5 + 6: dejar nota UNA vez ---
    print("\n--- Paso 5-6: lápiz -> cartel -> Confirmar (deja la nota REAL) ---", flush=True)
    obs1 = _dejar_nota_una_vez(destino, expe, "accion1")
    shot(destino, "probe_post_confirmar")

    # --- Observaciones post-confirmación ---
    scroll_desp = destino.evaluate("() => window.scrollY")
    estado_desp = destino.evaluate(JS_ESTADO_FILA, expe)
    mensajes = destino.evaluate(JS_MENSAJES)

    print("\n=== OBSERVACIONES POST-CONFIRMACIÓN ===", flush=True)
    log(f"¿Hubo cartel de confirmación?: {obs1['habia_cartel']}  texto={obs1['cartel_texto']!r}")
    log(f"¿Se clickeó 'Confirmar'?: {obs1['confirmo']}")
    log(f"¿Recarga TOTAL de página? (marcador perdido): {obs1.get('recarga_total')}")
    log(f"Scroll antes={scroll_antes}  después={scroll_desp}  "
        f"(¿volvió al tope?: {scroll_desp == 0 and scroll_antes != 0})")
    log(f"URL actual: {destino.url}")
    cambio = estado_antes.get("pencilOuter") != estado_desp.get("pencilOuter") or \
        estado_antes.get("celdas") != estado_desp.get("celdas")
    log(f"¿Cambió ALGO en la fila procesada?: {cambio}")
    if cambio:
        log(f"  pencil antes : {estado_antes.get('pencilClase')}")
        log(f"  pencil después: {estado_desp.get('pencilClase')}")
        log(f"  celdas antes : {estado_antes.get('celdas')}")
        log(f"  celdas después: {estado_desp.get('celdas')}")
    log(f"Mensajes/growl visibles tras confirmar: {mensajes if mensajes else 'ninguno'}")
    _volcar("accion_estado_antes_despues.json",
            {"expediente": expe, "antes": estado_antes, "despues": estado_desp,
             "obs_confirmacion": obs1, "mensajes": mensajes,
             "scroll": {"antes": scroll_antes, "despues": scroll_desp}})

    # --- Paso 7: REINTENTO deliberado en el MISMO expediente ---
    print("\n--- Paso 7: REINTENTO en el MISMO expediente (relevar bloqueo doble nota) ---", flush=True)
    obs2 = _dejar_nota_una_vez(destino, expe, "accion2")
    mensajes2 = destino.evaluate(JS_MENSAJES)
    shot(destino, "probe_reintento_fin")

    print("\n=== OBSERVACIONES DEL REINTENTO (bloqueo de doble nota) ===", flush=True)
    if obs2.get("sin_lapiz"):
        log("BLOQUEO: el lápiz YA NO está / no se pudo ubicar en el reintento.")
    else:
        log(f"¿Reapareció el cartel de confirmación?: {obs2['habia_cartel']}  texto={obs2['cartel_texto']!r}")
        log(f"¿Se pudo clickear 'Confirmar' de nuevo?: {obs2['confirmo']}")
    log(f"Mensajes/growl visibles en el reintento: {mensajes2 if mensajes2 else 'ninguno'}")
    _volcar("reintento_obs.json", {"expediente": expe, "obs": obs2, "mensajes": mensajes2})

    print("\n>>> ACCIÓN OK. Dejé UNA nota en el primer expediente + un reintento. "
          "No toqué ningún otro expediente ni avancé de página. <<<", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Sonda del flujo 'Dejar nota' (SCW/PJN)")
    ap.add_argument("--fase", choices=["inspeccion", "accion"], default="inspeccion")
    args = ap.parse_args()

    print(f"=== SONDA 'DEJAR NOTA' - fase: {args.fase} ===", flush=True)
    user, pwd = cargar_credenciales()

    with sync_playwright() as p:
        ctx = abrir_contexto(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            if args.fase == "inspeccion":
                fase_inspeccion(ctx, page, user, pwd)
            else:
                fase_accion(ctx, page, user, pwd)
        except Exception as e:
            log(f"EXCEPCIÓN: {type(e).__name__}: {e}")
            try:
                shot(page, "probe_excepcion")
            except Exception:
                pass
            print(">>> La sonda cortó por excepción. Revisá debug/. <<<", flush=True)
        finally:
            ctx.close()


if __name__ == "__main__":
    main()
