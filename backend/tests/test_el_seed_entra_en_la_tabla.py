# -*- coding: utf-8 -*-
"""
LO QUE EL SEED SIEMBRA TIENE QUE CABER EN LA TABLA.

## Cómo se descubrió (2026-08-14)

Un cambio de mapeo se desplegó, Railway quedó verde, y **el mapeo no cambió**.
`seed_mapping` había reventado con:

    value too long for type character varying(500)

Treinta y tres reglas traían una `notes` de 631–650 caracteres y la columna
admite 500. Como el seed hace **un solo commit**, no entró **ninguna** — ni las
33 largas ni las otras 1.090.

Y no dio error visible, porque `app/seed.py` envuelve el seed del mapeo en un
`try/except` que imprime «seed de mapeo omitido» y sigue arrancando. Ese
`try/except` está bien —un seed roto no debería impedir que la API levante—,
pero significa que **el único aviso vive en los logs de Railway**.

Peor: la migración que acompañaba el cambio **sí** corrió (las migraciones no
están dentro del `try`), así que producción quedó **a medias**: los borrados
aplicados y las altas no. Esa vez no movió plata de casualidad —las reglas
borradas se heredaban del padre y aterrizaban en la misma línea—, pero es
exactamente la forma en que este sistema falla caro: **el total cuadra y nadie
se entera**.

## Qué cuida esta prueba

Que **cada campo de texto de cada fila** de `mapping_pl.json` entre en su
columna, medido contra el modelo — no contra un número escrito a mano acá, que
se quedaría viejo el día que alguien agrande la columna.

Es una prueba de segundos que sustituye a un deploy silenciosamente a medias.
"""
import json
import pathlib

import pytest

from app.models.mapping import AccountMapping, ReportLineConfig
from app.seed_mapping import ARCHIVO


def _limites(modelo) -> dict[str, int]:
    """Campo -> largo máximo, leído del modelo."""
    return {c.name: c.type.length for c in modelo.__table__.columns
            if getattr(c.type, "length", None)}


@pytest.fixture(scope="module")
def datos() -> dict:
    return json.loads(pathlib.Path(ARCHIVO).read_text(encoding="utf-8"))


@pytest.mark.parametrize("bloque,modelo", [
    ("account_mapping", AccountMapping),
    ("report_line_config", ReportLineConfig),
])
def test_ningun_campo_del_seed_desborda_su_columna(datos, bloque, modelo):
    limites = _limites(modelo)
    assert limites, f"{modelo.__name__} no declara ningun largo: la prueba no mide nada"

    desbordes = []
    for fila in datos[bloque]:
        for campo, valor in fila.items():
            tope = limites.get(campo)
            if tope and isinstance(valor, str) and len(valor) > tope:
                desbordes.append(
                    f"{bloque} {fila.get('dept_code', '')}/{fila.get('account_code', '')} "
                    f"campo `{campo}`: {len(valor)} caracteres, la columna admite {tope}")

    assert not desbordes, (
        "el seed va a reventar entero y el deploy va a quedar VERDE — un solo "
        f"campo largo tira las {len(datos[bloque])} filas del bloque:\n  "
        + "\n  ".join(desbordes[:20])
        + (f"\n  ... y {len(desbordes) - 20} mas" if len(desbordes) > 20 else ""))


# ─────────────────────────────────────────────────────────────────────────────
# LO MISMO PARA LAS SEMILLAS QUE SE MUDARON A `seed_data/<HOTEL_ID>/`
# (2026-08-16).
#
# `mapping_pl.json` no es el único archivo que termina adentro de una columna.
# Las cuatro listas que estaban escritas a mano —el catálogo de OPEX, los
# canales del mix, las tarifas del checkbook y las reasignaciones de salario—
# ahora son JSON, y tres de ellas escriben en tablas con `String(n)`:
#
#   opex_accounts.json          → OpexEntry.account_code / account_name
#   canales_mix.json            → ChannelMixEntry.channel
#   reasignaciones_salario.json → SalaryAllocationConfig.source_dept / position_name
#
# Un nombre de cuenta largo en el JSON no revienta el arranque —estas no las
# siembra `seed.py`— pero revienta el INSERT del endpoint que las usa, con la
# pantalla ya abierta y el usuario mirando. Es el mismo error de siempre, un
# paso más tarde.
#
# `driver_rates.json` no toca ninguna tabla: son números que la pantalla usa
# para calcular. Se le mide lo que sí puede romperse — que estén todos y que
# sean números.
# ─────────────────────────────────────────────────────────────────────────────
from app.models.channel_mix import ChannelMixEntry
from app.models.opex_entry import OpexEntry
from app.models.salary_allocation_config import SalaryAllocationConfig
from app.seed_data import semilla_cruda

#: archivo → lista → {campo del JSON: columna del modelo}
SEMILLAS_CON_TEXTO = [
    ("opex_accounts", "cuentas", OpexEntry,
     {"code": "account_code", "name": "account_name"}),
    ("reasignaciones_salario", "reasignaciones", SalaryAllocationConfig,
     {"name": "position_name", "source": "source_dept", "target": "source_dept",
      "legacy": "position_code"}),
]


@pytest.mark.parametrize("archivo,bloque,modelo,campos", SEMILLAS_CON_TEXTO,
                         ids=[s[0] for s in SEMILLAS_CON_TEXTO])
def test_ninguna_semilla_nueva_desborda_su_columna(archivo, bloque, modelo, campos):
    datos = semilla_cruda(archivo)
    assert datos, f"{archivo}.json no existe para esta propiedad: la prueba no mide nada"
    limites = _limites(modelo)
    desbordes = []
    for fila in datos[bloque]:
        for campo, columna in campos.items():
            tope = limites.get(columna)
            valor = fila.get(campo)
            assert tope, f"{modelo.__name__}.{columna} no declara largo: la prueba no mide nada"
            if isinstance(valor, str) and len(valor) > tope:
                desbordes.append(f"{archivo} `{campo}`={valor[:40]!r}: {len(valor)} "
                                 f"caracteres, {modelo.__name__}.{columna} admite {tope}")
    assert not desbordes, (
        "la pantalla va a reventar al guardar, con el usuario mirando:\n  "
        + "\n  ".join(desbordes))


def test_los_canales_del_mix_entran_en_su_columna():
    """El nombre del canal ES la llave: se guarda tal cual en `channel`."""
    datos = semilla_cruda("canales_mix")
    assert datos and datos["canales"], "canales_mix.json vacío: la prueba no mide nada"
    tope = _limites(ChannelMixEntry)["channel"]
    largos = [c for c in datos["canales"] if len(c) > tope]
    assert not largos, f"no entran en channel({tope}): {largos}"


def test_los_canales_del_mix_no_se_repiten():
    """Un duplicado corre las columnas de la grilla: el PUT escribe POR POSICION
    y el UNIQUE de la tabla se come la segunda. El total del mes sigue cuadrando."""
    canales = semilla_cruda("canales_mix")["canales"]
    assert len(canales) == len(set(canales)), f"canales repetidos: {canales}"


def test_las_tarifas_del_checkbook_estan_completas_y_son_numeros():
    """La pantalla multiplica por cada una. Una que falte da `undefined` y llena
    la fila de NaN; una que venga como texto la llena de basura silenciosa."""
    tarifas = semilla_cruda("driver_rates")["tarifas"]
    esperadas = {"food", "tours", "transport", "nights_per_stay", "bev_ratio",
                 "retail_pct", "innoceana_pct", "sust_rate", "sust_non_pay"}
    assert set(tarifas) == esperadas, (
        f"faltan {esperadas - set(tarifas)} · sobran {set(tarifas) - esperadas}")
    malas = {k: v for k, v in tarifas.items() if not isinstance(v, (int, float))}
    assert not malas, f"no son números: {malas}"
    assert tarifas["nights_per_stay"], "nights_per_stay en 0: los tours y el transporte dividen por él"


def test_las_reasignaciones_no_se_mandan_a_si_mismas():
    """Un renglón `source == target` mueve plata al mismo departamento del que
    salió: no cambia nada y esconde la reasignación que sí hacía falta."""
    filas = semilla_cruda("reasignaciones_salario")["reasignaciones"]
    assert filas, "reasignaciones_salario.json vacío: la prueba no mide nada"
    circulares = [f for f in filas if f["source"] == f["target"]]
    assert not circulares, f"se reasignan a sí mismas: {circulares}"


def test_el_catalogo_de_opex_no_repite_cuentas():
    """El endpoint crea un renglón por cuenta; un código repetido choca contra
    `uq_opex_entry` y voltea toda la siembra del departamento."""
    cuentas = semilla_cruda("opex_accounts")["cuentas"]
    codigos = [c["code"] for c in cuentas]
    assert len(codigos) == len(set(codigos)), (
        f"repetidos: {sorted({c for c in codigos if codigos.count(c) > 1})}")
