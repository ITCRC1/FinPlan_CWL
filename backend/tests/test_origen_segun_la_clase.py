# -*- coding: utf-8 -*-
"""El mapeo dice lo mismo que la clase de la cuenta.

Owner, 2026-11-10: «asegurate que 4 son ingresos, 5 costos, 6 planilla, 7 opex
y 8 gastos de la propiedad y 9 stats».

El cálculo separa por el primer dígito (`pl_engine`); estas pruebas exigen que
el mapeo tampoco lo contradiga: ni la categoría que resulta de su sección, ni el
rótulo de origen (migración 163).
"""
import importlib.util
import json
import pathlib

from app.engine import gl_por_mes as g

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MAPEO = json.loads((RAIZ / "app" / "seed_data" / "mapping_pl.json").read_text(encoding="utf-8"))

CATEGORIA = {"4": {"REVENUE", "ALLOCATIONS"}, "5": {"COST_OF_SALES"}, "6": {"PAYROLL"},
             "7": {"OPERATING_EXPENSES"}, "8": {"BELOW_GOP"}}
ORIGEN = {"6": {"Payroll", "PAYROLL"}, "7": {"Opex", "OpEx", "Operating Expense"}}


def test_cada_fila_cae_en_la_categoria_de_su_clase():
    malas = [(x["source_department"], x["account_code"], x["report_section"])
             for x in MAPEO["account_mapping"]
             if g.categoria_de(str(x["account_code"]), x["report_section"])
             not in CATEGORIA[str(x["account_code"])[0]]]
    assert not malas, malas[:10]


def test_ninguna_estadistica_esta_en_el_pl():
    assert not [x for x in MAPEO["account_mapping"] if str(x["account_code"]).startswith("9")]


def test_el_origen_de_planilla_y_opex_dice_su_clase():
    malas = [(x["source_department"], x["account_code"], x["source_origin"])
             for x in MAPEO["account_mapping"]
             if str(x["account_code"])[0] in ORIGEN
             and x["source_origin"] not in ORIGEN[str(x["account_code"])[0]]]
    assert not malas, malas[:10]


def test_la_migracion_163_renombra_a_lo_que_dice_el_archivo():
    """Cada fila que la migración renombra tiene que existir en el archivo con el
    rótulo nuevo; si no, la semilla insertaría otra y quedarían dos."""
    ruta = RAIZ / "alembic" / "versions" / "163_origen_del_mapeo_segun_la_clase.py"
    spec = importlib.util.spec_from_file_location("m163", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    en_archivo = {(x["report_id"], x["source_department"], str(x["account_code"]), x["source_origin"])
                  for x in MAPEO["account_mapping"] if not x.get("vigente_desde")}
    assert len(mod.CAMBIOS) == 98
    for rep, dep, cta, viejo, nuevo in mod.CAMBIOS:
        assert (rep, dep, cta, nuevo) in en_archivo, (dep, cta, nuevo)
        assert (rep, dep, cta, viejo) not in en_archivo, (dep, cta, viejo)
