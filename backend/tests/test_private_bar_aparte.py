# -*- coding: utf-8 -*-
"""
EL 0121 ES EL PRIVATE BAR Y VA APARTE, NO DENTRO DE A&B.

Decisión del owner (2026-08-12): el 0121 deja de llamarse «Bar» y pasa a ser
**Private Bar**, un centro de utilidad propio con ingreso Y costo. No es un
outlet de A&B: no cuelga del 0120 y no comparte su bloque.

Por qué importa que sea grupo propio y no solo «sin padre»: si se lo saca de FB
sin darle grupo, `group_for_dept` lo manda a OTHER_OVERHEAD y el costo de un bar
termina en overhead. Con grupo propio el motor le arma sus tres líneas solo
—`REV_PRIVATE_BAR`, `OPEXP_PRIVATE_BAR`, `OPPROFIT_PRIVATE_BAR`— porque las
deriva de OPERATING_GROUP_ORDER.

Ojo con la historia: entre el commit 28e95fb y este, el 0121 estuvo colgado del
0120 por un rato. Fue al revés de lo que el owner quería, y esta prueba existe
para que no vuelva.

El arreglo vive en las constantes de `pl_engine` y NO en una migración:
`seed_department_catalog.build_rows()` deriva `parent_dept_code`,
`default_pl_group` y `dept_name` de ellas, y el seed corre en cada deploy
pisando todos los campos de las filas que ya existen.
"""
import json
import pathlib

from app.engine import pl_engine
from app.engine.pl_engine import (
    CHECKBOOK_DEPT_CONSOLIDATION, OPERATING_DEPT_GROUPS, OPERATING_GROUP_ORDER,
    GROUP_NAMES, REVENUE_ONLY_GROUPS,
)
from app.seed_department_catalog import build_rows

MAPEO = (pathlib.Path(pl_engine.__file__).parents[1]
         / "seed_data" / "mapping_pl.json")

# Departamentos sin reglas propias y sin padre. **El owner confirmó (2026-08-12)
# que están bien así: son independientes, no hijos de nadie.** Utilities es
# Utilities. No colgarlos de un padre.
#
# El 0121 NO está acá: ya tiene sus 35 reglas propias (modelo Gift Shop), así
# que no depende de heredar de nadie.
#
# Si aparece un SEXTO, esta prueba falla — no para colgarlo, sino para que
# alguien lo decida a conciencia en vez de descubrirlo en un P&L.
SUELTOS_CONOCIDOS = {"0140", "0151", "0184", "0191", "0210"}


def _reglas_por_depto() -> set[str]:
    datos = json.loads(MAPEO.read_text(encoding="utf-8"))
    return {(m.get("dept_code") or "").strip() for m in datos["account_mapping"]}


def test_el_private_bar_no_cuelga_de_ayb():
    assert "0121" not in CHECKBOOK_DEPT_CONSOLIDATION
    assert pl_engine.consolidate_dept("0121") == "0121"


def test_el_private_bar_salio_del_grupo_fb():
    assert "0121" not in OPERATING_DEPT_GROUPS["FB"]
    assert OPERATING_DEPT_GROUPS["PRIVATE_BAR"] == ["0121"]
    assert pl_engine.group_for_dept("0121") == "PRIVATE_BAR"


def test_el_private_bar_tiene_bloque_propio_con_costo():
    """Ingreso Y costo: el owner lo pidió como centro de utilidad completo."""
    assert "PRIVATE_BAR" in OPERATING_GROUP_ORDER
    assert GROUP_NAMES["PRIVATE_BAR"] == "Private Bar"
    # fuera de REVENUE_ONLY_GROUPS = el motor le arma la línea de gasto
    assert "PRIVATE_BAR" not in REVENUE_ONLY_GROUPS


def test_el_catalogo_lo_refleja():
    """El seed deriva nombre, grupo y padre de las constantes."""
    fila = next(r for r in build_rows() if r["dept_code"] == "0121")
    assert fila["dept_name"] == "Private Bar"
    assert fila["default_pl_group"] == "PRIVATE_BAR"
    assert not (fila["parent_dept_code"] or "")


def test_tiene_el_modelo_del_gift_shop():
    """Las MISMAS cuentas que el Gift Shop, sean las que sean.

    El owner lo pidió modelado como tienda —compra producto y lo vende con su
    margen— y con las mismas cuentas del `0165`. Funciona porque la línea la
    decide el par (departamento, cuenta): los mismos números en el 0121 caen en
    las líneas del Private Bar, no en las del Gift Shop.

    Se comparan los CONJUNTOS y no un número fijo. La versión anterior exigía
    «35 y 35», y el día que la tienda sumó el núcleo compartido de cuentas
    (4999, 7105, 7110, 7150, 7175, 7185) la prueba falló por el número aunque
    lo que vigila —que los dos lleven lo mismo— seguía siendo cierto. Un número
    mágico convierte cualquier crecimiento legítimo en una falla.
    """
    datos = json.loads(MAPEO.read_text(encoding="utf-8"))
    propias = [m for m in datos["account_mapping"]
               if (m.get("dept_code") or "").strip() == "0121"]
    modelo = [m for m in datos["account_mapping"]
              if (m.get("dept_code") or "").strip() == "0165"]
    assert propias and modelo
    assert len(propias) == len(modelo)
    # mismas cuentas que la tienda, ni una de más ni de menos
    assert ({m["account_code"] for m in propias}
            == {m["account_code"] for m in modelo})
    destinos = {m["report_line_code"] for m in propias}
    # Se le sumo `COS_PRIVATE_BAR` al separar el costo de ventas (2026-08-14).
    # Todas son del mismo departamento; lo que se vigila es que ninguna sea
    # de A&B.
    assert destinos == {"REV_PRIVATE_BAR", "OPEX_PRIVATE_BAR", "COS_PRIVATE_BAR"}
    assert sum(1 for m in propias if m["report_line_code"] == "REV_PRIVATE_BAR") == 4


def test_su_plata_llega_a_su_linea_y_no_a_la_de_ayb():
    """Antes de tener reglas, su ingreso caía en REV_FB y su gasto en OPEX_ROOMS."""
    datos = json.loads(MAPEO.read_text(encoding="utf-8"))
    resolve = pl_engine.construir_resolvedor(datos["account_mapping"])
    for cuenta in ("4301", "4302", "4303", "4304"):
        regla, como = resolve("0121", cuenta)
        assert como == "exact", (cuenta, como)
        assert regla["report_line_code"] == "REV_PRIVATE_BAR"
    # La 5203 es clase 5 y desde 2026-08-14 rutea a `COS_PRIVATE_BAR`; las de
    # planilla y opex siguen en `OPEX_PRIVATE_BAR`. Las dos son del mismo
    # departamento, que es lo que esta prueba cuida: que su plata no aparezca
    # en la línea de A&B.
    for cuenta in ("5203", "6000", "6025", "7400", "7680"):
        regla, como = resolve("0121", cuenta)
        assert como == "exact", (cuenta, como)
        esperada = "COS_PRIVATE_BAR" if cuenta.startswith("5") else "OPEX_PRIVATE_BAR"
        assert regla["report_line_code"] == esperada, (cuenta, regla["report_line_code"])
    # y el Gift Shop sigue yendo al suyo: las mismas cuentas, otro departamento
    regla, _ = resolve("0165", "4301")
    assert regla["report_line_code"] == "REV_RETAIL"


def test_las_tres_lineas_van_pegadas_a_ayb_y_sin_empate():
    """El reporte ordena solo por display_order: un empate se rompe al azar."""
    datos = json.loads(MAPEO.read_text(encoding="utf-8"))
    por_codigo = {l["line_code"]: l for l in datos["report_line_config"]}
    for nueva, vecina in (("REV_PRIVATE_BAR", "REV_FB"),
                          ("OPEX_PRIVATE_BAR", "OPEX_FB"),
                          ("PROFIT_PRIVATE_BAR", "PROFIT_FB")):
        assert nueva in por_codigo, nueva
        assert por_codigo[nueva]["display_order"] == por_codigo[vecina]["display_order"] + 1
        assert por_codigo[nueva]["line_name"] == "Private Bar"
    ordenes = [l["display_order"] for l in datos["report_line_config"]
               if l["line_code"] in ("REV_PRIVATE_BAR", "OPEX_PRIVATE_BAR",
                                     "PROFIT_PRIVATE_BAR")]
    for l in datos["report_line_config"]:
        if l["line_code"] not in ("REV_PRIVATE_BAR", "OPEX_PRIVATE_BAR",
                                  "PROFIT_PRIVATE_BAR"):
            assert l["display_order"] not in ordenes, (
                f"{l['line_code']} empata con una línea del Private Bar")


def test_la_misma_cuenta_en_dos_deptos_no_se_mezcla():
    """El caso que casi se va vivo: 4301 la usan el Gift Shop Y el Private Bar.

    Por rango de cuenta, todo 43xx es RETAIL — así que el ingreso del Private
    Bar se iba entero a Retail-Gift Shop. `build_actual_inputs` PREFIERE el
    departamento, pero solo si el grupo tiene llave en GROUP_TO_REVENUE_LINE; el
    grupo nuevo no la tenía y caía al rango. Sin esta prueba, compartir cuentas
    con la tienda se rompe en silencio: los totales cuadran, la plata está en la
    línea de al lado.
    """
    from decimal import Decimal
    from app.engine.pl_engine import calculate_full_pl, build_actual_inputs

    filas = [
        {"account_code": "4301", "dept_code": "0121", "amount": Decimal("50000")},
        {"account_code": "5203", "dept_code": "0121", "amount": Decimal("18000")},
        {"account_code": "6000", "dept_code": "0121", "amount": Decimal("9000")},
        {"account_code": "7400", "dept_code": "0121", "amount": Decimal("3000")},
        {"account_code": "4301", "dept_code": "0165", "amount": Decimal("7000")},
        {"account_code": "4110", "dept_code": "0120", "amount": Decimal("90000")},
    ]
    pl = {l.line_code: l.amount_usd
          for l in calculate_full_pl(**build_actual_inputs(filas))}
    assert pl["REV_PRIVATE_BAR"] == Decimal("50000")
    assert pl["REV_RETAIL"] == Decimal("7000")     # la tienda conserva lo suyo
    assert pl["REV_FB"] == Decimal("90000")        # A&B no se entera
    assert pl["OPEXP_PRIVATE_BAR"] == Decimal("30000")   # 18k producto + 9k planilla + 3k opex
    assert pl["OPPROFIT_PRIVATE_BAR"] == Decimal("20000")


def test_el_puente_al_vocabulario_del_reporte():
    """El motor emite OPEXP_/OPPROFIT_ y el reporte usa OPEX_/PROFIT_.

    El puente (_MOTOR_TO_CANON) es una lista fija: un grupo nuevo que no esté
    ahí sale del motor y nunca aparece en el P&L Full Detail.
    """
    canon = pl_engine._MOTOR_TO_CANON
    assert canon["REV_PRIVATE_BAR"] == ("REV_PRIVATE_BAR", "REVENUES")
    assert canon["OPEXP_PRIVATE_BAR"] == ("OPEX_PRIVATE_BAR", "OPERATING EXPENSES")
    assert canon["OPPROFIT_PRIVATE_BAR"] == ("PROFIT_PRIVATE_BAR", "OPERATING PROFIT")


def test_no_aparecio_otro_departamento_suelto():
    con_regla = _reglas_por_depto()
    sueltos = {
        r["dept_code"] for r in build_rows()
        if r["dept_code"] not in con_regla
        and not (r.get("parent_dept_code") or "").strip()
    }
    nuevos = sueltos - SUELTOS_CONOCIDOS
    assert not nuevos, (
        f"departamentos sueltos nuevos: {sorted(nuevos)} — sin reglas propias y "
        "sin padre, su dato va a rutear por FALLBACK a la línea de otro depto")
