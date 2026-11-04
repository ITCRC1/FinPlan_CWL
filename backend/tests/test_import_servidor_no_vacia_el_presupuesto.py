# -*- coding: utf-8 -*-
"""«Importar servidor» no puede dejar un escenario en cero.

**Lo que pasó (2026-11-03, Amarena · Budget Working 2027).** El endpoint
borraba el OPEX del escenario y DESPUÉS leía los checkbooks del disco del
servidor. Ese disco es el de la máquina vieja de CWL (`DATA_DIR`, por defecto
`C:/FinPlan_CWL`) y en producción no existe: el importador no encontró un solo
archivo y devolvió cero líneas.

El DELETE ya había corrido. 166 líneas y $930.000,09 —el presupuesto que el
contralor estaba revisando con la auditora— desaparecieron con un clic. En
pantalla salió «✓ Importado: 0 líneas», en verde.

**La propiedad, y no el caso:** una importación que no trae nada no puede
borrar lo que había. Leer primero y reemplazar después no es un detalle de
orden — es la diferencia entre un error y una pérdida de datos.
"""
import pytest

from app.api import opex_api
from app.errores import ErrorApi


class _Escenario:
    id = "esc-1"
    hotel_id = "AMA"

    def assert_editable(self):
        return None


class _Db:
    """Anota si alguien intentó borrar antes de tener con qué reemplazar."""

    def __init__(self, lineas_existentes=166):
        self.borro = False
        self.agrego = 0
        self.commits = 0
        self.lineas = lineas_existentes

    async def execute(self, stmt):
        if stmt.__class__.__name__ == "Delete":
            self.borro = True
            return None
        return _Scalar(self.lineas)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    def add(self, _obj):
        self.agrego += 1


class _Scalar:
    def __init__(self, v):
        self._v = v

    def scalar_one(self):
        return self._v


@pytest.fixture
def parcheado(monkeypatch):
    async def _esc(_sid, _db):
        return _Escenario()
    monkeypatch.setattr(opex_api, "_get_scenario_or_404", _esc)
    return monkeypatch


@pytest.mark.asyncio
async def test_sin_archivos_no_borra_nada(parcheado):
    """El caso exacto del accidente: la carpeta del servidor no existe."""
    parcheado.setattr(opex_api, "import_opex_for_scenario",
                      lambda *a, **k: [])
    db = _Db(lineas_existentes=166)
    with pytest.raises(ErrorApi) as e:
        await opex_api.import_all_opex("esc-1", db=db)
    assert e.value.status_code == 422
    assert not db.borro, (
        "borró el OPEX del escenario sin tener una sola línea para reemplazarlo: "
        "es exactamente lo que vació el Budget Working 2027 de Amarena")
    assert db.commits == 0, "no puede confirmar nada: no hizo nada"


@pytest.mark.asyncio
async def test_con_archivos_si_reemplaza(parcheado):
    """Cuando SÍ hay archivos el botón sigue sirviendo, igual que siempre."""
    parcheado.setattr(opex_api, "import_opex_for_scenario",
                      lambda *a, **k: [object(), object(), object()])
    db = _Db()
    r = await opex_api.import_all_opex("esc-1", db=db)
    assert db.borro, "para reemplazar hay que borrar lo viejo"
    assert db.agrego == 3 and r["imported"] == 3
    assert db.commits == 1


@pytest.mark.asyncio
async def test_el_error_dice_cuantas_lineas_se_salvaron(parcheado):
    """El mensaje tiene que decir que el escenario quedó INTACTO, con su número.
    «No se pudo importar» a secas deja al usuario sin saber si perdió algo."""
    parcheado.setattr(opex_api, "import_opex_for_scenario", lambda *a, **k: [])
    db = _Db(lineas_existentes=166)
    with pytest.raises(ErrorApi) as e:
        await opex_api.import_all_opex("esc-1", db=db)
    assert e.value.params.get("lineas") == 166
    assert "166" in str(e.value.detail), e.value.detail
