# -*- coding: utf-8 -*-
"""El simulador de grupos y la salida a Ventas (spec §4.4 a §4.6 y §4.9).

Lo que el módulo contestaba hasta acá era «cuánto cuesta una habitación-noche».
Esto contesta la pregunta de la mesa: *«grupo de 20 pax, 3 noches, en julio, a
este precio — ¿lo tomo, y quién lo autoriza?»*.

Las pruebas vigilan tres cosas que no se ven leyendo el código: que Ventas no
pueda ver un costo, que un piso no se redondee hacia abajo, y que lo que está
prorrateado o sin medir salga confesado en vez de salir en cero.
"""
import json
from decimal import Decimal as D

import pytest

from app.engine.costos_grupos import (
    Escalon, MesDeCostos, desplazamiento, ensamblar_grupo,
    escalones_aplicables, semaforo, ZONAS,
)


def _mes(mes=1, temporada="ALTA", dias=31, propio="200000", oh="80000",
         disp=930, ocup="600", rev_rooms="400000"):
    return MesDeCostos(
        mes=mes, temporada=temporada, dias_abiertos=dias,
        revenue_por_dept={"REV_ROOMS": D(rev_rooms)},
        costo_por_dept={"OPEX_ROOMS": D(propio), "OPEX_FB": D("50000")},
        overhead_por_componente={"OH_ADMIN": D(oh)},
        hab_disponibles=disp, hab_ocupadas=D(ocup),
        noches_huesped=D(ocup) * 2,
    )


COMP = {("ROOMS", "propio"): ["OPEX_ROOMS"], ("FB", "propio"): ["OPEX_FB"]}
PAR = {"management_fee_pct": "0.03", "margen_protegido_pct": "0.15",
       "metodo_absorcion": "M2", "tratamiento_mes_cerrado": "B"}


# ── El semáforo ─────────────────────────────────────────────────────────────

def test_el_semaforo_reparte_las_cuatro_zonas_del_spec():
    """Verde ≥ Piso 4 · Amarilla ≥ Piso 3 · Roja ≥ Piso 1 · Prohibida debajo."""
    m = {"marginal": D("100"), "departamental": D("150"),
         "integral": D("200"), "con_margen": D("250")}
    assert semaforo(D("300"), m) == "verde"
    assert semaforo(D("250"), m) == "verde"          # el borde es verde
    assert semaforo(D("249"), m) == "amarilla"
    assert semaforo(D("200"), m) == "amarilla"
    assert semaforo(D("199"), m) == "roja"
    assert semaforo(D("100"), m) == "roja"
    assert semaforo(D("99"), m) == "prohibida"


def test_cada_zona_dice_QUIEN_autoriza():
    """⚠️ Un semáforo sin autorización deja la decisión en el aire. La zona
    roja no es «no», es «sí con el GG y Finanzas»; sin decirlo, un vendedor la
    lee como prohibida y se pierde negocio que convenía."""
    assert set(ZONAS) == {"verde", "amarilla", "roja", "prohibida"}
    assert "Gerente General" in ZONAS["amarilla"]
    assert "capacidad ociosa" in ZONAS["roja"]
    assert ZONAS["prohibida"] == "No autorizado"


# ── El desplazamiento ───────────────────────────────────────────────────────

def test_si_el_grupo_cabe_en_lo_libre_no_desplaza_nada():
    meses = [_mes(ocup="600", disp=930)]        # 330 libres
    d = desplazamiento(meses, D("30"), D("0.03"), D("0.203"), D("100"))
    assert d.aplica is False
    assert d.contribucion_desplazada == 0
    assert "cabe" in d.motivo


def test_solo_el_exceso_desplaza_no_el_grupo_entero():
    """Con 10 libres y un grupo de 30, desplaza 20 — no 30."""
    meses = [_mes(ocup="920", disp=930)]        # 10 libres
    d = desplazamiento(meses, D("30"), D("0.03"), D("0.203"), D("100"))
    assert d.aplica is True
    assert d.noches_desplazadas == D("20")


def test_un_desplazamiento_que_pierde_plata_NO_baja_el_piso():
    """⚠️ Si el FIT desplazado deja menos que su propio costo variable, la
    contribución desplazada es NEGATIVA — y sumarla bajaría el piso. Ningún
    piso puede bajar porque llegue un grupo."""
    # ADR bajísimo contra un costo variable altísimo.
    meses = [_mes(ocup="920", disp=930, rev_rooms="9200")]     # ADR = $10
    d = desplazamiento(meses, D("30"), D("0.03"), D("0.203"), D("500"))
    assert d.aplica is True
    assert d.contribucion_desplazada == 0
    assert d.por_habitacion_noche == 0


def test_el_umbral_de_politica_no_tiene_default_inventado():
    """Por defecto es 0: se calcula el desplazamiento FÍSICO y nada más.
    Subirlo esconde negocio desplazado y es decisión del owner."""
    meses = [_mes(ocup="920", disp=930)]
    fisico = desplazamiento(meses, D("30"), D("0.03"), D("0.203"), D("100"))
    politica = desplazamiento(meses, D("30"), D("0.03"), D("0.203"), D("100"),
                              umbral_ocupacion=D("0.99"))
    assert fisico.aplica is True
    assert politica.aplica is False
    assert "umbral" in politica.motivo


# ── Los escalones ───────────────────────────────────────────────────────────

class _Regla:
    def __init__(self, driver, umbral, costo, desc=""):
        self.driver, self.umbral = driver, D(umbral)
        self.costo_adicional, self.descripcion = D(costo), desc


def test_un_escalon_entra_solo_cuando_se_CRUZA_el_umbral():
    reglas = [_Regla("pax", "16", "350", "guía adicional")]
    assert escalones_aplicables(reglas, D("16"), D("8")) == []     # igual no cruza
    cruzado = escalones_aplicables(reglas, D("17"), D("8"))
    assert len(cruzado) == 1
    assert cruzado[0].costo == D("350")


def test_sin_reglas_de_escalon_el_grupo_grande_sale_subestimado_Y_SE_DICE():
    """⚠️ Un cero silencioso se lee como «no aplica». Tiene que decir que la
    lista está vacía."""
    g = ensamblar_grupo([_mes()], COMP, PAR, D("0.203"), D("10"), D("3"), D("20"))
    assert g.costo_escalones == 0
    assert any("escalones" in p and "NO hay reglas" in p for p in g.prorrateados)


# ── Lo que el ensamblador tiene que confesar ────────────────────────────────

def test_el_piso_1_igual_al_piso_2_sale_MARCADO():
    """⚠️ El defecto que esto atrapa: sin clasificación fijo/variable el Piso 1
    cae al costo propio y sale IDÉNTICO al Piso 2. Dos pisos iguales se leen
    como que el modelo los calculó y coincidieron. No coincidieron."""
    g = ensamblar_grupo([_mes()], COMP, PAR, D("0.203"), D("10"), D("3"), D("20"))
    assert g.marginal_estimado is True
    assert g.minimo_pax_noche["marginal"] == g.minimo_pax_noche["departamental"]
    assert any("Piso 1" in p for p in g.prorrateados)


def test_el_desplazamiento_confiesa_su_grano_MENSUAL_siempre():
    """Medido contra producción: al grano mensual no se activa nunca en
    Corcovado. Un «$0» presentado como medición mentiría."""
    g = ensamblar_grupo([_mes()], COMP, PAR, D("0.203"), D("10"), D("3"), D("20"))
    assert any("MENSUAL" in p for p in g.prorrateados)


def test_los_costos_unitarios_salen_de_la_temporada_y_el_desplazamiento_del_MES():
    """⚠️ Medir el desplazamiento contra la temporada entera lo apaga siempre:
    30 habitación-noches contra las libres de cinco meses no desplazan nunca."""
    lleno = _mes(mes=2, ocup="925", disp=930)          # 5 libres
    vacio = _mes(mes=3, ocup="100", disp=930)          # 830 libres
    temporada = [lleno, vacio]

    contra_temporada = ensamblar_grupo(temporada, COMP, PAR, D("0.203"),
                                       D("10"), D("3"), D("20"))
    contra_el_mes = ensamblar_grupo(temporada, COMP, PAR, D("0.203"),
                                    D("10"), D("3"), D("20"),
                                    meses_del_grupo=[lleno])
    assert contra_temporada.desplazamiento.aplica is False
    assert contra_el_mes.desplazamiento.aplica is True


# ── Los mínimos ─────────────────────────────────────────────────────────────

def test_los_cuatro_minimos_estan_ordenados():
    g = ensamblar_grupo([_mes()], COMP, PAR, D("0.203"), D("10"), D("3"), D("20"))
    m = g.minimo_pax_noche
    assert m["marginal"] <= m["departamental"] <= m["integral"] < m["con_margen"]


def test_el_minimo_por_estadia_es_el_de_la_noche_por_las_noches():
    g = ensamblar_grupo([_mes()], COMP, PAR, D("0.203"), D("10"), D("3"), D("20"))
    for k in g.minimo_pax_noche:
        assert (g.minimo_pax_noche[k] * D("3") - g.minimo_pax_estadia[k]) < D("0.01")


def test_UN_GRUPO_MAS_GRANDE_NO_ABARATA_LA_HABITACION_SIN_ESCALONES():
    """El costo unitario no depende del tamaño, así que duplicar el grupo tiene
    que duplicar el costo — ni más ni menos. Si bajara, hay un fijo repartido
    donde no corresponde; si subiera, hay un escalón fantasma."""
    chico = ensamblar_grupo([_mes()], COMP, PAR, D("0.203"), D("5"), D("3"), D("10"))
    grande = ensamblar_grupo([_mes()], COMP, PAR, D("0.203"), D("10"), D("3"), D("20"))
    assert grande.costo_total == chico.costo_total * 2
    assert abs(grande.minimo_pax_noche["con_margen"]
               - chico.minimo_pax_noche["con_margen"]) < D("0.01")


# ── La regla que no se puede romper: Ventas no ve costos ────────────────────

def test_LA_SALIDA_A_VENTAS_NO_PUEDE_FILTRAR_UN_SOLO_COSTO():
    """⚠️ **La prueba que sostiene el sub-tab 13.** El spec lo pide en letras:
    «Sin costos visibles». Un vendedor con el costo a la vista negocia contra
    el costo, no contra el piso.

    Se revisa el CÓDIGO del endpoint, no una respuesta de ejemplo: una
    respuesta puede venir sin costos por casualidad del dato.
    """
    import inspect

    from app.api import costos_grupos_sim_api as api

    fuente = inspect.getsource(api.salida_ventas)
    for prohibido in ("g.costo_", "g.overhead", "costo_total", "g.variable",
                      "g.propio", "desplazamiento", "prorrateados"):
        assert prohibido not in fuente, f"la salida a Ventas expone {prohibido}"


def test_la_salida_a_ventas_no_expone_los_pisos_de_excepcion():
    """El Piso 1 y el Piso 2 son autorizaciones de excepción. Ponerlos en la
    pantalla de Ventas los convierte en el precio de lista de cualquier
    negociación difícil."""
    import inspect

    from app.api import costos_grupos_sim_api as api

    fuente = inspect.getsource(api.salida_ventas)
    assert "marginal" not in fuente
    assert "departamental" not in fuente
    assert "con_margen" in fuente and "integral" in fuente


def test_los_dos_endpoints_estan_SEPARADOS_y_no_son_un_parametro():
    """⚠️ Un `?ocultar_costos=true` que alguien olvide poner filtra el costo y
    no falla nada. Que sean dos rutas distintas es la garantía."""
    from app.main import app

    rutas = set(app.openapi()["paths"])
    assert "/api/costos-grupos/simular/" in rutas
    assert "/api/costos-grupos/salida-ventas/" in rutas


# ── El redondeo ─────────────────────────────────────────────────────────────

def test_un_minimo_se_redondea_hacia_ARRIBA():
    """⚠️ Redondear al centavo más cercano deja el precio publicado POR DEBAJO
    del piso. Es la clase de detalle que hace que un control diga «cumple»
    cuando no."""
    from app.api.costos_grupos_sim_api import _dinero, _piso

    assert _piso(D("645.7855818849653")) == "645.79"
    assert _piso(D("645.781")) == "645.79"          # hacia arriba, no a 645.78
    assert _dinero(D("645.781")) == "645.78"        # el informativo, normal


def test_los_minimos_del_endpoint_no_salen_con_veinte_decimales():
    import inspect

    from app.api import costos_grupos_sim_api as api

    for f in (api.simular, api.salida_ventas):
        fuente = inspect.getsource(f)
        assert "str(g.minimo" not in fuente
        assert "str(g.ingreso_minimo" not in fuente


# ── Las validaciones de entrada ─────────────────────────────────────────────

@pytest.mark.parametrize("hab,noches,pax", [(0, 3, 20), (10, 0, 20), (10, 3, 0)])
def test_un_grupo_de_cero_no_se_cotiza(hab, noches, pax):
    """Dividir por cero pax daría un mínimo de $0 y semáforo verde."""
    from fastapi import HTTPException

    from app.api.costos_grupos_sim_api import Cotizacion, _armar

    import asyncio
    # ⚠️ `match` no es cosmético: sin él la prueba también pasaría si saltara
    # OTRO HTTPException —por ejemplo el 409 de «el escenario base no existe»—
    # y entonces estaría verde sin vigilar la validación que dice vigilar.
    with pytest.raises(HTTPException, match="mayores que cero"):
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            _armar(None, Cotizacion(habitaciones=hab, noches=noches, pax=pax, mes=1)))


def test_mas_habitaciones_que_pax_se_rechaza():
    """No es un tipeo que convenga tolerar: el costo saldría igual y nadie lo
    notaría, porque el costo de habitaciones no depende de los pax."""
    from fastapi import HTTPException

    from app.api.costos_grupos_sim_api import Cotizacion, _armar

    import asyncio
    with pytest.raises(HTTPException, match="más habitaciones que pax"):
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            _armar(None, Cotizacion(habitaciones=20, noches=3, pax=10, mes=1)))


def test_el_EXCEL_de_la_vista_ventas_tampoco_lleva_costos():
    """⚠️ Un archivo que se baja desde la vista sin costos y sale con los
    costos adentro es PEOR que no tener la vista: el Excel se reenvía.

    Se revisa la rama de la pantalla que arma el archivo cuando hay `ven`.
    """
    import io
    import os
    import re

    ruta = os.path.join(os.path.dirname(__file__), "..", "..", "frontend",
                        "app", "cost", "simulador", "page.tsx")
    txt = io.open(ruta, encoding="utf-8").read()

    m = re.search(r"if \(ven\) \{(.*?)\n      \}", txt, re.S)
    assert m, "no encontré la rama de Excel de la vista Ventas"
    rama = m.group(1)
    for prohibido in ("sim.costo", "sim.overhead", "sim.minimos",
                      "sim.prorrateados", "sim.desplazamiento"):
        assert prohibido not in rama, f"el Excel de Ventas expone {prohibido}"
    # Y sale antes de llegar a la parte que sí los usa.
    assert "return;" in rama


def test_la_pantalla_llama_a_DOS_endpoints_y_no_filtra_con_css():
    """En modo Ventas el costo no llega al navegador. Esconderlo con un `if`
    de render lo dejaría en las herramientas de desarrollo y en la red."""
    import io
    import os

    ruta = os.path.join(os.path.dirname(__file__), "..", "..", "frontend",
                        "app", "cost", "simulador", "page.tsx")
    txt = io.open(ruta, encoding="utf-8").read()
    assert "salidaVentasGrupo" in txt and "simularGrupo" in txt
    # En la rama de Ventas se limpia lo interno, no se deja cargado y oculto.
    assert "setSim(null)" in txt
