"""
sesion.py - Login y manejo de sesión en el portal SCW del PJN.

Reciclado de scout-pjn-2 (tests/probe_pjn.py): SOLO la lógica de login/sesión.
Corta exactamente cuando la sesión queda logueada en SCW. La navegación
post-login (a dónde ir DENTRO del portal) NO vive acá: es responsabilidad del
flujo que use este módulo. En el scout, esa navegación iba a "Nueva Consulta
Pública"; este proyecto va a otro destino que se releva más adelante.

Reutiliza el perfil persistente de Playwright (carpeta profile/) para no tener
que loguearse en cada corrida. Si Keycloak pide login (sesión vencida o perfil
nuevo), re-loguea autocompletando PJN_USER/PJN_PASS desde el .env.

Si aparece captcha o segundo factor, NO los saltea: frena y devuelve un estado
que le avisa al llamador que hace falta intervención humana.
"""
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from utils_pagina import log, shot
import credenciales
import rutas

# --- Rutas del proyecto ---
ROOT = Path(__file__).parent.parent
# El perfil persistente sale de rutas.py: en desarrollo es ROOT/profile (igual
# que siempre); congelado en .exe va a %LOCALAPPDATA% (estable, no efímero).
PROFILE_DIR = rutas.dir_perfil()

# Origen del portal, derivado del redirect_uri del login (no inventado).
PORTAL_ORIGIN = "https://portalpjn.pjn.gov.ar/"


def cargar_credenciales():
    """Devuelve (PJN_USER, PJN_PASS). Prioridad:
      1) Almacén seguro (keyring), si la app ya fue configurada.
      2) .env (compatibilidad con el flujo de desarrollo previo).
    Frena si no encuentra credenciales por ninguna vía."""
    cred = credenciales.cargar()
    if cred:
        user, pwd = cred
        masked = f"{user[:2]}***{user[-2:]}" if len(user) > 4 else "***"
        log(f"Credenciales desde el almacén seguro. PJN_USER={masked}  PJN_PASS(len)={len(pwd)}")
        return user, pwd

    load_dotenv(ROOT / ".env", interpolate=False)
    user = os.getenv("PJN_USER")
    pwd = os.getenv("PJN_PASS")
    if not user or not pwd or user.startswith("tu_"):
        print("ERROR: no hay credenciales configuradas (ni en el almacén ni en "
              ".env). Configurá la app primero. Frená.", flush=True)
        sys.exit(1)
    # Confirmamos carga sin filtrar el secreto.
    masked = f"{user[:2]}***{user[-2:]}" if len(user) > 4 else "***"
    log(f"Credenciales cargadas. PJN_USER={masked}  PJN_PASS(len)={len(pwd)}")
    return user, pwd


def abrir_contexto(playwright, headless=False):
    """Abre Chromium con el perfil persistente PROPIO de este proyecto.
    headless=False por defecto: queremos ver la ventana en el smoke.

    Portabilidad: en Linux/ARM (Raspberry Pi) el Chromium de Playwright puede no
    estar disponible. Si en el .env se define CHROMIUM_PATH (ej. /usr/bin/chromium)
    se usa ese binario del sistema; alternativamente CHROMIUM_CHANNEL (ej. 'chromium')."""
    kwargs = dict(
        user_data_dir=PROFILE_DIR,
        headless=headless,
        accept_downloads=True,
    )
    chromium_path = os.getenv("CHROMIUM_PATH")
    canal = os.getenv("CHROMIUM_CHANNEL")
    if chromium_path:
        kwargs["executable_path"] = chromium_path
    elif canal:
        kwargs["channel"] = canal
    ctx = playwright.chromium.launch_persistent_context(**kwargs)
    ctx.set_default_timeout(30000)
    return ctx


def _hay_captcha_o_2fa(page):
    """Detecta indicios de captcha o segundo factor. Devuelve 'captcha',
    'segundo_factor' o None. NO intenta resolverlos: solo avisa."""
    try:
        if page.locator(
            "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], "
            ".g-recaptcha, [data-sitekey]"
        ).count() > 0:
            return "captcha"
        if page.locator(
            "#otp, #totp, input[name='otp'], input[name*='code'], "
            "input[autocomplete='one-time-code']"
        ).count() > 0:
            return "segundo_factor"
    except Exception:
        pass
    return None


def _esperar_estado(page, timeout_s=30):
    """Espera a que el SPA se estabilice en un estado definitivo:
    'login'    -> se ve el form de Keycloak (#username)
    'logueado' -> se ve el menú del portal ('Consultas' o 'Mis Expedientes')
    'desconocido' si se agota el tiempo.

    Adaptación: el scout detectaba 'logueado' solo por 'Consultas'. Acá acepto
    además 'Mis Expedientes' (ambas son etiquetas reales del menú del portal),
    porque este proyecto entra por ese menú. Solo amplía la detección: no puede
    dar un falso positivo en la pantalla de login de Keycloak."""
    fin = time.time() + timeout_s
    while time.time() < fin:
        if page.query_selector("#username"):
            return "login"
        try:
            for etiqueta in ("Consultas", "Mis Expedientes"):
                if page.get_by_text(etiqueta, exact=True).count() > 0:
                    return "logueado"
        except Exception:
            pass
        page.wait_for_timeout(500)
    return "desconocido"


def asegurar_sesion(page, user, pwd):
    """Reusa la sesión de profile/. Si Keycloak pide login (sesión no
    persistida), re-loguea entrando por el origen del portal (el SPA arma un
    OAuth fresco). Corta cuando la sesión queda logueada en SCW: NO navega a
    ningún destino interno del portal.

    Devuelve un estado:
      'logueado'        -> sesión activa, listo para navegar
      'captcha'         -> apareció un captcha: FRENO, necesita un humano
      'segundo_factor'  -> apareció un 2.º factor: FRENO, necesita un humano
      'fallo'           -> no se pudo confirmar la sesión (revisar debug/)
    """
    log(f"Navegando al portal: {PORTAL_ORIGIN}")
    page.goto(PORTAL_ORIGIN, wait_until="domcontentloaded", timeout=45000)

    estado = _esperar_estado(page, 30)
    log(f"Estado tras cargar el portal: {estado}  (URL: {page.url})")

    if estado == "logueado":
        log("Sesión reutilizada desde profile/ (no hizo falta re-loguear).")
        shot(page, "sesion_reusada")
        return "logueado"

    if estado == "login":
        # Antes de tocar nada: ¿hay captcha o 2.º factor? Si sí, no autocompletamos.
        obst = _hay_captcha_o_2fa(page)
        if obst:
            shot(page, f"login_{obst}")
            print(f"FRENO: apareció {obst} en la pantalla de login. No lo salteo. "
                  f"Logueate a mano una vez (queda en profile/) y reintentá.", flush=True)
            return obst

        log("Keycloak pide login (sesión no persistida). Re-logueando por el portal...")
        page.fill("#username", user)
        page.fill("#password", pwd)
        shot(page, "relogin_form")
        page.click("[name='login']")

        # Un captcha/2.º factor puede aparecer recién después del submit.
        page.wait_for_timeout(1500)
        obst = _hay_captcha_o_2fa(page)
        if obst:
            shot(page, f"post_login_{obst}")
            print(f"FRENO: apareció {obst} después del login. No lo salteo.", flush=True)
            return obst

        estado2 = _esperar_estado(page, 30)
        log(f"Estado tras re-loguear: {estado2}  (URL: {page.url})")
        if estado2 == "logueado":
            shot(page, "sesion_relogueada")
            return "logueado"
        shot(page, "relogin_no_confirmado")
        print("FRENO: re-login no llegó al portal. Revisá el screenshot.", flush=True)
        return "fallo"

    shot(page, "estado_desconocido")
    print("FRENO: el portal no se estabilizó ni en login ni en sesión activa.", flush=True)
    return "fallo"


# Mensajes amigables por estado, para mostrar en la ventana de configuración.
_MENSAJE_ESTADO = {
    "logueado": "✅ Conexión OK: usuario y contraseña válidos. Sesión guardada.",
    "captcha": "⚠️ Apareció un captcha. Resolvelo en la ventana del navegador y "
               "volvé a probar; queda guardado para las corridas automáticas.",
    "segundo_factor": "⚠️ Pide un segundo factor. Completalo en la ventana del "
                      "navegador; queda guardado para las corridas automáticas.",
    "fallo": "❌ No se pudo confirmar el ingreso (¿usuario/contraseña incorrectos?).",
}


def probar_login(user, pwd, headless=False):
    """Valida credenciales contra el portal real y deja la sesión guardada en
    profile/ si el ingreso fue exitoso. Pensado para el botón 'Probar login' de
    la ventana de configuración.

    Devuelve un dict: {'ok': bool, 'estado': str, 'mensaje': str}.
    Por defecto abre la ventana visible (headless=False) para que, si aparece un
    captcha/2FA, el colega pueda resolverlo a mano una vez."""
    from playwright.sync_api import sync_playwright

    estado = "fallo"
    try:
        with sync_playwright() as p:
            ctx = abrir_contexto(p, headless=headless)
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                estado = asegurar_sesion(page, user, pwd)
            finally:
                ctx.close()
    except Exception as e:
        return {"ok": False, "estado": "error",
                "mensaje": f"❌ Error técnico al probar el login: {type(e).__name__}: {e}"}

    return {
        "ok": estado == "logueado",
        "estado": estado,
        "mensaje": _MENSAJE_ESTADO.get(estado, f"Estado inesperado: {estado}"),
    }
