# -*- coding: utf-8 -*-
"""
LA MONEDA VIAJA EN EL EXCEL, DE IDA Y DE VUELTA.

Sin esto, bajar el Excel y volver a subirlo BORRA la marca de colones: la linea
vuelve a dolares y el presupuesto queda mal sin que nadie lo note. Y peor: si el
Excel llevara los DOLARES de una linea en colones, al reimportarla esos dolares
se tomarian como colones y el monto se dividiria por el tipo de cambio.
"""
from decimal import Decimal

from app.export.costs_excel import (
    COL_MONEDA as COL_MONEDA_COSTOS, export_costs_to_excel, import_costs_from_excel,
)
from app.export.opex_excel import (
    COL_MONEDA as COL_MONEDA_OPEX, export_opex_to_excel, import_opex_from_excel,
)

MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]


def test_la_columna_de_moneda_va_al_final():
    """En medio correria las columnas que los importadores asumen por posicion."""
    assert COL_MONEDA_COSTOS == 17
    assert COL_MONEDA_OPEX == 17


def _fila_costos(moneda, usd=0, crc=0):
    d = {"account_code": "5700", "account_name": "Cafetería",
         "driver_type": "MANUAL", "currency": moneda}
    for m in MESES:
        d[m] = usd
        d[f"crc_{m}"] = crc
    return d


def test_costos_ida_y_vuelta_conserva_los_colones():
    xlsx = export_costs_to_excel(
        {"0220": [_fila_costos("CRC", usd=9434, crc=5000000)]}, "CWL", 2027)
    filas = import_costs_from_excel(xlsx)
    fila = next(f for f in filas if f["account_code"] == "5700")
    assert fila["currency"] == "CRC"
    # los COLONES son los que vuelven, y a la columna de colones
    assert fila["crc_jan"] == Decimal("5000000")
    assert "jan" not in fila or fila.get("jan", Decimal("0")) == Decimal("0")


def test_costos_una_linea_en_dolares_sigue_en_dolares():
    xlsx = export_costs_to_excel(
        {"0110": [_fila_costos("USD", usd=1500)]}, "CWL", 2027)
    filas = import_costs_from_excel(xlsx)
    fila = next(f for f in filas if f["account_code"] == "5700")
    assert fila["currency"] == "USD"
    assert fila["jan"] == Decimal("1500")


def _fila_opex(moneda, usd=0, crc=0):
    d = {"account_code": "7065", "account_name": "Cleaning",
         "detail_desc": "detalle", "currency": moneda}
    for m in MESES:
        d[m] = usd
        d[f"crc_{m}"] = crc
    return d


def test_opex_ida_y_vuelta_conserva_los_colones():
    xlsx = export_opex_to_excel({"0220": [_fila_opex("CRC", usd=9434, crc=5000000)]},
                                "Budget 2027", 2027)
    filas = import_opex_from_excel(xlsx)
    fila = next(f for f in filas if f["account_code"].endswith("7065"))
    assert fila["currency"] == "CRC"
    assert fila["crc_jan"] == Decimal("5000000.00")


def test_opex_un_excel_viejo_sin_columna_de_moneda_no_rompe():
    """Un archivo bajado antes de este cambio no trae la columna Q: debe leerse
    como dolares, no reventar ni interpretarse como colones."""
    xlsx = export_opex_to_excel({"0110": [_fila_opex("USD", usd=800)]},
                                "Budget 2027", 2027)
    filas = import_opex_from_excel(xlsx)
    fila = next(f for f in filas if f["account_code"].endswith("7065"))
    assert fila["currency"] == "USD"
    assert fila["jan"] == Decimal("800.00")


def test_la_api_manda_la_moneda_al_exportador():
    import inspect
    from app.api import costs_api, opex_api
    for mod in (costs_api, opex_api):
        src = inspect.getsource(mod)
        assert '"currency": e.currency or "USD"' in src, (
            f"{mod.__name__} no manda la moneda al Excel")


# ── El consumidor del importador: donde reventaba ────────────────────────────
def test_el_importador_de_opex_no_exige_las_columnas_de_dolares():
    """Una fila en COLONES trae sus montos en crc_* y NO en jan..dec. El endpoint
    hacia `r[mk]` con acceso directo: KeyError -> 500 -> el navegador mostraba
    «Failed to fetch» sin decir por que. Con `.get` no revienta.
    """
    import inspect
    from app.api import opex_api
    src = inspect.getsource(opex_api.import_opex_excel)
    assert "r[mk] for mk in MONTH_ATTRS" not in src, (
        "acceso directo: una fila en colones lo revienta")
    assert "r.get(mk" in src


def test_los_dos_importadores_conservan_la_moneda():
    """Costos no reventaba: perdia la moneda en silencio, que es peor."""
    import inspect
    from app.api import costs_api, opex_api
    for mod, fn in ((opex_api, "import_opex_excel"),
                    (costs_api, "import_costs_excel")):
        src = inspect.getsource(getattr(mod, fn))
        assert "currency=" in src, f"{fn}: la fila entraria como dolares"
        assert 'f"crc_{mk}"' in src, f"{fn}: se perderian los colones"


def test_lo_importado_en_colones_queda_ya_en_dolares():
    """Si no, la linea queda con sus colones y el dolar en cero hasta que alguien
    recalcule — y el P&L la mostraria como si no existiera."""
    import inspect
    from app.api import costs_api, opex_api
    for mod in (opex_api, costs_api):
        assert hasattr(mod, "_derivar_importadas")
        src = inspect.getsource(mod._derivar_importadas)
        assert "get_tc_for_month" in src and "derivar_usd" in src
