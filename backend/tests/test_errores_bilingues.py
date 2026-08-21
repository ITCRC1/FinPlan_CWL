# -*- coding: utf-8 -*-
"""Los errores de la API se dicen en los dos idiomas, y nadie queda a medias.

**Qué protege.** Los 359 `raise HTTPException` del backend estaban a mano y ya
venían mezclados entre ellos: la misma validación existía como
«month debe estar entre 1 y 12», «month must be 1–12» y «month 1..12».

El modo de fallar de este trabajo es **silencioso**: una clave mal escrita no
rompe nada — devuelve la clave como si fuera el mensaje, y en pantalla se ve
un error raro pero plausible. Por eso el test mira el CÓDIGO, no solo el
catálogo.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

from app.errores import MENSAJES, ErrorApi, locale_de, manejador, texto

APP = pathlib.Path(__file__).resolve().parents[1] / "app"


def _claves_usadas() -> set[str]:
    """Toda clave literal que el código le pasa a `ErrorApi(...)`."""
    usadas = set()
    for p in APP.rglob("*.py"):
        try:
            arbol = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:                     # pragma: no cover
            continue
        for n in ast.walk(arbol):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "ErrorApi" and len(n.args) >= 2
                    and isinstance(n.args[1], ast.Constant)
                    and isinstance(n.args[1].value, str)):
                usadas.add(n.args[1].value)
    return usadas


def test_toda_clave_usada_existe_en_el_catalogo():
    """Una clave inventada NO revienta en producción: devuelve la clave como
    mensaje. Se ve mal pero funciona, así que solo se cacha acá."""
    faltan = sorted(_claves_usadas() - set(MENSAJES))
    assert not faltan, f"claves usadas que no están en MENSAJES: {faltan}"


def test_todo_mensaje_tiene_los_dos_idiomas():
    incompletos = sorted(k for k, v in MENSAJES.items()
                         if not v.get("es") or not v.get("en"))
    assert not incompletos, f"mensajes sin los dos idiomas: {incompletos}"


@pytest.mark.parametrize("clave", sorted(MENSAJES))
def test_los_parametros_coinciden_entre_idiomas(clave):
    """Si el español dice {escenario} y el inglés no, el inglés pierde el dato
    —o revienta al formatear. Es exactamente el error que no se ve al leer."""
    saca = lambda s: set(re.findall(r"\{(\w+)", s))
    assert saca(MENSAJES[clave]["es"]) == saca(MENSAJES[clave]["en"]), clave


def test_el_motor_no_se_entera_del_idioma():
    """Misma regla que `app/i18n.py`: el cálculo nunca sabe en qué idioma se va
    a mostrar. Si el motor empieza a importar esto, el engine deja de ser puro."""
    for p in (APP / "engine").rglob("*.py"):
        txt = p.read_text(encoding="utf-8")
        assert "app.errores" not in txt and "ErrorApi" not in txt, \
            f"{p.name} importa los errores de la API: el motor tiene que quedar puro"


def test_el_mensaje_cambia_de_idioma():
    assert texto("es", "escenario.no_encontrado") == "Escenario no encontrado"
    assert texto("en", "escenario.no_encontrado") == "Scenario not found"


def test_un_idioma_desconocido_cae_al_default():
    assert texto("fr", "escenario.no_encontrado") == texto("es", "escenario.no_encontrado")
    assert texto(None, "escenario.no_encontrado") == texto("es", "escenario.no_encontrado")


def test_los_parametros_se_rellenan():
    assert texto("en", "cuenta.no_encontrada", cuenta="7065") == "Account not found: 7065"


def test_una_clave_que_no_existe_no_revienta():
    """Un typo en el nombre no puede convertirse en un 500."""
    assert texto("es", "no.existe.esta.clave") == "no.existe.esta.clave"


def test_el_detail_por_defecto_sigue_siendo_texto():
    """`ErrorApi` hereda de `HTTPException`: si la respuesta NO pasa por el
    manejador, tiene que verse igual que antes de todo esto."""
    e = ErrorApi(404, "escenario.no_encontrado")
    assert e.status_code == 404
    assert e.detail == "Escenario no encontrado"


def test_los_datos_del_extra_viajan_sin_traducirse():
    e = ErrorApi(422, "escenario.no_encontrado", extra={"filas": [3, 7]})
    assert e.detail["filas"] == [3, 7]
    assert e.detail["mensaje"] == "Escenario no encontrado"


class _Req:
    """Lo mínimo de `Request` que mira `locale_de`: la cabecera y `?lang=`.

    ⚠️ `query_params` no es decorativo: las descargas van por `<a href>` y un
    href NO manda cabeceras, así que el idioma viaja por query. Si esta clase
    no lo tuviera, la prueba pasaría y el Excel saldría en el idioma equivocado.
    """

    def __init__(self, cabecera, lang=None):
        self.headers = {"accept-language": cabecera} if cabecera else {}
        self.query_params = {"lang": lang} if lang else {}


@pytest.mark.parametrize("cabecera,esperado", [
    ("en", "en"), ("es", "es"), ("en-US", "en"), ("ES-cr", "es"),
    ("fr", "es"), ("", "es"), (None, "es"),
])
def test_el_idioma_sale_de_la_cabecera(cabecera, esperado):
    assert locale_de(_Req(cabecera)) == esperado


# ─── Los nombres que ErrorApi ya usa ─────────────────────────────────────────

#: `ErrorApi(status_code, clave, *, extra=None, **params)`. Un mensaje cuyo
#: parámetro se llame igual que uno de estos revienta al construirse:
#: `ErrorApi(404, "x", clave=...)` → «got multiple values for argument 'clave'».
RESERVADOS = {"status_code", "clave", "extra", "self"}


@pytest.mark.parametrize("clave", sorted(MENSAJES))
def test_ningun_parametro_pisa_la_firma_de_ErrorApi(clave):
    """⚠️ Esto NO lo cacha ni el import, ni `py_compile`, ni la suite.

    Apareció al pasar los 359 `raise` al catálogo: una clave traía un parámetro
    llamado `clave`, y solo se vio al renderizar cada mensaje por el
    constructor DE VERDAD. El endpoint que la usaba no tenía prueba, así que
    habría reventado en producción la primera vez que alguien lo tocara.
    """
    for idioma in ("es", "en"):
        usados = set(re.findall(r"\{(\w+)", MENSAJES[clave][idioma]))
        choque = usados & RESERVADOS
        assert not choque, (
            f"[{idioma}] '{clave}' usa {sorted(choque)}, que es un argumento de "
            f"ErrorApi.__init__ — reventaría al construirse. Renombralo.")


@pytest.mark.parametrize("clave", sorted(MENSAJES))
def test_todo_mensaje_se_puede_construir_de_verdad(clave):
    """Cada clave, pasada por el constructor real y en los dos idiomas.

    Renderizar con `texto()` no alcanza: `ErrorApi` es quien recibe los
    parámetros como kwargs, y es ahí donde chocan con su propia firma."""
    # Un valor que sirva tanto para `{x}` como para `{x:.2%}` o `{x:,.2f}`:
    # con un string, un mensaje con formato numérico revienta y parecería un
    # defecto del mensaje cuando el defecto sería de esta prueba.
    e = None
    for valor in (1.0, "X"):
        params = {p: valor for p in re.findall(r"\{(\w+)", MENSAJES[clave]["es"])}
        try:
            e = ErrorApi(422, clave, **params)
            break
        except ValueError:
            continue
    assert e is not None, f"'{clave}' no se pudo construir con ningún valor"
    for idioma in ("es", "en"):
        assert isinstance(e._detalle(idioma), str) and e._detalle(idioma)


# ─── Decidir por la CLAVE, nunca por la prosa ───────────────────────────────

def test_la_respuesta_lleva_la_clave():
    """El frontend a veces necesita saber QUÉ error fue, no solo mostrarlo.

    Si esa decisión se toma mirando el texto, deja de funcionar el día que el
    texto cambia de idioma — y no falla: cambia de comportamiento en silencio."""
    import asyncio

    class _Req:
        headers = {"accept-language": "en"}
        query_params: dict = {}

    r = asyncio.run(manejador(_Req(), ErrorApi(409, "escenario.no_encontrado")))
    import json as _json
    cuerpo = _json.loads(bytes(r.body).decode("utf-8"))
    assert cuerpo["clave"] == "escenario.no_encontrado"
    assert cuerpo["detail"] == "Scenario not found", "el texto sigue traducido"


def test_ninguna_pantalla_decide_mirando_el_texto_del_error():
    """⚠️ Encontrado el 2026-08-19, y lo había causado el pase bilingüe.

    `master-data/provisioning` decidía si mostrar una CONFIRMACIÓN o un error
    duro con `detalle.includes("datos cargados")`. Funcionó mientras el backend
    hablaba un solo idioma. Con los mensajes bilingües, en inglés el mensaje
    dice «There is data loaded» — la confirmación no se abría nunca y **apagar
    un departamento con datos quedaba bloqueado**, sin forma de seguir.

    No hubo error ni pantalla rota: hubo un camino que dejó de existir.
    """
    import re

    from tests._rutas import FRONT

    sospechosas = []
    for p in list((FRONT / "app").rglob("*.tsx")) + list((FRONT / "components").rglob("*.tsx")):
        for i, linea in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
            if "//" in linea.split("includes")[0]:
                continue                            # es un comentario
            m = re.search(r'\b(detalle|detail|msg|mensaje|err\w*)\b[^;\n]*\.includes\(\s*"([^"]+)"', linea)
            # Una CLAVE (`tema.caso`) es contrato y no se traduce; la prosa sí.
            if m and not re.fullmatch(r"[a-z_]+\.[a-z_.]+", m.group(2)):
                sospechosas.append(f"{p.name}:{i} → {m.group(2)!r}")
    assert not sospechosas, (
        "estas pantallas deciden mirando el TEXTO del error, que cambia de "
        f"idioma; tienen que mirar la clave: {sospechosas}")


def test_la_descarga_lleva_el_idioma_por_query():
    """⚠️ Un `<a href>` no manda cabeceras. El Excel salía en el idioma del
    NAVEGADOR y no en el que el usuario eligió — y nadie entiende por qué.
    `dlUrl()` en `lib/api.ts` pone `?lang=`; acá se comprueba que gane."""
    assert locale_de(_Req("es", lang="en")) == "en", "la query tiene que ganar"
    assert locale_de(_Req(None, lang="en")) == "en"
    assert locale_de(_Req("en")) == "en", "sin query, manda la cabecera"
