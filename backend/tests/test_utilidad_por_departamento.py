# -*- coding: utf-8 -*-
"""La utilidad de un departamento se calcula con SUS propios ingresos y gastos.

**Cómo apareció (2026-08-14).** Cuadrando el Actual 2024, hoja Resumen contra
hoja Detalle, apareció una línea imposible en el lado del detalle:

    REV_TIENDA      0.00        REV_RETAIL     9,342.00
    OPEX_TIENDA     0.00        OPEX_RETAIL    7,006.50
    PROFIT_TIENDA   2,335.50 ←  igual  →       PROFIT_RETAIL  2,335.50

Utilidad sin ingreso y sin gasto. `PROFIT_TIENDA` tenía como fórmula
`REV_RETAIL - OPEX_RETAIL`: un copy-paste de cuando se separó la Tienda del Gift
Shop. Las reglas de cuenta estaban bien —`0151` a TIENDA y `0165` a RETAIL— y las
líneas de ingreso y gasto salían bien separadas. Solo la de utilidad mentía.

**Por qué importa más de lo que parece:** esa línea entra en el total de utilidad
departamental, así que inflaba el resultado del detalle en el monto del Gift
Shop, todos los años. Y el error se tapaba solo: como duplicaba un número que ya
existía, el orden de magnitud siempre parecía razonable.

**Dónde se arregla:** en `seed_data/mapping_pl.json`. El seed corre en cada
deploy y re-afirma `report_line_config`, así que una migración que tocara la
tabla se revertiría sola.
"""
import io
import json
import pathlib
import re

SEED = pathlib.Path(__file__).resolve().parents[1] / "app" / "seed_data" / "mapping_pl.json"

# Grupos que solo tienen ingreso: su utilidad ES el ingreso, sin término de
# gasto. No es un descuido de la fórmula, es cómo está definido el negocio.
# Departamentos cuya utilidad es SOLO su ingreso, sin restar gasto. No es un
# olvido: su costo vive en overhead y ya se resta en `TOTAL_OVERHEAD_EXPENSES`.
# Restarlo tambien aca lo contaria dos veces y bajaria el GOP por su monto.
#
# CLARO_HUERTA se sumo el 2026-08-14, cuando su ingreso salio de la linea de
# gasto donde estaba metido (ver `test_la_clase_manda.py`).
SOLO_INGRESO = {"SUSTAINABILITY", "AREC", "CLARO_HUERTA"}

# La línea de gasto de Misceláneos se llama distinto que su grupo. Es la única
# excepción de nombre y queda anotada acá para que no se vuelva costumbre.
ALIAS_OPEX = {"MISC_OTHER": "MISCELLANEOUS"}


def _lineas():
    return json.loads(SEED.read_text(encoding="utf-8"))["report_line_config"]


def test_ninguna_utilidad_usa_las_cuentas_de_otro_departamento():
    """La regla que faltaba. `PROFIT_TIENDA` restaba el Gift Shop entero."""
    culpables = []
    for r in _lineas():
        lc = r.get("line_code", "")
        if not lc.startswith("PROFIT_"):
            continue
        suf = lc[len("PROFIT_"):]
        # Un departamento puede tener VARIAS líneas de ingreso y de costo desde
        # que se partieron Rooms y A&B y el costo de ventas salió a su propia
        # línea (owner, 2026-08-14): `REV_ROOMS + REV_ROOMS_OTHER`,
        # `REV_FB + REV_FB_BEV + REV_FB_MISC`, `COS_FB_FOOD`… Son del MISMO
        # departamento, así que valen.
        #
        # Lo que la regla sigue prohibiendo —y es lo único que importaba— es que
        # `PROFIT_TIENDA` reste el gasto del Gift Shop, que fue el bug original.
        raices = {suf, ALIAS_OPEX.get(suf, suf)}

        def _propia(tok: str) -> bool:
            cuerpo = tok.split("_", 1)[1]
            return any(cuerpo == raiz or cuerpo.startswith(raiz + "_")
                       for raiz in raices)

        formula = r.get("calculation_logic") or ""
        # Se miran también las líneas de costo: si una utilidad restara el costo
        # de otro departamento sería el mismo error, y antes ni se revisaba.
        for token in re.findall(r"\b(?:REV|OPEX|COS|COH)_[A-Z_0-9]+\b", formula):
            if not _propia(token):
                culpables.append(f"{lc}: usa «{token}» — «{formula}»")
    assert not culpables, (
        "Una utilidad departamental calculada con las cuentas de OTRO "
        "departamento. Da un numero plausible y por eso no se nota:\n  "
        + "\n  ".join(culpables)
    )


def test_cada_utilidad_parte_de_su_propio_ingreso():
    faltan = []
    for r in _lineas():
        lc = r.get("line_code", "")
        if not lc.startswith("PROFIT_"):
            continue
        suf = lc[len("PROFIT_"):]
        if f"REV_{suf}" not in (r.get("calculation_logic") or ""):
            faltan.append(lc)
    assert not faltan, f"utilidades que no parten de su ingreso: {faltan}"


def test_solo_los_grupos_sin_costo_no_restan_gasto():
    """Que una utilidad no reste gasto tiene que ser una decisión, no un olvido."""
    sin_gasto = []
    for r in _lineas():
        lc = r.get("line_code", "")
        if not lc.startswith("PROFIT_"):
            continue
        suf = lc[len("PROFIT_"):]
        if "OPEX_" not in (r.get("calculation_logic") or ""):
            sin_gasto.append(suf)
    assert set(sin_gasto) == SOLO_INGRESO, (
        f"cambió qué departamentos no tienen costo: {sorted(sin_gasto)} "
        f"(esperado {sorted(SOLO_INGRESO)}). Si es a propósito, actualizá "
        "SOLO_INGRESO; si no, a alguien se le perdió el término de gasto."
    )


def test_la_tienda_quedo_con_sus_propias_cuentas():
    """El caso concreto, para que el arreglo no se deshaga sin que nadie note."""
    por = {r["line_code"]: r.get("calculation_logic") for r in _lineas()}
    # El costo de ventas salió a su propia línea (owner, 2026-08-14), así que la
    # fórmula ahora resta también `COS_X`. Lo que esta prueba cuida es que cada
    # tienda use LO SUYO: se compara el conjunto de términos, no el texto, para
    # que no vuelva a fallar por un cambio de forma que no cambia el resultado.
    assert set(por["PROFIT_TIENDA"].split()) >= {"REV_TIENDA", "OPEX_TIENDA", "COS_TIENDA"}
    assert "RETAIL" not in por["PROFIT_TIENDA"]
    assert set(por["PROFIT_RETAIL"].split()) >= {"REV_RETAIL", "OPEX_RETAIL", "COS_RETAIL"}
    assert "TIENDA" not in por["PROFIT_RETAIL"]


def test_el_arreglo_va_en_el_seed_y_no_en_una_migracion():
    """`python -m app.seed` corre en CADA deploy y re-afirma report_line_config:
    una migración que tocara la tabla se revertiría sola, y el total seguiría
    cuadrando, así que nadie se enteraría."""
    seed = (pathlib.Path(__file__).resolve().parents[1] / "app" / "seed_mapping.py")
    assert seed.exists()
    txt = io.open(seed, encoding="utf-8").read()
    assert "mapping_pl.json" in txt, (
        "si el seed dejara de leer el JSON, este arreglo dejaria de aplicarse"
    )
