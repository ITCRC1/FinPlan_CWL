# -*- coding: utf-8 -*-
"""Toda tabla con columnas de mes se lee igual que las demas.

**El defecto (owner, 2026-08-14).** Bajar la plantilla de Detalle daba
`Internal Server Error`. En pantalla eso es todo lo que se ve: ni que tabla, ni
que version, ni por que.

La causa: el endpoint recorre las CUATRO tablas del GL en un solo bucle —

    for Model in (RevenueAccountEntry, CostEntry, OpexEntry, BelowGopAccountEntry):
        _add(e.dept_code, e.account_code, ..., e.get_month)

— asumiendo que todas responden `get_month`. Lo tenian `OpexEntry` y
`CostEntry`; `RevenueAccountEntry` y `BelowGopAccountEntry` no, aunque tienen las
mismas doce columnas `jan..dec`. Venia roto desde el 2026-08-07 (`d6e6bf6`).

**La propiedad, y no el caso:** si una tabla guarda los doce meses en columnas,
tiene que exponerlos con la misma interfaz que sus hermanas. Si no, el que las
recorre necesita un caso especial por cada una — y el dia que se agregue la
quinta tabla nadie se va a acordar.
"""
from decimal import Decimal

import pytest

MESES = ("jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec")


def _tablas_con_columnas_de_mes() -> list:
    """Los modelos que guardan los doce meses como columnas."""
    import app.models  # noqa: F401  — registra todos los modelos
    from app.db import Base

    fuera = []
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        cols = {c.key for c in mapper.columns}
        if all(m in cols for m in MESES):
            fuera.append(cls)
    return fuera


def test_hay_tablas_que_revisar():
    """Que la prueba mire algo de verdad y no pase en verde vacia."""
    assert len(_tablas_con_columnas_de_mes()) >= 4


@pytest.mark.parametrize("cls", _tablas_con_columnas_de_mes(),
                         ids=lambda c: c.__name__)
def test_expone_get_month(cls):
    assert hasattr(cls, "get_month"), (
        f"{cls.__name__} guarda los doce meses en columnas y no tiene "
        f"`get_month`. Cualquier bucle que la recorra junto a sus hermanas "
        f"revienta con AttributeError, y en pantalla eso es un 500 sin detalle.")


@pytest.mark.parametrize("cls", _tablas_con_columnas_de_mes(),
                         ids=lambda c: c.__name__)
def test_get_month_devuelve_el_mes_pedido(cls):
    """No alcanza con que exista: tiene que leer el mes correcto.

    Un `get_month` corrido en uno —empezando en `feb` para el mes 1— devolveria
    numeros perfectamente crebles del mes equivocado, y eso no lo delata nada.
    """
    fila = cls()
    for i, mes in enumerate(MESES, start=1):
        setattr(fila, mes, Decimal(str(i)))
    for i in range(1, 13):
        assert fila.get_month(i) == Decimal(str(i)), (
            f"{cls.__name__}.get_month({i}) no devolvio el mes {i}")


@pytest.mark.parametrize("cls", _tablas_con_columnas_de_mes(),
                         ids=lambda c: c.__name__)
def test_set_month_escribe_donde_get_month_lee(cls):
    if not hasattr(cls, "set_month"):
        pytest.skip(f"{cls.__name__} no expone set_month")
    fila = cls()
    for i in range(1, 13):
        fila.set_month(i, Decimal(str(i * 10)))
    for i in range(1, 13):
        assert fila.get_month(i) == Decimal(str(i * 10))
