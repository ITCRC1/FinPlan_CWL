# -*- coding: utf-8 -*-
"""
LA HOJA DE REVISIÓN TIENE QUE QUEDAR EXACTAMENTE COMO SE VE.

Pedido del owner (2026-08-31): *«el tab de Julio debe quedar exactamente como se
ve, ya que será el que a ojo se hará la visión final para validar los
hallazgos»*. No es un intermedio: es la superficie de revisión.

Así que la prueba no comprueba que los números «sean razonables». Comprueba que
la hoja generada reproduce el tab `Julio 2026` del libro del owner **celda por
celda**: mismo número de fila, misma etiqueta —erratas incluidas— y mismo valor.
Si una fila se corre o una etiqueta cambia, deja de servir para revisar a ojo.

El fixture `revision_JUL2026_esperado.json` son los 67 valores de la columna
Actual, extraídos del libro. El libro pesa 104 MB y no entra al repo.
"""
import json
import pathlib
from decimal import Decimal as D

import pytest

from app.export import revision_mes_xlsx as rev
from app.importers import integrity_final as m

BASE = pathlib.Path(__file__).resolve().parents[1]
INTEGRITY = BASE / "tests" / "fixtures" / "integrity_final_JUL2026.xlsx"
ESPERADO = BASE / "tests" / "fixtures" / "revision_JUL2026_esperado.json"
SEMILLA = BASE / "app" / "seed_data" / "CWL" / "mapd_integrity.json"
TC_JULIO = D("454.75")
TOLERANCIA = D("0.06")      # el tab está redondeado a un decimal


@pytest.fixture(scope="module")
def grupo_de():
    from app.engine import pl_engine
    from app.seed_department_catalog import build_rows
    filas = build_rows()
    pl_engine.set_dept_catalog([{"dept_code": f["dept_code"],
                                 "default_pl_group": f.get("default_pl_group", ""),
                                 "parent_dept_code": f.get("parent_dept_code")}
                                for f in filas])
    cat = {f["dept_code"]: f for f in filas}

    def resolver(destino: str):
        f = cat.get(destino)
        if f is not None and not (f.get("default_pl_group") or ""):
            return None
        return pl_engine.group_for_dept(destino)
    return resolver


@pytest.fixture(scope="module")
def valores(grupo_de) -> dict:
    puente = {d["codigo"]: d for d in
              json.loads(SEMILLA.read_text(encoding="utf-8"))["departamentos"]}
    r = m.leer(INTEGRITY.read_bytes(), TC_JULIO, puente, grupo_de)
    return rev.valores_desde_precierre(r["filas"])


@pytest.fixture(scope="module")
def hoja(valores):
    return rev.construir("July", 2026, {}, valores).active


@pytest.fixture(scope="module")
def referencia() -> list[dict]:
    return json.loads(ESPERADO.read_text(encoding="utf-8"))["filas"]


# ═════════════════════════════════════════════════════════════════════════════
# CELDA POR CELDA CONTRA EL TAB DEL OWNER
# ═════════════════════════════════════════════════════════════════════════════

def test_todas_las_etiquetas_estan_en_su_fila(hoja, referencia):
    """Incluidas las erratas del original: «Total Operationg expenses»,
    «Miscellaneos», «TOTAL RENTA AND MANAGEMENT FEES». Cambiarlas es cambiar lo
    que el ojo busca."""
    malas = [(r["fila"], r["etiqueta"], hoja.cell(r["fila"], rev.COL_ETIQUETA).value)
             for r in referencia
             if (hoja.cell(r["fila"], rev.COL_ETIQUETA).value or "") != r["etiqueta"]]
    assert not malas, f"etiquetas que no coinciden: {malas}"


def test_la_columna_actual_reproduce_el_tab(hoja, referencia):
    """Los 67 valores, en su fila."""
    malas = []
    for r in referencia:
        esperado = D(str(r["actual"] or 0))
        got = D(str(hoja.cell(r["fila"], rev.COL_ACTUAL).value or 0))
        if abs(got - esperado) > TOLERANCIA:
            malas.append((r["fila"], r["etiqueta"], float(esperado), float(got)))
    assert not malas, f"valores que difieren: {malas}"


@pytest.mark.parametrize("fila,col", [(15, rev.COL_ETIQUETA), (15, rev.COL_FORECAST),
                                      (15, rev.COL_BUDGET), (15, rev.COL_ACTUAL),
                                      (15, rev.COL_VAR_FCST), (15, rev.COL_VAR_BUD)])
def test_los_encabezados_estan_en_su_columna(hoja, fila, col):
    assert hoja.cell(fila, col).value


def test_las_columnas_estan_donde_estaban(hoja):
    """D etiqueta · E Forecast · F Budget · H Actual · J y K las variaciones.
    Las columnas A B C G I van vacías: son las que separan los bloques."""
    assert (rev.COL_ETIQUETA, rev.COL_FORECAST, rev.COL_BUDGET) == (4, 5, 6)
    assert (rev.COL_ACTUAL, rev.COL_VAR_FCST, rev.COL_VAR_BUD) == (8, 10, 11)
    for col in (1, 2, 3, 7, 9):
        assert all(hoja.cell(f, col).value is None for f in range(16, 130))


# ═════════════════════════════════════════════════════════════════════════════
# LA CASCADA CIERRA CONSIGO MISMA
# ═════════════════════════════════════════════════════════════════════════════

def test_el_total_de_ingresos_es_la_suma_de_sus_divisiones(hoja):
    filas_rev = [17 + i for i in range(len(rev.DIVISIONES))]
    s = sum(D(str(hoja.cell(f, rev.COL_ACTUAL).value or 0)) for f in filas_rev)
    assert abs(s - D(str(hoja.cell(28, rev.COL_ACTUAL).value))) < D("0.02")


def test_la_utilidad_por_division_es_ingreso_menos_gasto(hoja):
    for i in range(len(rev.DIVISIONES)):
        ing = D(str(hoja.cell(17 + i, rev.COL_ACTUAL).value or 0))
        gto = D(str(hoja.cell(32 + i, rev.COL_ACTUAL).value or 0))
        pro = D(str(hoja.cell(49 + i, rev.COL_ACTUAL).value or 0))
        assert abs((ing - gto) - pro) < D("0.02"), rev.DIVISIONES[i][0]


def test_el_gop_es_utilidad_operativa_menos_overhead(hoja):
    op = D(str(hoja.cell(62, rev.COL_ACTUAL).value))
    oh = D(str(hoja.cell(77, rev.COL_ACTUAL).value))
    gop = D(str(hoja.cell(79, rev.COL_ACTUAL).value))
    assert abs((op - oh) - gop) < D("0.02")


def test_la_utilidad_neta_de_julio(hoja):
    """−94.182,95, el número que el owner ya cerró."""
    assert abs(D(str(hoja.cell(128, rev.COL_ACTUAL).value)) - D("-94182.95")) < D("0.02")


# ═════════════════════════════════════════════════════════════════════════════
# LAS TRAMPAS DEL LAYOUT
# ═════════════════════════════════════════════════════════════════════════════

def test_las_dos_filas_CAPITAL_EXPENSE_no_comparten_valor(hoja):
    """El tab tiene la etiqueta dos veces: la 99 está en cero y la 121 lleva la
    reserva de capital. Igualarlas metía 9.937,63 donde el tab muestra 0."""
    assert hoja.cell(99, rev.COL_ETIQUETA).value == "CAPITAL EXPENSE"
    assert hoja.cell(121, rev.COL_ETIQUETA).value == "CAPITAL EXPENSE"
    assert D(str(hoja.cell(99, rev.COL_ACTUAL).value or 0)) == D("0")
    assert abs(D(str(hoja.cell(121, rev.COL_ACTUAL).value)) - D("9937.63")) < D("0.02")


def test_la_fila_99_no_entra_en_el_total_de_owners_expenses(hoja):
    """18.664,70 = renta + fees + seguro + otros. Sin la 99."""
    assert abs(D(str(hoja.cell(103, rev.COL_ACTUAL).value)) - D("18664.70")) < D("0.02")


def test_la_variacion_es_actual_menos_el_comparativo(valores):
    """Verificado contra la fila 17 del tab: 105.358,4 − 133.920,0 = −28.561,6."""
    hoja = rev.construir("July", 2026, {}, valores,
                         forecast={"rev.Rooms": D("133920.00")}).active
    assert abs(D(str(hoja.cell(17, rev.COL_VAR_FCST).value)) - D("-28561.63")) < D("0.02")


def test_una_columna_que_no_se_pasa_queda_en_cero(hoja):
    """Sin Forecast ni Budget la hoja se dibuja igual, con esas columnas en cero
    — no se inventa un comparativo."""
    assert D(str(hoja.cell(17, rev.COL_FORECAST).value or 0)) == D("0")
    assert D(str(hoja.cell(17, rev.COL_BUDGET).value or 0)) == D("0")


def test_el_private_bar_esta_dentro_de_ayb_en_esta_hoja(valores):
    """FinPlan lo separa, pero el tab lo junta. La hoja respeta el tab; abrirlo
    es decisión del owner."""
    assert "PRIVATE_BAR" in dict(rev.DIVISIONES)["F&B"]
