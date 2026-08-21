# -*- coding: utf-8 -*-
"""
LA COLUMNA «YTD» DEL REPORTE RESPETA EL MES ELEGIDO.

En `/reports/ytd` el usuario elige «hasta qué mes» reportar. Los renglones de
dólares lo respetaban (`lineValYTD` suma 1..through), pero el bloque de
ESTADÍSTICAS —noches, ocupación, ADR, RevPAR— llamaba a una función que sumaba
los doce meses siempre.

Resultado: las columnas «YTD Jun» y «Full Year» mostraban el MISMO número, y el
reporte se contradecía consigo mismo —dólares hasta junio, estadísticas del año
entero— sin que nada avisara. Un ADR «YTD Jun» que en realidad era del año no se
nota mirándolo: se nota cuando alguien lo usa para decidir una tarifa.

Es una prueba de código fuente porque la lógica vive en el componente de React.
No es elegante, pero es lo único que puede vigilar que la función siga recibiendo
el corte — que es justo lo que le faltaba.
"""
import pathlib
import re

import pytest

PAGINA = (pathlib.Path(__file__).resolve().parents[2]
          / "frontend" / "app" / "reports" / "ytd" / "page.tsx")


@pytest.fixture(scope="module")
def fuente() -> str:
    return PAGINA.read_text(encoding="utf-8")


def test_la_funcion_de_estadisticas_recibe_el_corte(fuente):
    assert "function getKpiRange(pl: PLMonthly | null, code: string, through: number)" in fuente, (
        "la funcion de estadisticas volvio a no recibir el mes de corte")
    assert "getKpiAnnual" not in fuente, (
        "quedo la funcion vieja, que sumaba los doce meses sin mirar el corte")


def test_filtra_por_el_mes_elegido(fuente):
    cuerpo = fuente.split("function getKpiRange", 1)[1].split("\n}", 1)[0]
    assert "m.month <= through" in cuerpo, (
        "no filtra los meses: vuelve a sumar el año entero")


def test_la_columna_ytd_y_la_de_ano_completo_piden_cosas_distintas(fuente):
    """Si las dos piden lo mismo, la de YTD miente — que es el defecto original."""
    assert "getKpiRange(pl1, kpi.code, through)" in fuente, "falta la columna YTD"
    assert "getKpiRange(pl1, kpi.code, 12)" in fuente, "falta la columna Full Year"


def test_las_tasas_se_ponderan_no_se_promedian(fuente):
    """La ocupación acumulada es noches ocupadas ÷ noches disponibles del
    período, no el promedio de los porcentajes mensuales. Con meses de distinto
    tamaño —y con octubre cerrado— las dos cosas no dan lo mismo."""
    cuerpo = fuente.split("function getKpiRange", 1)[1].split("\n}", 1)[0]
    assert re.search(r'code === "occ"\s*\)\s*return avail \? occ / avail', cuerpo), (
        "la ocupacion acumulada no se esta ponderando por noches disponibles")
    assert re.search(r'code === "adr"\s*\)\s*return occ \? rev / occ', cuerpo), (
        "el ADR acumulado no se esta ponderando por noches ocupadas")


def test_el_excel_baja_el_ytd_del_corte_y_el_ano_aparte(fuente):
    """El archivo copia lo que está en pantalla: si la columna YTD del Excel
    trajera el año completo, el defecto seguiría vivo en el archivo."""
    assert "const ytd = getKpiRange(pl1, kpi.code, through);" in fuente
    assert "const anual = getKpiRange(pl1, kpi.code, 12);" in fuente
