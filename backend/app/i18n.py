"""Idioma de la interfaz — la resolución vive acá y en ningún otro lado.

Dos perillas, deliberadamente:

* **`hotels.default_locale`** — se fija al PROVISIONAR la propiedad. Es el idioma
  con el que abre cualquiera que entre a ese hotel.
* **`users.locale`** — preferencia personal, y es **nullable a propósito**:
  `NULL` significa «usá el del hotel», que NO es lo mismo que «elegí español».
  Sin esa distinción, cambiar el default de la propiedad no le llegaría nunca a
  quien ya tuviera un valor guardado.

⚠️ **El motor no se entera del idioma.** Nada de `backend/app/engine/` recibe un
locale ni importa este módulo: el motor emite `line_code` estable —el código es
el contrato, el inglés es el fallback— y la traducción ocurre en el frontend. Es
la misma regla del provisionamiento de departamentos: la presentación filtra y
traduce, el cálculo nunca se entera. `tests/test_i18n_locale.py` falla si el
motor empieza a mirar esto.
"""
from __future__ import annotations

# Los dos que existen. Cualquier otro valor se ignora en vez de romper la
# pantalla: un locale basura en la base no puede dejar a nadie sin app.
LOCALES: tuple[str, ...] = ("es", "en")
DEFAULT_LOCALE = "es"

# La cookie que lee el frontend en el servidor. El token de sesión vive en
# `localStorage`, que el render del servidor NO puede leer — por eso el idioma
# viaja aparte, en una cookie que se escribe al entrar.
LOCALE_COOKIE = "finplan_locale"


def normalize_locale(value: str | None) -> str | None:
    """'ES', 'es-CR', ' en ' → 'es' / 'en'. Lo que no reconozca → None."""
    if not value:
        return None
    base = str(value).strip().lower().replace("_", "-").split("-")[0]
    return base if base in LOCALES else None


def resolve_locale(user_locale: str | None, hotel_locale: str | None) -> str:
    """El idioma efectivo: preferencia del usuario → default del hotel → español.

    Único lugar donde se decide. Cualquier endpoint que devuelva un idioma pasa
    por acá; si se copia esta regla a otro archivo, la copia se va a quedar
    atrás.
    """
    return (normalize_locale(user_locale)
            or normalize_locale(hotel_locale)
            or DEFAULT_LOCALE)
