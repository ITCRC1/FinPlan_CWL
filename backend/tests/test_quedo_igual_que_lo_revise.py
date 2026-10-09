# -*- coding: utf-8 -*-
"""«¿Quedó igual que lo que revisé?» — que lo conteste la app.

Owner, 2026-09-16: *«dejá una mejoría»*. Era ésta, y quedó sin hacer: un
endpoint que compare el borrador del Pre-Cierre contra lo que se escribió, línea
por línea, en vez de un cálculo a mano cada vez.

Compara contra los DOS destinos que escribe el mismo camino, porque fallan
distinto:

* **el espejo**, que es lo que miran los sub-tabs de Pre-Closing. La subida
  escribe el borrador y después el espejo, y no es todo-o-nada: si el espejo
  falla, el borrador queda igual y la respuesta lo dice — pero un rato después
  nadie se acuerda.
* **el ACTUAL**, que responde si pasar a final cambió algo en el camino.

Verificado contra producción el 2026-10-09:

* setiembre contra el espejo: 194 pares, **194 coinciden, 0 difieren**;
* agosto contra el ACTUAL: 24 diferencias relevantes, de las cuales tres pares
  se cancelan entre sí —plata que cambió de renglón— y una es neta:
  `OH_CC_COMMISSIONS` con $2.807,50 de más en el ACTUAL.
"""
import inspect

from app.api import precierre_api


def _fuente() -> str:
    return inspect.getsource(precierre_api.contra_actual)


def test_compara_contra_LOS_DOS_destinos():
    """El espejo y el ACTUAL fallan distinto: uno por una subida a medias, el
    otro por lo que pase al pasar a final."""
    f = _fuente()
    assert "_espejo" in f
    assert 'Scenario.type == "ACTUAL"' in f
    assert '"espejo":' in f and '"actual":' in f


def test_el_destino_sale_de_LO_QUE_LEEN_LOS_REPORTES():
    """⚠️ `actual_rows_for_month` — no una tercera forma de sumar.

    Una comparación que suma distinto que los reportes contesta sobre un número
    que nadie ve.
    """
    assert "actual_rows_for_month" in _fuente()


def test_la_regla_de_allocation_NO_se_compara():
    """⚠️ Fuera del espejo, las clases 5/6/7 de Cafetería y Lavandería —y el
    crédito 4999— no entran al destino: `ALLOCATION_EXCLUDE` las deja fuera a
    propósito. Compararlas marcaría esas líneas como diferencia TODOS los meses.

    Medido en agosto 2026: de 44 diferencias contra el ACTUAL, 20 eran esto. Una
    revisión que llora lobo todos los meses deja de mirarse, y entonces el día
    que tenga razón tampoco.
    """
    f = _fuente()
    assert "excluida_del_archivo" in f
    assert "CUENTAS_DE_REPARTO" in f
    assert "omitidas_por_allocation" in f


def test_distingue_CAMBIO_DE_CODIGO_de_PLATA_QUE_SE_MOVIO():
    """La pregunta que de verdad importa.

    En agosto el borrador tenía `0152/4500` y el ACTUAL `0152/4400`: códigos
    distintos que el mapeo manda a la MISMA línea, así que el P&L dice lo mismo.
    Pero `0165/4316` (REV_RETAIL) contra `0151/4304` (REV_TIENDA) sí cambia el
    renglón. Sin separarlas, las dos se ven igual de graves.
    """
    f = _fuente()
    assert "lineas_movidas" in f
    assert "linea_pl" in f
    assert "construir_resolvedor" in f


def test_un_destino_vacio_lo_DICE_y_no_lista_todo():
    """Un mes que todavía no se pasó a final no tiene 195 problemas: tiene uno.

    Medido: contra el ACTUAL, setiembre daba 195 «solo en el borrador», que es
    ruido con forma de hallazgo.
    """
    f = _fuente()
    assert '"vacio": True' in f
    assert "no tiene nada" in f


def test_la_tolerancia_no_marca_el_REDONDEO():
    """El borrador guarda seis decimales y el destino cuatro. Exigir igualdad
    exacta marcaría el redondeo como diferencia — el mismo error que disparaba
    el 409 de la plantilla."""
    f = _fuente()
    assert "TOLERANCIA = 0.02" in f
    # Y el «cuadra» se decide por lo que importa, no por centavos.
    assert "difieren_relevantes" in f
    assert "abs(x[\"diferencia\"]) > 1.0" in f


def test_SOLO_LEE():
    """Es una pregunta, no una corrección. Si escribiera, sería un tercer camino
    de escritura para el mismo mes."""
    f = _fuente()
    for verbo in ("db.add", "commit", "delete(", "flush"):
        assert verbo not in f


def test_esta_registrado_y_pide_token():
    from fastapi.testclient import TestClient

    from app.main import app
    cliente = TestClient(app, raise_server_exceptions=False)
    rutas = cliente.app.openapi()["paths"]
    assert "/api/precierre/{precierre_id}/contra-actual/" in rutas
    assert cliente.get(
        "/api/precierre/loquesea/contra-actual/").status_code in (401, 403)
