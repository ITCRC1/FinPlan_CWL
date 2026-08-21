# -*- coding: utf-8 -*-
"""
LAS GUARDAS DEL BREAK-EVEN — cada una es una forma de mentir con un cero.

Spec §2.6 y §3.4. El hilo común: **ninguna respuesta puede ser un cero que se
lea como un resultado.** Un equilibrio en cero, un margen en blanco o una cuenta
asumida variable se ven todos como números normales, y ahí está el peligro: el
error no rompe nada, solo da una respuesta mejor de la que corresponde.
"""
from decimal import Decimal

import pytest

from app.engine import break_even as be

D = Decimal


def regla(slug="rooms", dept="0110", acct="6000", linea="OPEX_ROOMS",
          pct="1", **kw):
    return be.Regla(slug, dept, acct, linea, D(pct), **kw)


def monto(dept="0110", acct="6000", linea="OPEX_ROOMS", amt="100"):
    return be.Monto(dept, acct, linea, D(amt))


# ─── §3.3 · data_version es obligatorio y no tiene default ───────────────────

@pytest.mark.parametrize("v", [None, "", "budget", "PRESUPUESTO", "ACTUALES"])
def test_sin_data_version_valido_la_llamada_falla(v):
    """No hay valor implícito, y el motivo está escrito en el mensaje: un
    equilibrio calculado sobre la versión equivocada **se ve idéntico** a uno
    correcto. Si el motor eligiera una por default, nadie se enteraría nunca."""
    with pytest.raises(be.VersionDeDatoRequerida):
        be.calcular(data_version=v, revenue=D("100"), montos=[], reglas=[])


@pytest.mark.parametrize("v", ["ACTUAL", "BUDGET", "FORECAST"])
def test_las_tres_versiones_validas_pasan(v):
    assert be.calcular(data_version=v, revenue=D("100"),
                       montos=[], reglas=[]) is not None


# ─── §2.6 · la resolución en tres pasos ──────────────────────────────────────

def test_1_gana_la_coincidencia_exacta():
    r = be.calcular(data_version="BUDGET", revenue=D("1000"),
                    montos=[monto(amt="100")],
                    reglas=[regla(pct="1"),
                            regla(acct="", pct="0", map_source="LINEA")])
    assert r.variable_cost == D("100"), "la exacta le gana a la de línea"


def test_2_sin_exacta_resuelve_por_linea():
    r = be.calcular(data_version="BUDGET", revenue=D("1000"),
                    montos=[monto(acct="7777", amt="100")],
                    reglas=[regla(acct="", pct="1", map_source="LINEA")])
    assert r.variable_cost == D("100")
    assert r.sin_clasificar == []


def test_3_sin_regla_es_100_PCT_FIJO_y_queda_registrada():
    """La regla que más plata protege.

    El catálogo GL crece. Una cuenta nueva **asumida variable** infla el margen
    de contribución y **baja** el equilibrio: el error se ve como una buena
    noticia y nadie lo busca. Por eso va a fijo, y por eso queda en la lista.
    """
    r = be.calcular(data_version="BUDGET", revenue=D("1000"),
                    montos=[monto(acct="9999", amt="100")], reglas=[regla()])
    assert r.variable_cost == D("0")
    assert r.fixed_cost == D("100")
    assert [(s.account, s.amount) for s in r.sin_clasificar] == [("9999", D("100"))]


def test_una_regla_sin_monto_sale_como_huerfana():
    """El espejo: la cuenta se borró o se renombró en el master data y la regla
    quedó apuntando al vacío. La UI la ofrece para archivar."""
    r = be.calcular(data_version="BUDGET", revenue=D("1000"),
                    montos=[], reglas=[regla(dept="0110", acct="6000")])
    assert r.reglas_huerfanas == ["0110:6000"]


# ─── §3.4 · las guardas ──────────────────────────────────────────────────────

def test_margen_negativo_devuelve_None_con_motivo_y_no_cero():
    """Un cero acá se lee como «el equilibrio es cero», que es lo contrario de
    lo que pasa: con margen negativo NINGÚN nivel de ingreso alcanza."""
    r = be.calcular(data_version="BUDGET", revenue=D("100"),
                    montos=[monto(amt="200")], reglas=[regla(pct="1")])
    assert r.cm_pct <= 0
    assert r.be_revenue is None
    assert r.be_occupancy is None
    assert r.motivo == be.MSG_MC_NEGATIVO


def test_sin_ingreso_los_ratios_van_en_cero_sin_dividir_por_cero():
    r = be.calcular(data_version="BUDGET", revenue=D("0"),
                    montos=[monto(amt="100")], reglas=[regla(pct="0")])
    assert r.cm_pct == D("0")
    assert r.be_revenue is None
    assert "no hay ingreso" in r.motivo


def test_sin_habitaciones_las_metricas_de_cuarto_van_en_None_no_en_cero():
    """Cero noches de equilibrio es una afirmación: «no necesitás vender nada».
    `None` es la verdad: no hay con qué calcularlo."""
    r = be.calcular(data_version="BUDGET", revenue=D("1000"),
                    revenue_rooms=D("500"), montos=[monto(amt="100")],
                    reglas=[regla(pct="0")], adr=D("0"), rooms_available=D("0"))
    assert r.be_revenue is not None, "el equilibrio en dólares sí se puede"
    assert r.be_occupancy is None
    assert r.be_room_nights is None
    assert r.be_trevpar is None


def test_con_EBT_cero_el_apalancamiento_es_None_y_no_un_numero_gigante():
    """DOL = CM/EBT. Con EBT = 0 es infinito; devolver 10^9 lo haría pasar por
    un dato."""
    r = be.calcular(data_version="BUDGET", revenue=D("1000"),
                    montos=[monto(amt="1000")], reglas=[regla(pct="0.5")])
    assert r.ebt == D("0")
    assert r.operating_leverage is None


# ─── §2.5 · el impuesto ──────────────────────────────────────────────────────

def test_lo_excluido_no_toca_ni_variable_ni_fijo_pero_si_el_neto():
    r = be.calcular(data_version="BUDGET", revenue=D("1000"),
                    montos=[monto(acct="8060", amt="300")],
                    reglas=[regla(acct="8060", pct="0", excluded_from_be=True)])
    assert r.variable_cost == D("0") and r.fixed_cost == D("0")
    assert r.excluded_cost == D("300")
    assert r.ebt == D("1000")
    assert r.net == D("700")


def test_la_exclusion_es_la_bandera_y_no_el_texto_de_la_seccion():
    """Con `be_section == 'INCOME TAX'` bastaría renombrar la sección para que
    la exclusión deje de aplicar y el equilibrio salte $113k sin aviso."""
    r = be.calcular(data_version="BUDGET", revenue=D("1000"),
                    montos=[monto(acct="8060", amt="300")],
                    reglas=[regla(acct="8060", pct="0",
                                  be_section="INCOME TAX",
                                  excluded_from_be=False)])
    assert r.excluded_cost == D("0"), "manda la bandera, no el rótulo"
    assert r.fixed_cost == D("300")


# ─── El % fijo es DERIVADO, nunca almacenado ─────────────────────────────────

@pytest.mark.parametrize("pct", ["0", "0.25", "0.5", "0.75", "1"])
def test_variable_mas_fijo_es_siempre_el_monto(pct):
    """No se guardan dos porcentajes justamente para que esto no pueda fallar."""
    r = be.calcular(data_version="BUDGET", revenue=D("1000"),
                    montos=[monto(amt="400")], reglas=[regla(pct=pct)])
    assert r.variable_cost + r.fixed_cost == D("400")


def test_el_prorrateo_mensual_es_la_doceava_parte_y_se_llama_lineal():
    """El nombre del campo lleva `linear` a propósito: en CWL la ocupación va de
    52% en febrero a 0,7% en septiembre, así que un umbral plano no describe
    ningún mes. La UI tiene que rotularlo, y el campo se lo recuerda."""
    r = be.calcular(data_version="BUDGET", revenue=D("1000"),
                    montos=[monto(amt="200")], reglas=[regla(pct="0")])
    assert r.be_revenue_monthly_linear == r.be_revenue / D("12")
    assert "linear" in "be_revenue_monthly_linear"


# ─── §3.4 · el apalancamiento cuando el resultado es casi cero ───────────────
#
# El owner vio **−3.213,1x** en el `FORECAST April 2026` y preguntó qué era eso.
# Era `CM / EBT` con EBT = −993 sobre $5,19 M de ingreso: aritmética correcta,
# información nula. El cociente tiende a infinito según el resultado se acerca a
# cero, y a esa distancia el SIGNO lo decide un redondeo.

def _con_resultado(revenue, variable, fijo):
    reglas = [be.Regla("rooms", "0110", "6000", "OPEX_ROOMS", D("1")),
              be.Regla("rooms", "0110", "7000", "OPEX_ROOMS", D("0"))]
    montos = [be.Monto("0110", "6000", "OPEX_ROOMS", D(variable)),
              be.Monto("0110", "7000", "OPEX_ROOMS", D(fijo))]
    return be.calcular(data_version="FORECAST", revenue=D(revenue),
                       montos=montos, reglas=reglas)


def test_ebt_casi_cero_no_muestra_un_apalancamiento_gigante():
    """El caso exacto de la pantalla: EBT = −993 sobre 5.191.809."""
    r = _con_resultado("5191809", "2002775", "3190026")
    assert r.ebt == D("-992")  # el que se ve en pantalla, redondeado
    assert r.operating_leverage is None
    assert "ruido" in r.operating_leverage_motivo
    # Y lo que SÍ informa sigue estando, que es el punto de sacar el otro:
    assert r.margin_of_safety is not None


def test_el_apalancamiento_sigue_saliendo_cuando_significa_algo():
    """La contracautela: el umbral no puede comerse el caso normal.

    La prueba de aceptación tiene EBT = 5,7% del ingreso y **11,6x**. Si esta se
    cae, el umbral está apagando el dato en vez de apagar el ruido."""
    r = _con_resultado("4373146", "1469297", "2653628")
    assert r.operating_leverage is not None
    assert r.operating_leverage_motivo == ""
    assert 11 < float(r.operating_leverage) < 12


def test_el_cero_exacto_dice_infinito_no_ruido():
    """Los dos motivos son distintos porque las dos situaciones lo son: en el
    cero exacto el apalancamiento **es** infinito; cerca del cero, es indefinido
    en la práctica. Un solo mensaje para las dos mentiría en una."""
    r = _con_resultado("1000000", "400000", "600000")
    assert r.ebt == 0
    assert r.operating_leverage is None
    # El motor pone la CLAVE; el texto vive en `app/textos.py`. Se comprueba
    # el criterio donde vive ahora, y en los dos idiomas.
    from app.textos import t

    assert r.operating_leverage_motivo == "be.apalancamiento_en_el_equilibrio"
    assert "infinito por definición" in t("es", r.operating_leverage_motivo)
    assert "infinite by definition" in t("en", r.operating_leverage_motivo)
