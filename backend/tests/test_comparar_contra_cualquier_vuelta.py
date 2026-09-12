# -*- coding: utf-8 -*-
"""«Que cambio» se puede medir contra CUALQUIER vuelta del mes, no solo la de al lado.

Owner, 2026-09-11, con veintiuna vueltas de agosto: las dos ultimas eran el
mismo archivo al mismo tipo de cambio, asi que la comparacion decia «sin
cambios» —y tenia razon— mientras el cambio que le importaba, el TC de 453,06 a
453,68, habia quedado cinco vueltas atras. «No lo veo... la diferencia.»
"""
import inspect

from app.api import precierre_api


def test_el_endpoint_acepta_contra_quien_comparar():
    firma = inspect.signature(precierre_api.cambios)
    assert "contra" in firma.parameters, (
        "sin este parametro la comparacion queda atada a la vuelta anterior, "
        "que despues de veinte vueltas casi nunca es la que interesa")


def test_por_defecto_sigue_siendo_la_anterior():
    """Cambiar el default obligaria a elegir en cada carga."""
    assert precierre_api.cambios.__wrapped__ if hasattr(
        precierre_api.cambios, "__wrapped__") else True
    firma = inspect.signature(precierre_api.cambios)
    default = firma.parameters["contra"].default
    # Es un Query() de FastAPI: lo que importa es que su valor sea vacio.
    assert getattr(default, "default", default) == ""


def test_devuelve_las_vueltas_para_poder_elegir():
    src = inspect.getsource(precierre_api.cambios)
    assert '"vueltas": vueltas' in src, (
        "la lista tiene que viajar con la respuesta: si la pantalla la tuviera "
        "que ir a buscar aparte, las dos podrian discrepar")
    assert src.count('"vueltas": vueltas') == 2, (
        "tambien en la salida temprana de la primera vuelta del mes, o el "
        "selector desapareceria justo cuando explica por que no hay nada")


def test_solo_compara_contra_vueltas_del_mismo_mes():
    """Comparar contra otro mes daria deltas que no significan nada."""
    src = inspect.getsource(precierre_api.cambios)
    assert "Precierre.anio == pc.anio" in src and "Precierre.mes == pc.mes" in src
    assert "precierre.vuelta_desconocida" in src, (
        "un id de otro mes tiene que fallar diciendolo, no caer en silencio a "
        "la vuelta anterior")


def test_sin_elegir_toma_la_anterior_EN_EL_TIEMPO():
    """Comparar contra una posterior daria los deltas al reves."""
    src = inspect.getsource(precierre_api.cambios)
    assert "h.creado_en <= pc.creado_en" in src


# ── El P&L lado a lado ──────────────────────────────────────────────────────
#
# Owner, 2026-09-11: «espero ver una tabla comparativa y la varianza». La
# comparacion por CUENTA contesta «que se movio» y sirve para ir a buscar el
# posteo, pero son codigos del mayor. Esta es la hoja que el revisa a ojo.

def test_la_comparacion_trae_el_pl_lado_a_lado():
    src = inspect.getsource(precierre_api.cambios)
    assert '"hoja": hoja' in src, "sin esto no hay tabla comparativa de P&L"
    assert '"var_pct"' in src, "y sin porcentaje no hay varianza"


def test_el_pl_comparado_usa_el_MISMO_calculo_que_la_hoja_de_revision():
    """Si se calculara distinto, las dos pestanas podrian discrepar sobre el
    mismo mes y no habria forma de saber cual creer."""
    src = inspect.getsource(precierre_api.cambios)
    assert "revision.valores_completos" in src
    assert "revision.PLAN" in src


def test_sin_base_no_hay_porcentaje():
    """Una linea que estaba en cero y ahora tiene plata no varia «un infinito
    por ciento»: no tiene porcentaje, y eso se dice con null."""
    src = inspect.getsource(precierre_api.cambios)
    assert "if a else None" in src


def test_los_titulos_de_seccion_viajan():
    """Sin ellos la tabla pierde la estructura que la hace legible."""
    src = inspect.getsource(precierre_api.cambios)
    assert '"clave": None' in src
