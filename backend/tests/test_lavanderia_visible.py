# -*- coding: utf-8 -*-
"""
LA LAVANDERIA SE MUESTRA CON SU PROPIA BASE.

El panel de reparto enseñaba FTE en los dos tabs. Pero la lavandería reparte el
linen por KILOS: mostrar FTE ahi es enseñar un numero que NO explica el reparto,
y quien intente cuadrar el costo de un departamento contra su FTE no va a poder.

Las dos bases son distintas a proposito:
  Cafeteria  -> FTE   (se come segun cuanta gente haya)
  Lavanderia -> KILOS para el linen, FTE para los uniformes
"""
import pathlib

from tests._rutas import FRONT
PAGINA = FRONT / "app" / "allocations" / "config" / "page.tsx"


def _src():
    return PAGINA.read_text(encoding="utf-8") if PAGINA.exists() else ""


def test_la_lavanderia_no_repite_los_kilos_de_solo_lectura():
    """Los kilos se EDITAN en la configuracion. Mostrarlos otra vez de solo
    lectura en el panel ocupaba el espacio que necesitan los cuadros de costo, y
    dejaba las dos tablas apretadas con scroll interno."""
    s = _src()
    if not s:
        return
    assert 'if (tab === "laundry") return null;' in s


def test_la_configuracion_de_lavanderia_va_a_todo_el_ancho():
    """Es una tabla de 12 meses POR departamento: en una columna angosta queda
    con scroll interno y no se puede trabajar."""
    s = _src()
    if not s:
        return
    assert 'tab === "cafeteria" ? "minmax(320px, 520px) 1fr" : "1fr"' in s


def test_la_razonabilidad_se_juzga_por_kilo_en_lavanderia():
    s = _src()
    if not s:
        return
    # Los rótulos viven en el catálogo desde que el Excel y la pantalla
    # comparten clave. Se comprueba el criterio en los DOS idiomas.
    assert 't("perKilo")' in s and 't("perFte")' in s
    for idioma, kilo, fte in (("es", "Por kilo", "Por FTE"), ("en", "Per kilo", "Per FTE")):
        c = _catalogo(idioma)
        assert c["alloc.perKilo"] == kilo and c["alloc.perFte"] == fte
    # El criterio vive en el catálogo desde el 2026-08-19.
    assert "costo por kilo" in _catalogo("es")["alloc.perKiloEven"]
    assert "cost per kilo" in _catalogo("en")["alloc.perKiloEven"]


def test_el_panel_de_lavanderia_no_depende_del_reporte_de_FTE():
    """Sus kilos vienen de su propia configuracion: exigir el reporte de FTE
    dejaria la tabla en blanco sin motivo."""
    s = _src()
    if not s:
        return
    assert 'tab === "cafeteria" && !fteMes' in s


def test_el_reparto_de_lavanderia_sigue_siendo_de_3_vias():
    """Linen por kilos, uniformes por FTE, y el lavado de huespedes se queda como
    costo de venta en el 0161."""
    from app.engine.allocation_calculator import calculate_laundry_distribution
    import inspect
    src = inspect.getsource(calculate_laundry_distribution)
    assert "kilos" in src.lower()
    assert "uniform" in src.lower()


# ── El asiento contable, mes por mes ─────────────────────────────────────────
def test_el_asiento_muestra_los_12_meses():
    """Antes colapsaba todo a un periodo y habia que ir mes por mes con un
    selector. Con las 12 columnas se ve de una en que mes entra cada cosa."""
    s = _src()
    if not s:
        return
    assert "Asiento contable" in s
    assert "asientoPeriod" not in s, "quedo el selector de periodo, ya no hace falta"
    assert 't("totalDebit")' in s and 't("totalCredit")' in s
    for idioma, debe, haber in (("es", "TOTAL DEBE", "TOTAL HABER"),
                                ("en", "TOTAL DEBIT", "TOTAL CREDIT")):
        c = _catalogo(idioma)
        assert c["alloc.totalDebit"] == debe and c["alloc.totalCredit"] == haber


def test_el_asiento_cuadra_MES_A_MES_no_solo_en_el_ano():
    """Un asiento puede cuadrar en el ano y estar descuadrado en marzo y en junio
    compensandose. Lo que importa contablemente es cada mes."""
    s = _src()
    if not s:
        return
    assert 't("differenceZero")' in s, "se perdió la fila de control"
    assert "debe ser 0" in _catalogo("es")["alloc.differenceZero"]
    assert "must be 0" in _catalogo("en")["alloc.differenceZero"]
    assert "cuadra los 12 meses" in _catalogo("es")["alloc.balances12"]
    assert "balances all 12 months" in _catalogo("en")["alloc.balances12"]
    assert "MONTHS.every" in s, "no comprueba el cuadre en cada mes"


# ── El asiento en formato contable clasico ───────────────────────────────────
def test_hay_un_asiento_con_debe_y_haber_en_dos_columnas():
    """El formato de asiento: se ve de donde SALE y a donde ENTRA, con la cuenta
    y el departamento nombrados. Es anual — el mes a mes esta en el cuadro de
    arriba y repetirlo aqui solo lo haria ilegible."""
    s = _src()
    if not s:
        return
    # El asiento se rotula desde el catálogo; lo que la pantalla tiene que
    # seguir teniendo son las DOS columnas.
    assert 't("debit")' in s and 't("credit")' in s
    for idioma, debe, haber in (("es", "Debe", "Haber"), ("en", "Debit", "Credit")):
        c = _catalogo(idioma)
        assert c["alloc.debit"] == debe and c["alloc.credit"] == haber
    # La etiqueta se mudó al catálogo de idiomas: acá se verifica la CLAVE, y
    # `test_la_etiqueta_de_la_cuenta_existe_en_los_dos_idiomas` verifica que la
    # clave tenga texto. Buscar el literal en español haría fallar esta prueba
    # cada vez que se traduce algo, que es justo lo que NO tiene que pasar.
    assert 'accountDescription' in s
    assert 't("fullYearJanDec")' in s, "el asiento tiene que decir que es anual"
    assert "Año completo" in _catalogo("es")["alloc.fullYearJanDec"]
    assert "Full year" in _catalogo("en")["alloc.fullYearJanDec"]
    assert "const val = anual" in s, "el asiento clasico debe ser anual"


def test_la_etiqueta_de_la_cuenta_existe_en_los_dos_idiomas():
    """La otra mitad de la prueba de arriba: que la clave no apunte al vacío.
    Un `t("accountDescription")` sin entrada en el catálogo renderiza el nombre
    de la clave, y la columna del asiento queda diciendo «accountDescription»."""
    import json
    base = PAGINA.parents[2] / "messages"
    if not base.exists():
        return
    for idioma in ("es", "en"):
        cat = json.loads((base / f"{idioma}.json").read_text(encoding="utf-8"))
        assert cat.get("alloc", {}).get("accountDescription"), (
            f"falta alloc.accountDescription en {idioma}.json")


def test_el_asiento_nombra_la_cuenta_y_el_departamento():
    """Una lista de codigos (7310, 7685, 4999) no se lee como asiento."""
    s = _src()
    if not s:
        return
    assert "account_names" in s
    assert "ctaNombre" in s and "deptNombre" in s


def test_el_backend_manda_los_nombres_de_cuenta():
    import inspect
    from app.api import allocation_api
    src = inspect.getsource(allocation_api)
    assert '"account_names"' in src
    assert 'nombres.setdefault("4999"' in src


def _catalogo(idioma: str) -> dict:
    """El catálogo de idiomas, aplanado.

    ⚠️ Varias pruebas de este archivo comprobaban un CRITERIO buscando su texto
    dentro del `.tsx`. Al extraer los textos al catálogo (2026-08-19) ese texto
    dejó de estar ahí — el criterio no cambió, cambió de archivo. Y ahora se
    comprueba en LOS DOS idiomas: si solo se mirara el español, la pantalla en
    inglés podría perder la garantía sin que nadie se entere.
    """
    import json

    from tests._rutas import FRONT

    def plano(o, p=""):
        for k, v in o.items():
            if isinstance(v, dict):
                yield from plano(v, f"{p}{k}.")
            else:
                yield f"{p}{k}", v

    return dict(plano(json.loads(
        (FRONT / "messages" / f"{idioma}.json").read_text(encoding="utf-8"))))
