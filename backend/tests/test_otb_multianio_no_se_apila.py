# -*- coding: utf-8 -*-
"""Un XML multi-año no tiene UN total: tiene uno por año.

**El defecto (owner, 2026-08-18).** «Hay algo incorrecto acá, no sé de dónde
sale total revenue 6315043, ninguno de los escenarios tiene ese saldo.»

Tenía razón en las dos mitades: el número existía y no era de ningún escenario.
El XML del owner trae **1.826 días = 5 años** en el mismo archivo, y el import
devolvía `full_year_revenue` = la suma de TODOS los días. Los tres años con dato
eran 2026 $4.513.865 + 2027 $1.772.782 + 2028 $28.396 = **$6.315.043,09**, al
centavo. Un "FY revenue" de tres años a la vez.

**La medición que lo cerró** (producción, corte 34):

    ACT26  año 2026: $6.315.043  8.130 noches  enero 1.353 de 1.023 = 132,3%
    BUD27  año 2026: $4.513.865  4.621 noches  enero   688 de 1.023 =  67,3%
    BUD27  año 2027: $1.772.782  2.083 noches
    BUD27  año 2028: $   28.396  1.426 noches

El enero bueno —688— es **idéntico** al de los cortes 24 al 28, que se subieron
antes. O sea: el dato por año estaba bien; lo que estaba mal era sumarlos.

⚠️ **Y mi primer diagnóstico fue equivocado.** Dije que el importador contaba
cada día dos veces (History + Forecast solapados) y escribí el arreglo sobre esa
teoría. El dato de arriba lo desmiente: 4.621 noches en 2026 son 38% de
ocupación, perfectamente sanas. El candado de `test_otb_no_cuenta_dos_veces`
sigue valiendo por su cuenta, pero no era esto.
"""
import inspect

from app.api import revenue_api


def test_el_import_ya_no_devuelve_un_total_entre_anios():
    """`full_year_revenue` era la suma de 5 años. No debe volver."""
    src = inspect.getsource(revenue_api.import_otb_xml)
    # La LLAVE del diccionario, no la palabra: el comentario que explica el bug
    # la nombra a propósito y tiene que poder seguir nombrándola.
    assert '"full_year_revenue"' not in src, (
        "un archivo multi-año no tiene UN total de año; devolvé `por_anio`")


def test_el_import_desglosa_por_anio():
    src = inspect.getsource(revenue_api.import_otb_xml)
    assert '"por_anio"' in src
    for campo in ('"year"', '"revenue"', '"noches"', '"meses"'):
        assert campo in src, f"falta {campo} en el desglose por año"


def test_el_reporte_mensual_filtra_por_anio():
    """Sin esto, los 12 meses mezclan enero-2026 + enero-2027 + enero-2028."""
    src = inspect.getsource(revenue_api.get_on_the_books)
    assert "OnTheBooksEntry.year == anio" in src


def test_el_heatmap_diario_tambien_filtra_por_anio():
    src = inspect.getsource(revenue_api.get_daily_occ)
    assert "anio" in src, "el heatmap tiene que mirar el mismo año que el reporte"
