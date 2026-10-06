# -*- coding: utf-8 -*-
"""Un mes cerrado no se edita — owner, 2026-08-20.

*«Este mensaje no me gusta, que sigue editable. Para mí debe enllavarse el
checkbook, no debe dejar que se edite.»*
"""
import inspect
from decimal import Decimal
from decimal import Decimal as D

from app import candado_meses as cm
# ⚠️ El mapa se deriva del registro de modelos: sin la app importada, el
# registro está vacío. Importarla es parte de lo que se prueba.
from app.main import app  # noqa: F401


def test_un_mapa_VACIO_no_se_cachea():
    """⚠️ Si se cacheara el vacío —por correr antes de que los modelos estén
    importados— el candado quedaría apagado **para siempre y en silencio**, que
    es peor que no tenerlo: parece puesto."""
    fuente = inspect.getsource(cm.columnas_de_mes)
    assert "if _MAPA:" in fuente
    assert "if fuera:" in fuente


def test_los_modelos_se_DERIVAN_del_mapeo():
    """⚠️ Una lista a mano dejaría afuera la tabla nueva, y este proyecto ya
    pagó dos veces por eso."""
    fuente = inspect.getsource(cm.columnas_de_mes)
    assert "Base.registry.mappers" in fuente
    mapa = cm.columnas_de_mes()
    assert len(mapa) >= 9, f"sólo {len(mapa)} modelos con meses"
    nombres = {c.__name__ for c in mapa}
    for esperado in ("OpexEntry", "PayrollPosition", "RevenueEntry", "CostEntry"):
        assert esperado in nombres


def test_reconoce_las_TRES_formas_de_columna_de_mes():
    """`jan`, `crc_jan` y `fte_jan` son el mismo mes."""
    mapa = cm.columnas_de_mes()
    opex = next(c for c in mapa if c.__name__ == "OpexEntry")
    assert mapa[opex]["jan"] == 1 and mapa[opex]["crc_jan"] == 1
    pos = next(c for c in mapa if c.__name__ == "PayrollPosition")
    assert mapa[pos]["fte_dec"] == 12


def test_solo_entran_modelos_CON_ESCENARIO():
    """Sin escenario no hay corte contra el cual comparar."""
    for cls in cm.columnas_de_mes():
        assert "scenario_id" in {c.key for c in cls.__mapper__.columns}


def test_se_mira_si_el_valor_CAMBIA_no_si_viaja():
    """⚠️ **El defecto que esto evita.** Los guardados en grilla mandan los doce
    meses siempre (`OpexBulkRow` tiene `jan..dec` con default 0). Rechazar «el
    cuerpo trae un mes cerrado» bloquearía TODA edición, incluida la de
    diciembre."""
    fuente = inspect.getsource(cm._revisar)
    assert "hist.has_changes()" in fuente
    assert "es_edicion(antes, ahora)" in fuente


def test_el_candado_es_SOLO_para_FORECAST():
    """⚠️ En un ACTUAL «cerrado» es «tiene dato»: aplicarlo impediría corregir
    un histórico, que es trabajo normal y otra conversación."""
    fuente = inspect.getsource(cm._cerrados)
    assert '!= "FORECAST"' in fuente
    assert "actuals_through" in fuente


def test_bloquea_CAMBIAR_CREAR_y_BORRAR():
    fuente = inspect.getsource(cm._revisar)
    assert "session.dirty" in fuente
    assert "session.new" in fuente
    assert "session.deleted" in fuente


def test_va_en_la_sesion_de_la_APP_y_no_en_el_Session_global():
    """⚠️ Registrado en el global disparaba en sesiones sueltas —una prueba con
    SQLite en memoria y dos tablas— y ahí la consulta revienta porque
    `scenarios` no existe."""
    fuente = inspect.getsource(cm)
    assert '@event.listens_for(SesionFinPlan, "before_flush")' in fuente


def test_el_recalculo_NO_se_ve_afectado():
    """Ya saltea los meses cerrados por su cuenta. Si dejara de hacerlo, el
    candado lo frenaría — y esta prueba dice por qué."""
    import pathlib

    rec = (pathlib.Path(cm.__file__).parent / "engine" / "recalculate.py"
           ).read_text(encoding="utf-8")
    assert "if cerrados and (i + 1) in cerrados:" in rec


def test_el_error_dice_DONDE_se_abre_el_periodo():
    """Un 409 que no dice cómo seguir es un callejón."""
    from app.errores import MENSAJES

    es = MENSAJES["escenario.mes_cerrado"]["es"]
    assert "Cierre de períodos" in es
    assert "{mes}" in es and "{escenario}" in es


def test_un_valor_reguardado_IGUAL_no_se_frena():
    """Es la mitad que hace usable al candado: la grilla reenvía los doce meses
    y sólo debe fallar si un mes cerrado cambia de verdad."""
    fuente = inspect.getsource(cm._revisar)
    assert "if not hist.has_changes():\n                continue" in fuente


# ─── Medio centimo no es una edicion ────────────────────────────────────────

def test_una_diferencia_menor_a_un_centimo_NO_es_una_edicion():
    """⚠️ El Excel de Detalle exporta `round(float(v), 2)` y las columnas de mes
    son `Numeric(..., 4)`. Un ingreso en dolares sale del GL dividido por el tipo
    de cambio, asi que casi siempre trae cuatro decimales: 176,9961 baja a la
    plantilla como 176,99 y vuelve DISTINTO.

    Comparando exacto, bajar la plantilla y subirla SIN TOCAR NADA disparaba el
    409 — y el mensaje mandaba a reabrir el periodo, que es destruir un mes
    cerrado y bueno para arreglar un redondeo. Owner, 2026-10-06: «VUELVE A
    SALIR»."""
    assert not cm.es_edicion(D("176.9961"), D("177.00"))
    assert not cm.es_edicion(D("1234.5678"), D("1234.57"))
    assert not cm.es_edicion(D("100"), D("100.004"))
    # El PEOR caso del redondeo cae justo en el umbral, y es el mas probable de
    # aparecer: con `>=` se frenaba.
    assert not cm.es_edicion(D("1234.565"), D("1234.56"))


def test_el_umbral_se_calcula_contra_el_redondeo_de_verdad():
    """No se eligio a ojo: se mide contra lo que el exportador hace."""
    from decimal import ROUND_HALF_EVEN
    for v in ("176.9961", "1234.5678", "1234.565", "0.0049", "98765.4321"):
        guardado = D(v)
        en_plantilla = guardado.quantize(D("0.01"), rounding=ROUND_HALF_EVEN)
        assert not cm.es_edicion(guardado, en_plantilla), v


def test_un_centimo_SI_es_una_edicion():
    """La tolerancia no puede volverse una rendija: un centavo se frena."""
    assert cm.es_edicion(D("100.00"), D("100.01"))
    assert cm.es_edicion(D("100.00"), D("99.99"))
    assert cm.es_edicion(D("176.9961"), D("177.50"))
    assert cm.es_edicion(D("0"), D("12000"))


def test_el_redondeo_NO_se_escribe_en_el_mes_cerrado():
    """No alcanza con dejarlo pasar: si se escribiera el valor redondeado, el mes
    cerrado se correria medio centimo por carga y por cuenta. Se devuelve el
    guardado — un mes cerrado no se toca ni un poquito."""
    fuente = inspect.getsource(cm._revisar)
    assert "setattr(obj, col, antes)" in fuente


def test_la_tolerancia_es_la_del_redondeo_de_la_plantilla():
    """Media parte del ultimo decimal que la plantilla sabe escribir. Si el
    exportador pasara a cuatro decimales, esto deberia bajar con el."""
    assert cm.TOLERANCIA == D("0.005")


def test_el_error_dice_CUANTO_cambio_y_en_que_cuenta():
    """Sin los numeros, «enero esta cerrado» no distingue medio centimo de doce
    mil dolares — y la unica salida que el texto ofrecia era reabrir el periodo.

    Owner, 2026-10-06, tras tres intentos: «SIGUE SALIENDO». La diferencia real
    era de medio centimo por el redondeo de la plantilla; el mensaje no permitia
    saberlo ni a el ni a mi."""
    fuente = inspect.getsource(cm._revisar)
    assert "diferencia" in fuente, "el detalle tiene que traer la diferencia"
    assert 'frenar(obj, mes, col, "cambiar", antes, ahora)' in fuente
    assert "account_code" in fuente, "y en que cuenta fue"
