# -*- coding: utf-8 -*-
"""Idioma: la resolución vive en un solo lugar y el motor no se entera.

Dos reglas que sostienen todo lo demás:

1. `usuario → hotel → 'es'`, decidido en `app/i18n.py` y en ningún otro archivo.
   Copiada en cada endpoint, una copia se queda atrás.
2. **El motor es Python puro.** Nada de `app/engine/` recibe un locale: el motor
   emite `line_code` estable —el código es el contrato— y la traducción ocurre
   en el frontend. Es la misma regla del provisionamiento de departamentos.
"""
import pathlib

import pytest

from app import i18n
from app.i18n import (
    DEFAULT_LOCALE, LOCALE_COOKIE, LOCALES, normalize_locale, resolve_locale,
)


# ── normalización ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("entrada,esperado", [
    ("es", "es"), ("en", "en"),
    ("ES", "es"), (" EN ", "en"),
    ("es-CR", "es"), ("en_US", "en"),
    ("fr", None), ("", None), (None, None), ("español", None),
])
def test_normalizar(entrada, esperado):
    assert normalize_locale(entrada) == esperado


def test_un_locale_basura_no_deja_sin_app_a_nadie():
    """Un valor raro en la base cae al default en vez de romper la pantalla."""
    assert resolve_locale("klingon", "marciano") == DEFAULT_LOCALE


# ── la cadena de resolución ───────────────────────────────────────────────────

def test_manda_la_preferencia_del_usuario():
    assert resolve_locale("en", "es") == "en"
    assert resolve_locale("es", "en") == "es"


def test_sin_preferencia_manda_el_hotel():
    assert resolve_locale(None, "en") == "en"


def test_sin_nada_es_espanol():
    assert resolve_locale(None, None) == "es"


def test_null_no_es_lo_mismo_que_elegir_espanol():
    """La distinción que hace que el campo sea nullable: con NULL, mover el
    default de la propiedad SÍ le llega al usuario; con 'es' guardado, no."""
    assert resolve_locale(None, "en") == "en"
    assert resolve_locale("es", "en") == "es"


# ── la regla que no se rompe ──────────────────────────────────────────────────

def test_el_motor_no_se_entera_del_idioma():
    """Si `engine/` empieza a mirar el locale, el mismo cálculo podría dar
    distinto según el idioma del que mira — y eso no se ve hasta que alguien
    compara dos pantallas."""
    motor = pathlib.Path(i18n.__file__).parent / "engine"
    ofensores = []
    for p in motor.rglob("*.py"):
        texto = p.read_text(encoding="utf-8")
        if "app.i18n" in texto or "resolve_locale" in texto or LOCALE_COOKIE in texto:
            ofensores.append(p.name)
    assert not ofensores, (
        f"El motor no puede leer el idioma: {ofensores}. Emite line_code "
        f"estable; la traducción ocurre en el frontend.")


def test_solo_hay_dos_idiomas_y_el_default_es_uno_de_ellos():
    assert LOCALES == ("es", "en")
    assert DEFAULT_LOCALE in LOCALES


def test_la_cookie_tiene_el_nombre_que_lee_el_frontend():
    """`frontend/i18n/request.ts` lee exactamente este nombre. El token vive en
    localStorage y el servidor no lo puede leer: el idioma viaja por acá."""
    assert LOCALE_COOKIE == "finplan_locale"


# ── los campos existen donde se dijo ──────────────────────────────────────────

def test_el_usuario_guarda_su_idioma_y_admite_null():
    from app.models.user import User
    col = User.__table__.c["locale"]
    assert col.nullable is True, "NULL es «usá el del hotel»; no puede ser NOT NULL"


def test_la_propiedad_tiene_idioma_por_defecto():
    from app.models.hotel import Hotel
    col = Hotel.__table__.c["default_locale"]
    assert col.nullable is False
    assert col.default.arg == "es"
