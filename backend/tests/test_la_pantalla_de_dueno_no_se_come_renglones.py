# -*- coding: utf-8 -*-
"""La pantalla de Gastos del Propietario lista TODO lo que su guardado borra.

## De dónde sale (2026-11-09)

Owner: *«dónde está Rent y Insurance en Budget 2027»*. Estaban en cero — y no
porque nadie los hubiera cargado: **la pantalla no tenía dónde**. El P&L dibuja
`RENT` y `PROPERTY_INSURANCE` desde siempre, pero `SECTIONS` sólo listaba
Other/No-deducibles, Financieros y Depreciación.

Medido: el Budget Working 2027 tenía $0 de renta y $0 de seguro, mientras el
Forecast 2026 traía **$20.779,81** y **$56.851,81** del mayor.

## El agujero caro no es el que se ve

Un renglón que falta se nota: sale en cero. Lo que no se nota es que el guardado
de esta pantalla usa `bulkReplaceNonOp`, que **borra TODO el below-GOP del
escenario** y vuelve a insertar únicamente las líneas que la pantalla conoce.

Así que con la renta y el seguro cargados por cualquier otra vía —el importador,
un script, la pantalla de otra propiedad— **el primer Guardar de acá se los
llevaba por delante**. Sin error, sin aviso, y con el P&L cuadrando consigo
mismo después.

Esta prueba exige que las dos listas coincidan: todo renglón que el guardado
pueda borrar tiene que estar dibujado. Mientras el guardado sea `bulk`, agregar
un renglón al P&L sin agregarlo acá es programar su borrado.
"""
import re

import pytest

from ._rutas import FRONT, sin_comentarios

PANTALLA = "app/nonop/checkbook/page.tsx"

#: Los renglones below-GOP que se CARGAN a mano (mini checkbooks). Los otros
#: —honorarios, reserva de capital, impuesto— son fórmulas y viven en otra
#: pantalla, así que no se dibujan acá a propósito.
A_MANO = {
    "RENT": "8000",
    "PROPERTY_INSURANCE": "8015",
    "OTHER_EXPENSES": "8025",
    "BANK_INTEREST": "8030",
    "LEASINGS_RENTS": "8035",
    "FINANCIAL_LOSSES": "8045",
    "DEPRECIATION": "8040",
}


def _src() -> str:
    return sin_comentarios((FRONT / PANTALLA).read_text(encoding="utf-8"))


def _declarados() -> set[str]:
    bloque = _src().split("const SECTIONS")[1].split("type Row")[0]
    return set(re.findall(r'code:\s*"([A-Z_]+)"', bloque))


@pytest.mark.parametrize("code", sorted(A_MANO))
def test_la_pantalla_dibuja_el_renglon(code):
    assert code in _declarados(), (
        f"{code} no está en SECTIONS: no hay dónde cargarlo, y el Guardar de "
        f"esta pantalla lo BORRA si alguien lo cargó por otra vía")


@pytest.mark.parametrize("code,cuenta", sorted(A_MANO.items()))
def test_cada_renglon_lleva_su_cuenta_del_mayor(code, cuenta):
    """Sin la cuenta, la fila queda sin referencia contra el mayor y no se puede
    cotejar con Integrity."""
    bloque = _src().split("const SECTIONS")[1].split("type Row")[0]
    m = re.search(rf'code:\s*"{code}".*?account_code:\s*"(\d+)"', bloque, re.S)
    assert m, f"{code} no declara su cuenta del mayor"
    assert m.group(1) == cuenta, (
        f"{code} apunta a la cuenta {m.group(1)} y le corresponde la {cuenta}")


def test_el_guardado_sigue_siendo_el_que_borra_todo():
    """⚠️ Si esto se pone rojo, la razón de la prueba de arriba cambió.

    Mientras el guardado sea `bulkReplaceNonOp` —que borra todo el below-GOP—
    la lista de la pantalla TIENE que estar completa. El día que se cambie por
    `replaceNonOpLines` (que borra sólo lo que nombra, y ya existe en el
    backend), el riesgo desaparece y esta prueba puede aflojarse."""
    src = _src()
    assert "bulkReplaceNonOp(scenarioId" in src, (
        "cambió el guardado: revisar si la lista de SECTIONS todavía tiene que "
        "estar completa, y actualizar la explicación de este archivo")


def test_los_renglones_de_formula_NO_se_dibujan_aca():
    """Honorarios, reserva de capital e impuesto son % y se editan en su propia
    pantalla. Dibujarlos acá como casillas invitaría a escribir un monto que el
    recálculo pisa en silencio."""
    declarados = _declarados()
    for code in ("MGMT_FEE_3", "MGMT_FEE_5_ROYALTIES", "CAPITAL_RESERVE",
                 "INCOME_TAXES"):
        assert code not in declarados, (
            f"{code} es una fórmula: no va como casilla en esta pantalla")
