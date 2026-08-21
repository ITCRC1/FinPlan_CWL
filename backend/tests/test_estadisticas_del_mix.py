# -*- coding: utf-8 -*-
"""La 9000 y la 9001 se llenan solas del Channel Mix.

**El pedido (owner, 2026-08-18).** «Que las clase 9 se llenen solas del mix.»

La **9000** son noches por segmento de mercado y la **9001** pax por segmento —
exactamente lo que `channel_mix_detail` guarda por market code, porque el
segmento ES el market code de Opera. Cargarlas a mano teniendo el dato al lado
es copiar números de una tabla a otra, y cada copia es una oportunidad de que
difieran.

⚠️ **Las dos perdieron la dimensión `ROOMTYPE`.** Estaban definidas como
`["SEGMENT", "ROOMTYPE"]`, pero su fuente —el `res_statistics1` de Opera abierto
por market code— **no trae tipo de habitación**: la cuenta prometía un desglose
que el dato no tiene. Las opciones eran dejarlas vacías para siempre o llenarlas
con un tipo de habitación inventado, y la segunda es la peligrosa: el total
cuadra y el desglose miente. Si algún día aparece un reporte que cruce las dos
dimensiones, se agregan cuentas nuevas y estas no se tocan.

⚠️ **Lo cargado a mano MANDA sobre lo derivado.** Es la regla de la casa: si
alguien corrigió un mes en el archivo, el mix no se lo pisa.
"""
import inspect
import json

import pytest

from app.api import estadisticas_api


def _catalogo() -> dict:
    with open("app/seed_data/stats_catalog.json", encoding="utf-8") as fh:
        return {c["code"]: c for c in json.load(fh)["cuentas"]}


@pytest.mark.parametrize("code", ["9000", "9001"])
def test_la_cuenta_se_abre_SOLO_por_segmento(code):
    """Su fuente no tiene tipo de habitación: prometerlo sería mentir."""
    c = _catalogo()[code]
    assert c["dims"] == ["SEGMENT"], (
        f"{code} volvió a abrirse por {c['dims']}. El res_statistics1 de Opera "
        f"no trae tipo de habitación — la cuenta quedaría vacía para siempre o "
        f"llena de un ROOMTYPE inventado.")


def test_las_dos_cuentas_estan_declaradas_como_derivadas():
    assert estadisticas_api.DERIVADAS_DEL_MIX == {"9000": "rooms", "9001": "pax"}


def test_la_9000_toma_NOCHES_y_la_9001_PAX():
    """Cruzarlas daría números plausibles y equivocados: pax siempre es mayor
    que noches, así que nadie notaría el intercambio mirando por encima."""
    assert estadisticas_api.DERIVADAS_DEL_MIX["9000"] == "rooms"
    assert estadisticas_api.DERIVADAS_DEL_MIX["9001"] == "pax"


def test_la_llave_derivada_calza_con_la_de_la_grilla():
    """La grilla arma `(cuenta, depto, posición, tipo_hab, dim_type, dim_code)`.

    Si la derivación usara otra llave, los valores existirían y la pantalla los
    mostraría vacíos — el defecto más caro de encontrar, porque nada falla.
    """
    src = inspect.getsource(estadisticas_api._del_channel_mix)
    assert '(cuenta, "", "", "", "SEGMENT", f.market_code)' in src


def test_lo_cargado_a_mano_no_se_pisa():
    """`setdefault`, no asignación: la derivación llena lo vacío y no discute
    lo que alguien ya decidió."""
    src = inspect.getsource(estadisticas_api._cargados)
    assert "destino.setdefault(mes, v)" in src, (
        "la derivación tiene que llenar lo vacío, no sobrescribir lo cargado")


def test_el_motor_ya_sabia_generar_una_cuenta_de_segmento_sin_roomtype():
    """No hubo que tocar el motor: la rama ya existía. Esta prueba lo fija —
    si desapareciera, la 9000 dejaría de generar filas y nadie lo notaría hasta
    abrir la pantalla."""
    from app.engine import estadisticas_grilla

    src = inspect.getsource(estadisticas_grilla.construir)
    assert 'if "ROOMTYPE" in dims:' in src
    assert 'dim_type="SEGMENT"' in src


# ── Las otras tres derivaciones ──────────────────────────────────────────────
#
# «Y los FTEs por posición, kilos, cover, treatments, persons, pax, room nights»
# (owner, 18-ago-2026). De esa lista, tres más se podían derivar de datos que el
# sistema YA tiene; kilos, covers y treatments no tienen fuente todavía y se
# siguen cargando a mano — inventarlas sería peor que dejarlas vacías.

def test_las_cuentas_por_canal_y_por_pais_estan_declaradas():
    assert estadisticas_api.DERIVADAS_POR_CANAL == {"9070": "rooms", "9071": "pax"}
    assert estadisticas_api.DERIVADAS_POR_PAIS == {"9080": "rooms", "9081": "pax"}


def test_las_cuatro_fuentes_se_leen():
    src = inspect.getsource(estadisticas_api._del_channel_mix)
    for tabla in ("ChannelMixDetail", "ChannelMixEntry", "CountryMixEntry", "PayrollPosition"):
        assert tabla in src, f"falta la fuente {tabla}"


def test_el_FTE_se_SUMA_por_posicion():
    """⚠️ Una misma posición puede tener VARIAS personas —hay tres «AGENTE DE
    RECEPCION 501» en el mismo departamento— y la grilla tiene UNA fila por
    posición. Quedarse con la última daría FTE 1 donde hay 3."""
    src = inspect.getsource(estadisticas_api._del_channel_mix)
    assert "sumar(k, i, v)" in src
    assert 'k = ("9901"' in src


def test_una_posicion_sin_codigo_no_se_deriva():
    """Sin código no hay forma de ubicarla en la grilla: sumarla a otra fila
    sería peor que dejarla afuera."""
    src = inspect.getsource(estadisticas_api._del_channel_mix)
    assert "if not cod:" in src


def test_COUNTRY_ya_no_es_una_dimension_sin_definir():
    """El Country Mix ya tiene países cargados: la lista existe."""
    from app.engine import estadisticas_grilla

    assert "COUNTRY" not in estadisticas_grilla.DIMS_SIN_DEFINIR


def test_los_paises_salen_del_country_mix_del_escenario():
    """No de un catálogo cerrado: el owner define su lista al cargar, y
    «Others» es una fila legítima de su mix, no un descarte."""
    from app.engine import estadisticas_grilla

    src = inspect.getsource(estadisticas_grilla._paises)
    assert "CountryMixEntry" in src
    assert "scenario_id" in src, "los países son POR ESCENARIO, no globales"


def test_sin_paises_cargados_no_se_generan_filas():
    """Pedir un país que nadie cargó es pedir que alguien lo invente."""
    from app.engine import estadisticas_grilla

    src = inspect.getsource(estadisticas_grilla.construir)
    assert 'for pais in paises:' in src


@pytest.mark.parametrize("code", ["9700", "9110", "9201"])
def test_kilos_covers_y_treatments_NO_se_derivan(code):
    """No tienen fuente. Derivarlas sería inventar el número — y el total
    cuadraría igual, que es la forma de fallar que no avisa."""
    derivadas = (set(estadisticas_api.DERIVADAS_DEL_MIX)
                 | set(estadisticas_api.DERIVADAS_POR_CANAL)
                 | set(estadisticas_api.DERIVADAS_POR_PAIS) | {"9901"})
    assert code not in derivadas
