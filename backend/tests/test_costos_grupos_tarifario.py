# -*- coding: utf-8 -*-
"""El tarifario RACK del módulo de grupos.

Decisión del owner (2026-08-19): «la realidad debe ser Forecast 2026», y
«tomá 2027 como válidos en una tabla de rack rates y yo los edito».

La pregunta que estas pruebas contestan no es «¿el CRUD guarda?» sino **¿puede
el precio moverle el piso a alguien?** — porque si puede, el módulo entero
deja de servir: negociar un descuento bajaría el piso justo lo necesario para
que el descuento parezca aceptable.
"""
from decimal import Decimal

import pytest

from app.engine.costos_grupos import (
    TarifaRack, descuentos, factor_neto_del_rack, pisos_habitacion,
)
from app.engine.costos_grupos import MesDeCostos
from app.seed_costos_grupos import ARCHIVO_RACK, _rack_rates


def _mes(temporada="ALTA", propio="100000", oh="40000", disp=930, ocup="500"):
    return MesDeCostos(
        mes=1, temporada=temporada, dias_abiertos=31,
        revenue_por_dept={"REV_ROOMS": Decimal("300000")},
        costo_por_dept={"OPEX_ROOMS": Decimal(propio)},
        overhead_por_componente={"OH_ADMIN": Decimal(oh)},
        hab_disponibles=disp, hab_ocupadas=Decimal(ocup),
        noches_huesped=Decimal(ocup) * 2,
    )


COMP = {("ROOMS", "propio"): ["OPEX_ROOMS"], ("ROOMS", "venta"): ["OPEX_ROOMS"]}
PAR = {"management_fee_pct": "0.03", "margen_protegido_pct": "0.15",
       "metodo_absorcion": "M2", "sustainability_libre": "NO"}


# ── La razón de ser de la tabla aparte ──────────────────────────────────────

def test_EL_PISO_NO_SE_MUEVE_AUNQUE_EL_RACK_CAMBIE():
    """⚠️ **La prueba que justifica que el tarifario sea una tabla aparte.**

    Si el rack viviera en `rate_cards` del escenario, editarlo movería el
    ingreso, el ingreso movería el costo unitario y el piso se movería solo:
    conceder un descuento bajaría el piso lo suficiente para que el descuento
    pareciera aceptable. Circular y silencioso.

    Acá el rack no entra en `pisos_habitacion` ni por parámetro. Duplicarlo o
    partirlo por diez tiene que dar EXACTAMENTE el mismo piso.
    """
    meses = [_mes()]
    antes = pisos_habitacion(meses, COMP, PAR, Decimal("0.203"))

    # El rack se mueve muchísimo — y no se le pasa a `pisos_habitacion`,
    # porque esa función no lo recibe. Ese es el punto.
    for rack in ("100", "839.52", "10000"):
        racks = [TarifaRack("BL01", "Deluxe King", 1, Decimal(rack),
                            Decimal(rack) * Decimal("0.797"), Decimal("1.8"))]
        descuentos(racks, antes.con_margen)          # se usa, y no muta nada
        despues = pisos_habitacion(meses, COMP, PAR, Decimal("0.203"))
        assert despues.con_margen == antes.con_margen
        assert despues.integral == antes.integral
        assert despues.departamental == antes.departamental
        assert despues.marginal == antes.marginal


def test_mover_el_rack_SI_mueve_el_descuento():
    """El contrapunto: si nada se moviera, la tabla no serviría de nada."""
    piso = Decimal("500")
    bajo = descuentos([TarifaRack("X", "X", 1, Decimal("800"),
                                  Decimal("637.6"), Decimal("1.8"))], piso)[0]
    alto = descuentos([TarifaRack("X", "X", 1, Decimal("1600"),
                                  Decimal("1275.2"), Decimal("1.8"))], piso)[0]
    assert alto.descuento_max > bajo.descuento_max


# ── La semilla ──────────────────────────────────────────────────────────────

def test_la_semilla_del_rack_vive_en_git_y_tiene_las_96_celdas():
    """La lista de verdad vive en git, no en la base — misma regla que el
    mapeo del P&L y las cuentas estadísticas. 8 categorías × 12 meses."""
    filas = _rack_rates()
    assert ARCHIVO_RACK.exists()
    assert len(filas) == 96
    assert len({f["room_type_code"] for f in filas}) == 8
    assert sorted({int(f["mes"]) for f in filas}) == list(range(1, 13))


def test_la_semilla_se_llavea_por_CODIGO_y_no_por_nombre():
    """⚠️ El nombre es una etiqueta renombrable; el código es fijo por
    categoría. Llavear por nombre haría que renombrar «Deluxe King» dejara
    huérfanas sus doce tarifas sin que nada fallara."""
    filas = _rack_rates()
    assert all(f.get("room_type_code") for f in filas)
    codigos = {f["room_type_code"] for f in filas}
    assert codigos == {"BL01", "BI02", "PO03", "RO04",
                       "BI05", "BL06", "SH07", "SH08"}


def test_el_rack_de_la_semilla_cambia_mes_a_mes():
    """⚠️ Por esto la tabla es de 12 columnas y no de 3 temporadas.

    El rack BAJA en temporada baja justo cuando el piso SUBE. Un promedio por
    temporada taparía exactamente el mes que duele.
    """
    filas = _rack_rates()
    por_tipo: dict[str, set] = {}
    for f in filas:
        por_tipo.setdefault(f["room_type_code"], set()).add(f["rack"])
    variables = [c for c, v in por_tipo.items() if len(v) > 1]
    assert len(variables) >= 6, f"solo {len(variables)} categorías varían por mes"

    # Y baja de verdad: enero contra setiembre en una categoría que varía.
    de = {(f["room_type_code"], int(f["mes"])): Decimal(f["rack"]) for f in filas}
    assert de[("BI02", 9)] < de[("BI02", 1)]


def test_la_semilla_no_trae_tarifas_negativas_ni_netos_mayores_al_rack():
    """Un neto por encima del rack daría una comisión negativa y un factor
    mayor que 1 — el mismo defecto que tiene `compute_net_factor`."""
    for f in _rack_rates():
        rack, neto = Decimal(f["rack"]), Decimal(f["neto"])
        assert rack > 0, f
        assert 0 < neto <= rack, f


# ── El factor neto ──────────────────────────────────────────────────────────

def test_el_factor_neto_de_la_semilla_es_menor_que_uno():
    """⚠️ `compute_net_factor(channels)` devuelve **9,5639** en producción para
    los 36 canales del Budget Working 2027. Un factor mayor que 1 multiplicaría
    el ingreso por nueve. El módulo saca el suyo del tarifario a propósito."""
    filas = _rack_rates()
    racks = [TarifaRack(f["room_type_code"], f["nombre"], f["orden"],
                        Decimal(f["rack"]), Decimal(f["neto"]), Decimal(f["pax"]))
             for f in filas if int(f["mes"]) == 1]
    fn = factor_neto_del_rack(racks)
    assert fn is not None
    assert Decimal("0") < fn < Decimal("1")
    assert Decimal("0.79") < fn < Decimal("0.80")


# ── La tabla del módulo NO es la del escenario ──────────────────────────────

def test_el_motor_del_modulo_no_lee_los_rate_cards_del_escenario():
    """⚠️ Hay DOS tarifarios en la app y editar el equivocado es el error
    fácil. `/revenue/rack-rates` mueve el ingreso del presupuesto; éste no
    mueve nada. Que el motor del módulo no importe `RateCard` es lo que lo
    sostiene."""
    import inspect

    from app.engine import costos_grupos

    fuente = inspect.getsource(costos_grupos.tarifas_rack)
    assert "CfgTarifaRack" in fuente
    assert "RateCard" not in fuente
    # Y no recibe `scenario_id`: no hay forma de apuntarlo a un escenario.
    firma = inspect.signature(costos_grupos.tarifas_rack)
    assert "scenario_id" not in firma.parameters


def test_la_pantalla_avisa_que_no_es_el_otro_tarifario():
    """Tener dos tablas de rack sin explicar la diferencia es cómo se edita la
    equivocada. La pantalla lo tiene que decir, no sólo el código."""
    import io
    import os

    ruta = os.path.join(os.path.dirname(__file__), "..", "..", "frontend",
                        "app", "cost", "pisos", "page.tsx")
    txt = io.open(ruta, encoding="utf-8").read()
    assert "rack-rates" in txt or "Rack Rates" in txt
    assert "no mueve" in txt.lower()


# ── Lo que la pantalla tiene que confesar ───────────────────────────────────

def test_un_piso_1_estimado_llega_marcado_hasta_la_pantalla():
    """Un Piso 1 que parece medido y no lo está es peor que no tenerlo."""
    meses = [_mes()]
    sin_venta = {("ROOMS", "propio"): ["OPEX_ROOMS"]}
    p = pisos_habitacion(meses, sin_venta, PAR, Decimal("0.203"))
    assert p.marginal_estimado is True

    import io
    import os
    ruta = os.path.join(os.path.dirname(__file__), "..", "..", "frontend",
                        "app", "cost", "pisos", "page.tsx")
    txt = io.open(ruta, encoding="utf-8").read()
    assert "marginal_estimado" in txt


@pytest.mark.parametrize("temporada", ["ALTA", "MEDIA", "BAJA"])
def test_el_descuento_maximo_nunca_pasa_del_cien_por_ciento(temporada):
    """Un descuento del 100% sería regalar la habitación. Con un piso positivo
    la fórmula no puede llegar ahí; la prueba fija esa propiedad."""
    p = pisos_habitacion([_mes(temporada=temporada)], COMP, PAR, Decimal("0.203"))
    assert p.con_margen > 0
    d = descuentos([TarifaRack("X", "X", 1, Decimal("999999"),
                               Decimal("797000"), Decimal("1.8"))],
                   p.con_margen)[0]
    assert d.descuento_max < Decimal("1")
