# -*- coding: utf-8 -*-
"""Socios del Club Madresal: estadístico, no plata.

El Club vende **acceso a las instalaciones** del hotel. Detrás hay un desarrollo
inmobiliario que NO es parte de este P&L; la cuota de acceso sí, y ya vive en
`REV_CLUB`. Este conteo explica de dónde sale esa cuota — pero no es dinero, así
que **no puede tocar ninguna línea del estado de resultados**.

Dos cosas que estas pruebas cuidan, y que son fáciles de romper sin darse cuenta:

1. **El total del año es DICIEMBRE, no la suma.** Sumar 121 + 121 + 123… daría
   1.500 socios donde hay 129. Es una de las cuatro filas no aditivas del Excel
   de Amarena (`ESCANEO_03` §5.13).
2. **Se apaga desde Provisionamiento.** El owner avisó que esto desaparece
   cuando el Club se opere por fuera del hotel. Si alguien lo ata a un
   `if hotel == "AMA"`, ese día hay que tocar código — y el que lo toque no va
   a saber por qué existe.
"""
import inspect
import pathlib

import pytest

from app.api import club_stats_api as mod
from app.api.club_stats_api import CAMPOS, ETIQUETAS, cierre


# ── El total del año NO es la suma ───────────────────────────────────────────

TODO_EL_ANIO = set(range(1, 13))


def test_el_total_del_anio_es_diciembre_no_la_suma():
    """El caso real del Excel del owner: 121…129 socios. La suma daría 867."""
    meses = [0, 0, 0, 0, 0, 121, 121, 121, 123, 125, 127, 129]
    assert cierre(meses, TODO_EL_ANIO) == 129
    assert cierre(meses, TODO_EL_ANIO) != sum(meses)


def test_cero_en_diciembre_ES_la_respuesta_cuando_diciembre_esta_cargado():
    """El caso que se me pasó y apareció con el dato real del owner: los 35
    «Condicionados» se convierten en «Pagando» en septiembre, así que diciembre
    vale 0 — y su Excel muestra 0.

    Una versión anterior devolvía «el último mes con dato» y esta línea mostraba
    **35 condicionados que ya no existen**. Cero es una respuesta, no un hueco."""
    condicionados = [0, 0, 0, 0, 0, 35, 35, 35, 0, 0, 0, 0]
    assert cierre(condicionados, TODO_EL_ANIO) == 0


def test_si_diciembre_no_esta_cargado_manda_el_ultimo_mes_que_si():
    """Año en curso: no hay fila de diciembre. Mostrar 0 cuando hay 129 socios
    en agosto sería inventar una baja que no pasó."""
    meses = [0, 0, 0, 0, 0, 0, 0, 129, 0, 0, 0, 0]
    assert cierre(meses, {6, 7, 8}) == 129


def test_la_diferencia_entre_ausente_y_cero():
    """La misma fila da distinto según diciembre esté cargado o no. Eso es lo
    que la versión anterior no distinguía."""
    meses = [0, 0, 0, 0, 0, 35, 35, 35, 0, 0, 0, 0]
    assert cierre(meses, TODO_EL_ANIO) == 0      # diciembre cargado y en cero
    assert cierre(meses, {6, 7, 8}) == 35        # diciembre sin cargar


def test_sin_ningun_mes_cargado_da_cero():
    assert cierre([0] * 12, set()) == 0


# ── Los cuatro conceptos, con los nombres del Excel ──────────────────────────

def test_estan_los_cuatro_conceptos():
    assert CAMPOS == ("total", "condicionados", "pagando", "acuerdo_pago")
    assert set(ETIQUETAS) == set(CAMPOS)
    assert ETIQUETAS["total"] == "Total Membresías"
    assert ETIQUETAS["acuerdo_pago"] == "Membresías En acuerdo de pago"


# ── Se apaga desde Provisionamiento, no desde el código ──────────────────────

def test_la_visibilidad_sale_de_la_matriz_y_no_de_un_if_por_hotel():
    """El owner: «debe desaparecer una vez que llegue club por fuera, solo es
    para Amarena». Si esto se ata al nombre del hotel, ese día hay que tocar
    código; atado al provisionamiento, se desmarca una casilla."""
    src = inspect.getsource(mod.club_visible)
    assert "dept_apagado(" in src, "la visibilidad tiene que salir del provisionamiento"
    assert "AMA" not in src and "Amarena" not in src, (
        "no puede depender del nombre del hotel")
    assert mod.DEPT_CLUB == "260"


def test_una_propiedad_sin_marcas_lo_tiene_prendido():
    """El default del sistema es «todo activo, se DESMARCA lo que no aplica».
    Si esto naciera apagado, una propiedad nueva no vería el Club sin que nadie
    hubiera decidido esconderlo.

    La regla vive en `_apagados.py` desde que la comparten el Club y las
    pantallas de carga: se pregunta quién está APAGADO, así que la ausencia de
    fila es «prendido» por construcción.
    """
    from app.api import _apagados
    src = inspect.getsource(_apagados.dept_apagado)
    assert "enabled.is_(False)" in src
    assert "is not None" in src, "sin fila = prendido"


# ── No toca el P&L ───────────────────────────────────────────────────────────

def test_el_conteo_no_entra_en_ninguna_linea_del_pl():
    """Es un estadístico. Si apareciera en el motor, 129 socios se sumarían a
    algún total en dólares."""
    motor = pathlib.Path(mod.__file__).parent.parent / "engine"
    ofensores = [p.name for p in motor.rglob("*.py")
                 if "club_membership" in p.read_text(encoding="utf-8")
                 or "ClubMembershipStat" in p.read_text(encoding="utf-8")]
    assert not ofensores, f"el motor no puede leer el conteo de socios: {ofensores}"


def test_el_reporte_lo_lleva_aparte_de_las_lineas():
    """En el P&L Full Detail va en su propia llave `club`, al lado de los KPIs
    — no mezclado con `resumen`, `bloques` ni `propiedad`."""
    from app.api import pl_full_detail_api as rep
    src = inspect.getsource(rep.pl_full_detail)
    assert '"club": club' in src
    assert "club_visible" in src


# ── El guardado ──────────────────────────────────────────────────────────────

def test_guardar_no_pisa_los_meses_que_no_vienen():
    """Mandar enero no puede borrar febrero: el owner carga mes a mes."""
    src = inspect.getsource(mod.guardar_membresias)
    assert "for m in body.meses" in src
    assert "delete" not in src.lower(), "no debe borrar nada"


def test_no_se_puede_escribir_en_una_version_enllavada():
    src = inspect.getsource(mod.guardar_membresias)
    assert "candado(" in src


@pytest.mark.parametrize("mes", [0, 13, -1, 99])
def test_un_mes_fuera_de_rango_se_rechaza(mes):
    src = inspect.getsource(mod.guardar_membresias)
    assert "1 <= m.month <= 12" in src


# ── El driver de la cuota ────────────────────────────────────────────────────

def test_el_checkbook_ahora_tiene_linea_de_club():
    """Antes de esto, `REVENUE_LINES` iba de ROOMS a SUSTAINABILITY y no había
    por dónde meter el ingreso del Club: en el Budget 2027 `REV_CLUB` daba cero
    y parecía falta de carga."""
    from app.models.revenue_entry import REVENUE_LINES, REVENUE_LINE_LABELS
    assert "CLUB" in REVENUE_LINES
    # El rótulo es el del catálogo (cuenta 4500 del depto 260), no uno inventado
    # acá; `test_club_tres_lineas_de_ingreso.py` lo compara contra el mapeo.
    assert REVENUE_LINE_LABELS["CLUB"] == "Ingreso Madresal Club"


def test_el_motor_de_ingresos_lleva_el_club_hasta_el_pl():
    """La cadena completa: campo en RevenueResult → dict de líneas → REV_CLUB.
    Si se corta en cualquier punto, el ingreso se calcula y no llega."""
    from app.engine.revenue_calculator import RevenueResult
    from app.engine.recalculate import revenue_line_dict
    from app.engine.pl_engine import REVENUE_LINE_TO_REPORT_LINE

    r = RevenueResult(month=1, year=2027)
    r.club = 5000
    assert revenue_line_dict(r)["club"] == 5000
    assert REVENUE_LINE_TO_REPORT_LINE["club"] == "REV_CLUB"


def test_la_linea_del_checkbook_mapea_al_campo_club():
    from app.engine.recalculate import _REVENUE_LINE_TO_FIELD
    assert _REVENUE_LINE_TO_FIELD["CLUB"] == "club"


def test_la_base_por_defecto_son_los_que_pagan():
    """Los condicionados, por definición, todavía no pagan cuota. Multiplicar
    por el total inventaría ingreso."""
    from app.models.club_fee_budget import BASES, ClubFeeBudget
    assert BASES[0] == "pagando"
    assert ClubFeeBudget.__table__.c["base"].default.arg == "pagando"


def test_quien_paga_es_configurable_y_no_una_constante():
    """Quién paga es regla del negocio del Club, no del software: tiene que
    poder cambiar sin tocar código."""
    from app.models.club_fee_budget import BASES
    assert set(BASES) == set(CAMPOS), (
        "las bases posibles son los cuatro conteos de socios")


def test_hay_puerta_para_ingreso_sin_driver():
    """El Club no vive solo de la cuota. Y esos otros ingresos no son un «otros»
    anónimo: el catálogo los lleva con nombre y cuenta propia, así que cada uno
    tiene su columna."""
    from app.models.club_fee_budget import ClubFeeBudget
    assert "actividad_usd" in ClubFeeBudget.__table__.c    # 4501
    assert "visitantes_usd" in ClubFeeBudget.__table__.c   # 4502


def test_guardar_la_cuota_deposita_el_ingreso_donde_el_pl_lo_lee():
    """Si el cálculo se quedara en su tabla, la pantalla mostraría un ingreso
    que el P&L no ve. Tiene que aterrizar en las líneas de ingreso — en las DOS
    fuentes, porque hay dos modos y el Club no tiene por qué saber en cuál está
    su escenario. El camino es el compartido (`_ingreso_de_driver.py`), no una
    escritura propia; ver `tests/test_los_drivers_llegan_al_pl.py`."""
    src = inspect.getsource(mod.guardar_cuota)
    assert "persistir_ingreso_de_driver(" in src
    assert "_montos_por_linea(filas)" in src, "cada fuente va a SU línea"
    assert "candado(" in src, "no se escribe en una versión enllavada"


def test_el_ingreso_es_la_cuota_mas_las_otras_dos_fuentes():
    src = inspect.getsource(mod._driver_filas)
    assert "cuota = n * precio" in src
    assert "cuota + actividad + visitantes" in src


def test_cada_fuente_va_a_su_propia_linea():
    """Mandarlas todas a CLUB daría el mismo total en el P&L, pero el reporte
    cuenta por cuenta mostraría un bulto en la 4500 donde la contabilidad tiene
    tres renglones."""
    destinos = mod._montos_por_linea([
        {"cuotas": 10.0, "actividad": 20.0, "visitantes": 30.0}])
    assert destinos["CLUB"] == [10.0]
    assert destinos["CLUB_ACTIVIDAD"] == [20.0]
    assert destinos["CLUB_VISITANTES"] == [30.0]


def test_la_cuota_llega_al_pl_en_los_dos_modos():
    """El agujero que casi se va vivo a producción, y que ya no está.

    La cuota se escribía **solo** en la línea CLUB del checkbook, y un escenario
    en modo `drivers` arma los ingresos con tarifas y ocupación sin mirar esas
    líneas: uno guardaba, la pantalla mostraba el ingreso y el P&L seguía en
    cero — sin un solo error. Costaba $125.180 al año y dejó al `BUDGET Working
    2027` fuera de la migración 116.

    Owner, 2026-08-15: «solo quiero que trabaje **estándar como todos los
    departamentos**». Hoy el ingreso se deposita en las dos fuentes, así que la
    respuesta es `True` en los dos modos.
    """
    class _Esc:
        revenue_source = "drivers"
    assert mod.llega_al_pl(_Esc()) is True
    _Esc.revenue_source = "checkbook"
    assert mod.llega_al_pl(_Esc()) is True


def test_el_modo_viaja_en_la_respuesta():
    """De nada sirve la regla si la pantalla no la recibe. Se sigue publicando
    aunque hoy dé siempre `True`: el día que haya una tercera fuente, la
    pantalla se entera sin que nadie se acuerde de volver a mandarlo."""
    src = inspect.getsource(mod.leer_cuota)
    assert '"llega_al_pl"' in src
    assert '"modo_ingresos"' in src
