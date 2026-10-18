# -*- coding: utf-8 -*-
"""Una columna del P&L Statement puede mirar OTRO mes.

Owner, 2026-10-17, por tercera vez y señalando esta pantalla: *«quiero que
salga primero Agosto, como base comparativa y precierre Setiembre contra
forecast o budget»* · *«veo todo igual»*.

## Lo que estaba viendo

Puso el espejo de Pre-Cierre en las ranuras 1 y 2 y le salieron dos columnas
idénticas con **Var $0.00** en cada línea. No era un defecto: las cuatro
ranuras eligen ESCENARIO y el mes salía del selector de arriba, así que poner
el mismo escenario dos veces daba el mismo mes dos veces.

Y **Var $0,00 se lee como «no cambió nada»**, que es una conclusión — no un
hueco. Por eso había que arreglarlo y no solo explicarlo.

## El límite, dicho en la pantalla

El mes por ranura vale en el **P&L Statement**. Los otros sub-tabs leen el mes
de arriba. Un cuadro que muestra otro mes sin decirlo es la forma de fallar más
cara de este sistema, así que cuando hay una columna en otro mes y el sub-tab
no lo soporta, la pantalla lo dice en rojo.
"""
import inspect
import pathlib
import re

from app.api import pl_api

FRONT = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "app"
         / "month-end" / "pl" / "Pantalla.tsx")


def test_el_endpoint_acepta_id_arroba_mes():
    fuente = inspect.getsource(pl_api.get_pl_compare)
    assert 'sid, _, m_txt = crudo.partition("@")' in fuente
    assert "m_col = int(m_txt) if m_txt else month" in fuente
    # Y el mes y el acumulado se calculan con el mes DE ESA COLUMNA.
    assert 'one = _col([m for m in monthly if m["month"] == m_col])' in fuente
    assert 'ytd = _col([m for m in monthly if m["month"] <= m_col])' in fuente


def test_un_mes_invalido_no_revienta_la_pantalla():
    """El sufijo llega de la URL y puede venir con cualquier cosa. Tumbar el
    P&L entero por un `@abc` seria peor que ignorarlo."""
    fuente = inspect.getsource(pl_api.get_pl_compare)
    assert "except ValueError:" in fuente
    assert "if not 1 <= m_col <= 12:" in fuente


def test_el_MISMO_escenario_en_dos_meses_da_DOS_columnas():
    """⚠️ La trampa, y es silenciosa.

    «Pre-Cierre agosto» y «Pre-Cierre setiembre» son el MISMO `scenario_id`. Con
    la llave pelada la segunda pisa a la primera: el cuadro se ve perfecto
    mostrando un solo mes dos veces, y las variaciones dan cero — que es
    exactamente lo que el owner estaba viendo antes de este cambio.
    """
    fuente = inspect.getsource(pl_api.get_pl_compare)
    assert '"scenario_id": f"{sid}@{m_col}" if m_col != month else sid' in fuente
    # Y la columna se ROTULA con el mes, o no hay como saber cual es cual.
    assert 'f"{_scenario_label(scenario)} · {MESES_ES[m_col - 1]}"' in fuente


def test_sin_arroba_se_comporta_igual_que_antes():
    """Los enlaces guardados, el Word y el Excel de la pantalla no cambian."""
    fuente = inspect.getsource(pl_api.get_pl_compare)
    assert "if m_col != month else sid" in fuente
    assert "if m_col == month else" in fuente


# ── La pantalla ────────────────────────────────────────────────────────────

def _front() -> str:
    return FRONT.read_text(encoding="utf-8", errors="replace")


def test_cada_ranura_tiene_su_mes_y_se_resalta():
    txt = _front()
    assert "const [mesRanura, setMesRanura]" in txt
    assert "const claveRanura = useCallback" in txt
    # El sufijo SOLO cuando el mes es otro.
    assert "return m && m !== mes ? `${id}@${m}` : id;" in txt
    # Y se ve que esa columna dejo de ser el mes de la pantalla.
    assert '"1px solid var(--brand)" : SEL.border' in txt


def test_el_gasto_de_una_columna_usa_SU_mes():
    """⚠️ `/pl/compare/` ya viene calculado por su mes, pero el gasto por clase
    trae los DOCE y hay que decirle cual mirar.

    Sin esto, una columna de agosto mostraba su ingreso de agosto contra su
    gasto de setiembre: dos meses dentro de la misma columna, y el GOP
    resultante no es el de ningun mes.
    """
    txt = _front()
    assert "const mCol = mesDeRanura(idx);" in txt
    assert 'const hasta = horizonte === "month" ? [mCol]' in txt
    assert 'clase(g, "payroll", h, mCol)' in txt
    assert "dato(vA, gA, f.code, bl.h, mesDeRanura(varA))" in txt


def test_las_dos_fuentes_se_buscan_con_SU_llave():
    """`datos` viene de /pl/compare/ y su llave lleva el mes; `gastos` trae los
    doce meses y su llave es el id pelado. Buscarlos con la misma llave dejaba
    una de las dos columnas vacia."""
    txt = _front()
    assert "datos.find(d => d.scenario_id === claveRanura(varA))" in txt
    assert "gastos.find(g => g.scenario_id === idA)" in txt


def test_cambiar_el_mes_vuelve_a_pedir_el_dato():
    """Sin `claveRanura` en las dependencias, cambiar el mes de una ranura no
    pedia nada y la columna seguia mostrando el mes viejo con el rotulo nuevo
    — que es peor que no tener la funcion."""
    txt = _front()
    assert "}, [ranuras, mes, t, claveRanura]);" in txt


def test_los_sub_tabs_que_NO_lo_soportan_lo_DICEN():
    """⚠️ Lo que no se puede dejar pasar.

    El mes por ranura vale en el P&L Statement. Si otro sub-tab mostrara el mes
    de la pantalla sin avisar, el owner leeria agosto donde dice agosto y
    setiembre donde tambien dice agosto. Un cuadro que miente callado es peor
    que una funcion que falta.
    """
    txt = _front()
    assert 'vista !== "estado" && (' in txt
    assert "El mes por columna aplica por" in txt
    assert '"1px solid var(--negative)"' in txt


def test_el_selector_no_aparece_en_una_ranura_vacia():
    """Un selector de mes sobre una ranura sin escenario no hace nada."""
    txt = _front()
    i = txt.index("const [mesRanura")
    assert re.search(r"\{id && \(\s*\n\s*<select value=\{mesRanura\[i\]\}",
                     txt[i:]), "el selector de mes no esta condicionado a `id`"
