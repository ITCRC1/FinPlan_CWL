# -*- coding: utf-8 -*-
"""
LA TIENDA NO PUEDE CAER EN EL PRIVATE BAR.

**Esto fue una regresión de verdad, introducida el 2026-08-12.** Vale escribir
cómo pasó, porque el mecanismo va a volver a morder:

1. El `0151` Tienda / Gift Shop nunca tuvo reglas propias. Resolvía por FALLBACK
   —que ignora el departamento y agarra la regla de cualquiera que use esa
   cuenta— y aterrizaba bien de casualidad, porque `4301`–`4304` y `5203`–`5208`
   tenían UNA sola regla: la del `0165` Retail.
2. Ese mismo día se creó el Private Bar (`0121`) con **las mismas cuentas**, por
   decisión del owner.
3. El desempate del FALLBACK se queda con el departamento de código **MENOR**, y
   `0121 < 0165`. Desde ese momento el costo de la Tienda —$7,006 en 2024,
   $14,214 en 2025, $17,403 en 2026, $23,440 en el Budget— resolvía hacia
   `OPEX_PRIVATE_BAR`.

Nada dio error. Los totales seguían cuadrando: la plata estaba, solo que en la
línea de al lado.

**El arreglo NO es colgarlo de un padre** — el owner decidió que estos
departamentos son independientes. Es darle **reglas propias**, que es lo que lo
saca del FALLBACK sin tocar esa decisión.
"""
import json
import pathlib

from app.engine import pl_engine
from app.seed_department_catalog import build_rows

MAPEO = (pathlib.Path(pl_engine.__file__).parents[1]
         / "seed_data" / "mapping_pl.json")

# Las que comparten Tienda, Gift Shop y Private Bar.
COMPARTIDAS_INGRESO = ("4301", "4302", "4303", "4304")
COMPARTIDAS_COSTO = ("5203", "5204", "5205", "5206", "5207", "5208")


def _resolver():
    reglas = json.loads(MAPEO.read_text(encoding="utf-8"))["account_mapping"]
    pl_engine.set_dept_catalog(build_rows())
    try:
        return pl_engine.construir_resolvedor(reglas), reglas
    finally:
        pass


def test_la_tienda_va_a_su_linea_no_al_bar():
    """La Tienda tiene línea propia desde el 2026-08-13 — antes compartía
    «Retail-Gift Shop» con el 0165 y los dos se veían sumados."""
    resolve, _ = _resolver()
    for cuenta in COMPARTIDAS_INGRESO:
        regla, como = resolve("0151", cuenta)
        assert regla["report_line_code"] == "REV_TIENDA", (cuenta, regla["report_line_code"])
        assert como == "exact", (cuenta, como)
    for cuenta in COMPARTIDAS_COSTO:
        regla, como = resolve("0151", cuenta)
        # La 5203 es clase 5 y desde 2026-08-14 va a `COS_TIENDA`. Sigue
        # siendo de la Tienda, que es lo unico que esta prueba cuida.
        assert regla["report_line_code"].endswith("_TIENDA"), (cuenta, regla["report_line_code"])
        assert como == "exact", (cuenta, como)


def test_los_tres_departamentos_van_cada_uno_a_lo_suyo():
    """Misma cuenta, tres departamentos, tres líneas. Es el diseño."""
    resolve, _ = _resolver()
    esperado = {"0151": "REV_TIENDA", "0165": "REV_RETAIL", "0121": "REV_PRIVATE_BAR"}
    for dept, linea in esperado.items():
        regla, como = resolve(dept, "4301")
        assert regla["report_line_code"] == linea, (dept, regla["report_line_code"])
        assert como == "exact", (dept, como)


def test_la_tienda_ya_no_depende_del_desempate():
    """Con regla propia, da igual quién más use el número de cuenta.

    Es la prueba que importa: mientras el `0151` resuelva `exact`, agregar un
    departamento nuevo con esas cuentas no le puede mover la plata.
    """
    resolve, reglas = _resolver()
    propias = [m for m in reglas if (m.get("dept_code") or "") == "0151"]
    assert len(propias) >= 35, f"el 0151 quedó con {len(propias)} reglas propias"
    for cuenta in COMPARTIDAS_INGRESO + COMPARTIDAS_COSTO:
        _, como = resolve("0151", cuenta)
        assert como == "exact", (cuenta, como)
