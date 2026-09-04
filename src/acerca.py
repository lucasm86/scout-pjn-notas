"""
acerca.py - Identidad y texto legal de la app, en un solo lugar.

La idea es tener UNA fuente de verdad para: nombre, versión, URL del repositorio
y el descargo de responsabilidad. Lo usa el cartel "Acerca de..." de la ventana
de configuración, y debería coincidir con lo que dice el README y la LICENSE.
"""

APP_NOMBRE = "Scout PJN — Dejar notas"
APP_VERSION = "1.0.0"
REPO_URL = "https://github.com/lucasm86/scout-pjn-notas"

# Descargo de responsabilidad. Lenguaje estándar de software libre + aclaración
# de no-afiliación con el Poder Judicial. NO es asesoramiento legal.
DESCARGO = (
    "Software libre de uso personal. Se distribuye TAL CUAL, sin garantía de "
    "ningún tipo. Cada persona lo usa bajo su propia y exclusiva responsabilidad.\n\n"
    "Esta herramienta NO tiene relación, patrocinio ni aval del Poder Judicial de "
    "la Nación ni de ningún organismo estatal. Solo automatiza, con las credenciales "
    "del propio usuario, acciones que este puede hacer manualmente en el portal SCW. "
    "El usuario es el único responsable del uso de sus credenciales y del "
    "cumplimiento de los términos de uso del portal.\n\n"
    "Licencia MIT."
)


def texto_acerca() -> str:
    """Texto completo del cartel 'Acerca de...'."""
    return (
        f"{APP_NOMBRE}\n"
        f"Versión {APP_VERSION}\n\n"
        f"{DESCARGO}\n\n"
        f"Código fuente:\n{REPO_URL}"
    )
