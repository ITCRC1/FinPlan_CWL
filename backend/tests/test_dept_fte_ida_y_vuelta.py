# -*- coding: utf-8 -*-
"""FTE real por depto: exportar la plantilla y volver a leerla tiene que dar
lo mismo que se prellenó — es la ida y vuelta que pidió el owner para cargar
mes a mes cuando el costo es real pero no hay planilla al detalle."""
from app.export.dept_fte_excel import export_dept_fte_template
from app.importers.dept_fte_importer import parse_dept_fte

DEPTS = [("0110", "Rooms"), ("0120", "F&B")]


def test_prellenado_vuelve_igual():
    prellenado = {("0110", 6): 4.5, ("0120", 6): 2.0}
    xlsx = export_dept_fte_template(DEPTS, prellenado, "ACTUAL 2026")
    filas = parse_dept_fte(xlsx)
    junio = {(r["dept_code"], r["month"]): r["fte"] for r in filas if r["month"] == 6}
    assert junio[("0110", 6)] == 4.5
    assert junio[("0120", 6)] == 2.0


def test_blanco_no_genera_fila():
    """Una celda vacía no debe convertirse en una fila con FTE=0 fantasma —
    el importador debe poder distinguir 'sin dato' de 'cero real' del lado
    del endpoint (que descarta fte=0 al guardar), no acá."""
    xlsx = export_dept_fte_template(DEPTS, {}, "ACTUAL 2026")
    filas = parse_dept_fte(xlsx)
    assert all(f["fte"] == 0.0 for f in filas)
    assert len(filas) == 12 * len(DEPTS)


def test_los_12_meses_se_detectan():
    xlsx = export_dept_fte_template(DEPTS, {}, "ACTUAL 2026")
    filas = parse_dept_fte(xlsx)
    assert sorted(set(f["month"] for f in filas)) == list(range(1, 13))
