# -*- coding: utf-8 -*-
"""
FASE 2 — la matriz de sensibilidad y el equilibrio mensual con estacionalidad.

Las dos pruebas que de verdad importan acá no son las de rangos: son las **dos
de coherencia**, que atan la matriz al resto del modelo.

1. `test_en_el_punto_del_presupuesto_la_matriz_da_el_EBT_del_PL` — con la
   ocupación y el ADR reales (factor 1,0), la celda tiene que dar **el mismo
   resultado antes de impuestos que el P&L**. Si no, la matriz está midiendo
   otra cosa y nadie lo notaría: 153 celdas plausibles se leen igual de bien
   estando bien que estando mal.

2. `test_en_la_ocupacion_de_equilibrio_el_resultado_es_cero` — a la ocupación de
   equilibrio, el EBT tiene que ser 0. Es la definición misma de punto de
   equilibrio, y cruza la matriz contra `be_occupancy`, que se calcula por otro
   camino.

Juntas cierran la matriz por sus dos extremos conocidos.
"""
from decimal import Decimal

import pytest

from app.engine import break_even as be

D = Decimal

# Los parámetros del modelo de referencia (hoja PARAMETROS / INGRESOS).
CM_PCT = D("0.6640181")
FC = D("2653700.85")
ROOMS_AVAIL = D("10950")
ADR = D("493.5156")
MIX = D("0.4855094")
OCC_PRESUP = D("0.3928950")     # 4.302,2 / 10.950
EBT_REF = D("250147.68")


# ─── Coherencia: los dos extremos conocidos ──────────────────────────────────

def test_en_el_punto_del_presupuesto_la_matriz_da_el_EBT_del_PL():
    """La celda del presupuesto tiene que reproducir el resultado real."""
    m = be.sensibilidad(cm_pct=CM_PCT, fixed_cost=FC, rooms_available=ROOMS_AVAIL,
                        adr=ADR, rooms_mix=MIX,
                        ocupaciones=[OCC_PRESUP], factores_adr=[D("1.0")])
    assert abs(m.celdas[0][0] - EBT_REF) < D("5"), (
        f"la matriz da {m.celdas[0][0]:,.2f} donde el P&L da {EBT_REF:,.2f}")


def test_en_la_ocupacion_de_equilibrio_el_resultado_es_cero():
    """A la ocupación de equilibrio (35,905%), el EBT es 0 — por definición."""
    occ_be = D("0.35905")
    m = be.sensibilidad(cm_pct=CM_PCT, fixed_cost=FC, rooms_available=ROOMS_AVAIL,
                        adr=ADR, rooms_mix=MIX,
                        ocupaciones=[occ_be], factores_adr=[D("1.0")])
    assert abs(m.celdas[0][0]) < D("100"), (
        f"a la ocupación de equilibrio el resultado debería ser ~0 y da "
        f"{m.celdas[0][0]:,.2f}")


def test_cuanto_cuesta_cada_punto_de_ocupacion():
    """El titular del módulo, MEDIDO — y no es exactamente lo que dice el spec.

    El spec (y el RESUMEN del Excel) afirman que **«tres puntos de ocupación
    borran el resultado del año»**. Medido con la matriz:

        −0 pp   ocup 39,29%   EBT   250.146
        −1 pp   ocup 38,29%   EBT   176.237
        −2 pp   ocup 37,29%   EBT   102.329
        −3 pp   ocup 36,29%   EBT  **28.420**   ← todavía POSITIVO
        −3,385  ocup 35,90%   EBT         0     ← acá cruza
        −4 pp   ocup 35,29%   EBT   −45.489

    Tres puntos se llevan el **89%** del resultado, no el 100%. El número que
    borra el año es **3,385 pp**, que es exactamente la holgura que el propio
    modelo reporta (39,289% presupuestada − 35,905% de equilibrio).

    No cambia la conclusión —el negocio es frágil— pero la frase redondeada
    hacia abajo dice algo más fuerte de lo que el modelo sostiene, y esta prueba
    existe para que nadie la vuelva a citar sin medirla.
    """
    def ebt(pp: str):
        m = be.sensibilidad(cm_pct=CM_PCT, fixed_cost=FC,
                            rooms_available=ROOMS_AVAIL, adr=ADR, rooms_mix=MIX,
                            ocupaciones=[OCC_PRESUP - D(pp) / 100],
                            factores_adr=[D("1.0")])
        return m.celdas[0][0]

    assert ebt("3") > 0, "tres puntos NO borran el resultado: quedan ~28.400"
    assert abs(ebt("3.385")) < D("1000"), "el cero está en 3,385 pp"
    assert ebt("4") < 0
    # Cada punto cuesta ~74.000, y es lineal: la matriz escala el ingreso.
    assert abs((ebt("0") - ebt("1")) - (ebt("1") - ebt("2"))) < D("1")


# ─── La matriz del modelo de referencia ──────────────────────────────────────

def test_los_rangos_por_defecto_reproducen_la_hoja():
    m = be.sensibilidad(cm_pct=CM_PCT, fixed_cost=FC, rooms_available=ROOMS_AVAIL,
                        adr=ADR, rooms_mix=MIX)
    assert len(m.ocupaciones) == 17, "20% a 60% en pasos de 2,5 pp"
    assert len(m.factores_adr) == 9, "0,80 a 1,20 en pasos de 0,05"
    assert m.ocupaciones[0] == D("0.20") and m.ocupaciones[-1] == D("0.60")
    assert m.factores_adr[0] == D("0.80") and m.factores_adr[-1] == D("1.20")


def test_la_matriz_crece_en_las_dos_direcciones():
    """Más ocupación y más tarifa dan más resultado: si alguna vez se invierte,
    hay un signo cambiado y el semáforo pintaría al revés."""
    m = be.sensibilidad(cm_pct=CM_PCT, fixed_cost=FC, rooms_available=ROOMS_AVAIL,
                        adr=ADR, rooms_mix=MIX)
    for i in range(len(m.ocupaciones) - 1):
        assert m.celdas[i + 1][0] > m.celdas[i][0]
    for j in range(len(m.factores_adr) - 1):
        assert m.celdas[0][j + 1] > m.celdas[0][j]


def test_la_celda_del_presupuesto_se_marca_en_el_paso_mas_cercano():
    """39,289% no cae justo en un paso de 2,5 pp: se marca el más cercano (40%),
    y por eso el valor de ESA celda no es el EBT del P&L."""
    m = be.sensibilidad(cm_pct=CM_PCT, fixed_cost=FC, rooms_available=ROOMS_AVAIL,
                        adr=ADR, rooms_mix=MIX, occ_presupuestada=OCC_PRESUP)
    i, j = m.celda_presupuesto
    assert m.ocupaciones[i] == D("0.400")
    assert m.factores_adr[j] == D("1.00")


def test_sin_mezcla_ni_ADR_la_matriz_no_se_inventa():
    """Devuelve celdas en `None` con motivo, no una matriz de ceros — que se
    leería como «el resultado es cero en todo escenario»."""
    m = be.sensibilidad(cm_pct=CM_PCT, fixed_cost=FC, rooms_available=ROOMS_AVAIL,
                        adr=D("0"), rooms_mix=D("0"))
    assert all(c is None for fila in m.celdas for c in fila)
    assert "no se puede calcular" in m.motivo


# ─── Equilibrio mensual con estacionalidad ───────────────────────────────────

def _mes(n: int, revenue: str, costo: str, pct_var: str = "0.5") -> be.Resultado:
    r = be.calcular(
        data_version="BUDGET", revenue=D(revenue),
        montos=[be.Monto("0110", "6000", "OPEX_ROOMS", D(costo))],
        reglas=[be.Regla("rooms", "0110", "6000", "OPEX_ROOMS", D(pct_var))])
    r.month = n
    return r


def test_el_mensual_ya_no_es_la_doceava_parte():
    """Lo que la Fase 2 viene a arreglar: en la Fase 1 los doce meses tenían el
    MISMO umbral (~$333.036), y en CWL la ocupación va de 52% en febrero a 0,7%
    en septiembre. Con estacionalidad, cada mes tiene el suyo."""
    filas = be.equilibrio_mensual([
        _mes(1, "500000", "200000"), _mes(2, "800000", "260000"),
        _mes(9, "20000", "40000")])
    umbrales = [f.be_revenue for f in filas if f.be_revenue is not None]
    assert len(set(umbrales)) > 1, "los meses no pueden compartir un solo umbral"


def test_un_mes_sin_equilibrio_sale_en_None_con_motivo_y_no_en_cero():
    """Septiembre en CWL: el margen no cubre el costo fijo a ningún volumen.

    Rellenarlo con cero diría «este mes no necesita vender nada»; rellenarlo con
    el promedio anual inventaría que el mes cierra. Las dos son mentiras que se
    leen como un número normal.
    """
    filas = be.equilibrio_mensual([_mes(9, "10000", "60000", pct_var="1")])
    f = filas[0]
    assert f.be_revenue is None
    assert f.motivo == be.MSG_MC_NEGATIVO


def test_la_holgura_dice_si_el_mes_cierra():
    # Septiembre: ingreso chico contra un costo casi todo fijo — el mes no
    # llega a su umbral aunque el margen siga siendo positivo.
    filas = be.equilibrio_mensual([
        _mes(2, "800000", "200000", "0.5"), _mes(9, "60000", "90000", "0.2")])
    feb, sep = filas
    assert feb.holgura > 0, "febrero cierra"
    assert sep.holgura < 0, "septiembre no llega a su equilibrio"


def test_la_suma_de_los_doce_no_es_el_equilibrio_anual():
    """Es la trampa de lectura de esta pantalla, y por eso el endpoint manda una
    nota: un mes que no llega se compensa con otro que se pasa, y el anual
    reparte el costo fijo sobre el margen de TODO el año."""
    meses = [_mes(n, "300000", "150000") for n in range(1, 13)]
    filas = be.equilibrio_mensual(meses)
    suma = sum((f.be_revenue for f in filas if f.be_revenue), D("0"))
    anual = be.calcular(
        data_version="BUDGET", revenue=D("3600000"),
        montos=[be.Monto("0110", "6000", "OPEX_ROOMS", D("1800000"))],
        reglas=[be.Regla("rooms", "0110", "6000", "OPEX_ROOMS", D("0.5"))])
    # En este caso construido dan igual porque los doce meses son idénticos; lo
    # que la prueba fija es que se calculan por caminos distintos y que la nota
    # existe para cuando NO coincidan.
    assert suma > 0 and anual.be_revenue > 0
    assert filas[0].be_revenue == filas[-1].be_revenue


def test_el_mensual_usa_el_mismo_motor_que_el_anual():
    """`equilibrio_mensual` recibe `Resultado` ya calculados, no montos crudos:
    así el mes y el año no pueden divergir por tener dos implementaciones."""
    r = _mes(3, "400000", "100000")
    f = be.equilibrio_mensual([r])[0]
    assert f.be_revenue == r.be_revenue
    assert f.cm_pct == r.cm_pct
    assert f.fixed_cost == r.fixed_cost


# ─── Las celdas del modelo de referencia, al centavo ─────────────────────────
#
# Extraídas de la hoja SENSIBILIDAD del `BREAK_EVEN_CWL.xlsx`. Con estas la
# matriz deja de ser «parece razonable»: o reproduce el Excel o no.
#
# Las constantes son las EXACTAS del libro, no las redondeadas:
CM_EXACTO = D("0.664018265607422")
FC_EXACTO = D("2653700.85")
ADR_EXACTO = D("493.515552693971")
MIX_EXACTO = D("0.485509247490038")

#: (ocupación, factor de ADR) -> resultado antes de impuestos
CELDAS_REF = {
    # las cuatro esquinas
    ("0.200", "0.80"): "-1471156.42", ("0.200", "1.20"): "-879884.21",
    ("0.600", "0.80"): "893932.43",   ("0.600", "1.20"): "2667749.06",
    # la fila de 35% entera — cruza el cero entre 1,00 y 1,05
    ("0.350", "0.80"): "-584248.11", ("0.350", "0.85"): "-454907.31",
    ("0.350", "0.90"): "-325566.51", ("0.350", "0.95"): "-196225.72",
    ("0.350", "1.00"): "-66884.92",  ("0.350", "1.05"): "62455.88",
    ("0.350", "1.10"): "191796.67",  ("0.350", "1.15"): "321137.47",
    ("0.350", "1.20"): "450478.27",
    # las tres más cercanas al cero de toda la matriz
    ("0.325", "1.10"): "-11453.15", ("0.425", "0.85"): "16262.74",
    ("0.375", "0.95"): "-20691.78",
    # la celda de la grilla más cercana al presupuesto
    ("0.400", "1.00"): "302660.21",
    # la diagonal iso-utilidad: k = occ × factor = 0,36 en las tres
    ("0.300", "1.20"): "7024.11", ("0.400", "0.90"): "7024.11",
    ("0.450", "0.80"): "7024.11",
}


@pytest.mark.parametrize("clave,esperado", sorted(CELDAS_REF.items()))
def test_las_celdas_reproducen_el_modelo_de_referencia(clave, esperado):
    occ, adr_f = clave
    m = be.sensibilidad(cm_pct=CM_EXACTO, fixed_cost=FC_EXACTO,
                        rooms_available=ROOMS_AVAIL, adr=ADR_EXACTO,
                        rooms_mix=MIX_EXACTO,
                        ocupaciones=[D(occ)], factores_adr=[D(adr_f)])
    real = m.celdas[0][0]
    assert abs(real - D(esperado)) < D("0.5"), (
        f"ocupación {occ} × ADR {adr_f}: el Excel da {esperado} y el motor "
        f"{real:,.2f}")


def test_la_celda_solo_depende_del_PRODUCTO_ocupacion_por_tarifa():
    """La invariante que delata un signo o un factor mal puesto.

    La fórmula se reduce a `PBT(k) = pendiente · k − FC` con `k = ocupación ×
    factor`. O sea que **(0,30 × 1,20), (0,40 × 0,90) y (0,45 × 0,80) tienen que
    dar el mismo número** — los tres son k = 0,36. Si alguna vez dejan de
    coincidir, hay un término que no está multiplicando donde debe, y eso en una
    matriz de 153 celdas plausibles no se ve a ojo.
    """
    vals = []
    for occ, f in (("0.300", "1.20"), ("0.400", "0.90"), ("0.450", "0.80")):
        m = be.sensibilidad(cm_pct=CM_EXACTO, fixed_cost=FC_EXACTO,
                            rooms_available=ROOMS_AVAIL, adr=ADR_EXACTO,
                            rooms_mix=MIX_EXACTO,
                            ocupaciones=[D(occ)], factores_adr=[D(f)])
        vals.append(m.celdas[0][0])
    assert max(vals) - min(vals) < D("0.5"), f"k=0,36 da tres valores: {vals}"


def test_cada_punto_de_ocupacion_vale_73_909():
    """La pendiente del modelo, que es lo que hace legible el apalancamiento."""
    m = be.sensibilidad(cm_pct=CM_EXACTO, fixed_cost=FC_EXACTO,
                        rooms_available=ROOMS_AVAIL, adr=ADR_EXACTO,
                        rooms_mix=MIX_EXACTO,
                        ocupaciones=[D("0.400"), D("0.410")],
                        factores_adr=[D("1.0")])
    por_punto = (m.celdas[1][0] - m.celdas[0][0]) / D("1")
    assert abs(por_punto - D("73909.03")) < D("1"), f"da {por_punto:,.2f}"


# ─── La BASE de costo: lo que entra y lo que no ──────────────────────────────
#
# Las dos reglas de acá salieron de errores que el owner vio en pantalla antes
# que ninguna prueba. Las dos se ven igual de plausibles estando mal.

def test_las_secciones_de_costo_son_lista_BLANCA_y_no_incluyen_ingreso():
    """El error que hacía dar el equilibrio en $12,4 M.

    Las 567 reglas de la semilla son **todas de costo**. Al pasar todas las filas
    del escenario, las cuentas `4xxx` no encontraban regla y el motor las trataba
    como **100% fijas**: en el `BUDGET Final 2026` eso metió **$4.667.098 de
    ingreso dentro del costo fijo**.

    La lista es BLANCA a propósito: con una negra, una sección nueva del reporte
    entraría al costo en silencio — y acá eso **baja** el equilibrio, o sea que
    el error se ve como una buena noticia.
    """
    from app.api.break_even_api import SECCIONES_DE_COSTO
    assert "REVENUES" not in SECCIONES_DE_COSTO
    assert "KPIs" not in SECCIONES_DE_COSTO
    # Las computadas tampoco: sumarlas sería contar el mismo costo dos veces.
    for calculada in ("GOP", "EBITDA", "OPERATING PROFIT"):
        assert calculada not in SECCIONES_DE_COSTO
    # Y el impuesto SÍ entra: su regla lo marca `excluded_from_be`, así que sale
    # del costo fijo pero resta al neto. Sin él, el neto no cierra contra el P&L.
    assert "TAX / NET PROFIT" in SECCIONES_DE_COSTO


def test_un_departamento_que_REPARTE_se_reconoce_por_su_cuenta_de_distribucion():
    """Cafetería y Lavandería quedan fuera de la base, y no por una lista de códigos.

    Owner, 2026-08-17: *«no debería estar viendo cafetería ni laundry, porque ya
    están incluidos en los departamentos como gastos o como beneficios en
    planilla»*. Y tenía razón: el `0220` reparte todo su costo por la `6025` y el
    `0161` por linen/uniformes; el crédito viaja en una cuenta de distribución
    que **cancela el costo exacto** — medido, el `0220` netea 0,00 y el `0161`
    0,01.

    No se contaban dos veces, pero ensuciaban «Sin Clasificar» con 26 filas que
    sumaban un centavo, y eso hace parecer que falta clasificar plata donde no
    falta. La marca es la cuenta de distribución del propio motor del P&L, así
    que una propiedad con otro código de cafetería queda cubierta sola.
    """
    from app.engine import pl_engine
    assert pl_engine.ALLOCATION_ACCOUNTS == {"4900", "4901", "4999"}

    filas = [
        {"dept_code": "0220", "account_code": "6000", "amount": 36385.0},
        {"dept_code": "0220", "account_code": "4901", "amount": -158063.74},
        {"dept_code": "0110", "account_code": "6000", "amount": 182699.93},
    ]
    reparten = {(f["dept_code"] or "") for f in filas
                if str(f["account_code"]) in pl_engine.ALLOCATION_ACCOUNTS}
    assert reparten == {"0220"}, "el 0220 reparte; el 0110 no"


# ─── El equilibrio en NOCHES, contra la hoja del owner ───────────────────────
#
# Owner, 2026-08-17, con captura de su hoja. Junio Actual 2025 de CWL:
#   102 noches ocupadas de 900 disponibles · ingreso por noche $821,07 ·
#   costo variable por noche $864,57 · costo fijo $204.212,51
# La hoja da: contribución −43,50 · equilibrio −4.694,81 noches · −521,65% ·
# varianza 4.797.

def test_el_equilibrio_en_noches_reproduce_la_hoja_del_owner():
    r = be.equilibrio_en_noches(
        revenue=D("821.07") * 102, variable_cost=D("88185.79"),
        fixed_cost=D("204212.51"), nights_occupied=D("102"),
        nights_available=D("900"), meses=1)
    assert abs(r.revenue_per_night - D("821.07")) < D("0.01")
    assert abs(r.variable_cost_per_night - D("864.57")) < D("0.01")
    assert abs(r.contribution_per_night - D("-43.50")) < D("0.01")
    assert abs(r.be_nights - D("-4694.81")) < D("1")
    assert abs(r.be_occupancy_pct * 100 - D("-521.65")) < D("0.1")
    assert abs(r.variance_nights - D("4797")) < D("1")


def test_las_noches_negativas_se_muestran_y_se_marcan():
    """No es un signo mal puesto: es que cada noche vendida pierde plata.

    Cuando el costo variable por noche supera al ingreso por noche, **ningún
    volumen alcanza el equilibrio**. Devolver `None` o un cero escondería el dato
    más importante del mes — en el junio real de CWL es exactamente lo que pasa.
    """
    r = be.equilibrio_en_noches(
        revenue=D("100"), variable_cost=D("200"), fixed_cost=D("500"),
        nights_occupied=D("10"), nights_available=D("100"), meses=1)
    assert r.contribution_per_night < 0
    assert r.be_nights is not None and r.be_nights < 0
    assert r.pierde_por_noche is True


def test_en_noches_y_en_ingreso_son_LA_MISMA_formula():
    """La identidad que justifica preferir la de noches.

        FC / (Rev/N − VC/N) = FC·N / (Rev − VC) = N · (FC / CM%) / Rev

    O sea: `noches_equilibrio × ingreso_por_noche == ingreso_de_equilibrio`. La
    de noches llega al mismo número **sin** pasar por la mezcla de Rooms ni por
    el ADR, que son el supuesto más fuerte del modelo.
    """
    rev, vc, fc, noches = D("1000000"), D("300000"), D("400000"), D("2000")
    n = be.equilibrio_en_noches(revenue=rev, variable_cost=vc, fixed_cost=fc,
                                nights_occupied=noches, nights_available=D("5000"))
    r = be.calcular(data_version="BUDGET", revenue=rev,
                    montos=[be.Monto("0110", "6000", "OPEX_ROOMS", vc + fc)],
                    reglas=[be.Regla("rooms", "0110", "6000", "OPEX_ROOMS",
                                     vc / (vc + fc))])
    assert abs(r.variable_cost - vc) < D("0.01") and abs(r.fixed_cost - fc) < D("0.01")
    assert abs(n.be_nights * n.revenue_per_night - r.be_revenue) < D("1")


def test_sin_noches_ocupadas_no_se_inventa_un_ingreso_por_noche():
    r = be.equilibrio_en_noches(
        revenue=D("0"), variable_cost=D("0"), fixed_cost=D("1000"),
        nights_occupied=D("0"), nights_available=D("900"), meses=1)
    assert r.revenue_per_night is None and r.be_nights is None
    assert r.occupancy_pct == D("0")


def test_la_validacion_del_costo_compara_contra_el_PL():
    """⚠️ Esta prueba afirmaba la tautología, y por eso pasaba siempre.

    Decía «variable + fijo tiene que dar el total» — con el total derivado de
    esos mismos dos números dos líneas antes. No podía fallar ni con entradas
    absurdas, y mientras tanto el `BUDGET Working 2027` mostraba un neto de
    $2.882.508 contra $1.304.602 del P&L: **$1.577.905,52 de costo que la base
    no tenía**, con el semáforo en verde.

    El control de verdad es contra un número que este cálculo NO produce.
    """
    r = be.equilibrio_en_noches(
        revenue=D("500"), variable_cost=D("120.55"), fixed_cost=D("380.45"),
        nights_occupied=D("10"), nights_available=D("100"),
        costo_del_pl=D("501.00"))
    assert r.validacion_costo == D("0")
    assert r.cuadra is True


def test_la_validacion_DETECTA_el_costo_que_falta():
    """El caso real, con los montos del `Working 2027` redondeados."""
    r = be.equilibrio_en_noches(
        revenue=D("6374026"), variable_cost=D("1000000"), fixed_cost=D("3064126"),
        nights_occupied=D("2000"), nights_available=D("10950"),
        costo_del_pl=D("4510308"))
    assert r.cuadra is False
    assert r.validacion_costo == D("-446182")


def test_sin_costo_del_pl_la_validacion_dice_SIN_CONTROL_no_cuadra():
    """`None` no es `True`. Pintar de verde lo que nadie midió es exactamente
    como pasaron desapercibidos $1.577.905,52."""
    r = be.equilibrio_en_noches(
        revenue=D("500"), variable_cost=D("120.55"), fixed_cost=D("380.45"),
        nights_occupied=D("10"), nights_available=D("100"))
    assert r.validacion_costo is None
    assert r.cuadra is None
