"""Un archivo bajado de OTRO hotel del grupo no se puede subir.

El 2026-11-12 se subió al Budget 2027 Working de CWL un OPEX bajado de FinPlan
Amarena: los dos se llaman `OPEX_2027_Working (N).xlsx`, el import no miraba
el título, y cinco departamentos quedaron con los números de otro hotel sin un
solo aviso. Estas pruebas amarran que el título «FinPlan {hotel} — …» manda.
"""
import io

import pytest
from openpyxl import Workbook

from app import hotel_actual
from app.errores import ErrorApi
from app.export.costs_excel import import_costs_from_excel
from app.export.excel_base import hotel_del_archivo
from app.export.nonop_excel import import_nonop_from_excel
from app.export.opex_excel import import_opex_from_excel
from app.export.payroll_excel import import_payroll_from_excel


def _libro(titulo):
    wb = Workbook()
    ws = wb.active
    ws.title = "0110 Rooms  Habitaciones"
    if titulo is not None:
        ws.cell(1, 1, titulo)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def en_cwl(monkeypatch):
    monkeypatch.setattr(hotel_actual, "HOTEL_ID", "CWL")


@pytest.mark.parametrize("importar", [import_opex_from_excel, import_costs_from_excel,
                                      import_nonop_from_excel, import_payroll_from_excel])
def test_un_archivo_de_otro_hotel_se_rechaza(en_cwl, importar):
    with pytest.raises(ErrorApi) as e:
        importar(_libro("FinPlan AMA — OPEX 2027  ·  Budget 2027 · Working"))
    assert e.value.status_code == 422
    assert e.value.clave == "archivo.de_otro_hotel"
    assert e.value.params == {"archivo": "AMA", "hotel": "CWL"}


def test_el_del_mismo_hotel_y_el_sin_titulo_entran(en_cwl):
    # No revientan por el hotel: lo que devuelvan depende de las filas.
    import_opex_from_excel(_libro("FinPlan CWL — OPEX 2027  ·  Budget 2027 · Working"))
    import_opex_from_excel(_libro(None))
    import_opex_from_excel(_libro("Una hoja armada a mano"))


def test_el_titulo_que_escribe_el_export_se_reconoce():
    """El patrón tiene que leer lo que de verdad escriben los cuatro exports."""
    from openpyxl import load_workbook
    for titulo in ("FinPlan CWL — OPEX 2027  ·  Budget 2027 · Working",
                   "FinPlan CWL — Cost of Sales (Clase 5) | Budget 2027",
                   "FinPlan CWL — Non-Operating Expenses | Budget 2027",
                   "FinPlan CWL — Planilla de Personal | Budget 2027"):
        assert hotel_del_archivo(load_workbook(io.BytesIO(_libro(titulo)))) == "CWL"

