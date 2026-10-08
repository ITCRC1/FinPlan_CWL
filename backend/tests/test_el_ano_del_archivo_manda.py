# -*- coding: utf-8 -*-
"""El archivo no se puede cargar en un ano que no es el suyo.

**Como aparecio (2026-10-08).** El owner subio
`Ojochal_Gardens_Detalle_ACTUAL_Final_2025_full.xlsx` con la version
**ACTUAL Final 2026** elegida en el selector. Los doce meses de 2025 quedaron
guardados como 2026: $153,204.61 de ingreso de habitaciones, al centavo, en el
ano equivocado.

**Nada fallo.** El P&L cuadro consigo mismo, y la verificacion de arriba contra
el detalle de abajo tambien — porque los dos lados salen del MISMO archivo. Lo
unico que no cuadraba era contra la realidad, y eso el sistema no lo mira. Se
descubrio de casualidad, al intentar subir el archivo por segunda vez: el 409
del anti-reimport nombro el escenario destino y ahi salto el ano.

**Donde estaba el agujero.** `_match_block_target` siempre compara el ano
(`s.type == typ and s.year == year`), pero el `scenario_id` del selector lo
puentea entero:

    target = forced or _match_block_target(scenarios, blk["type"], blk["year"])

`forced` nacio para DESEMPATAR entre versiones del mismo tipo+ano —el caso que
lo justifico fue «2 forecast 2026»—, y sin este chequeo tambien servia para
mover el dato de un ano a otro.
"""
import inspect

import pytest

from app.api import scenarios_api
from app.errores import MENSAJES, texto


def _tramo(fuente: str) -> str:
    """El tramo del chequeo de ano, desde el calculo hasta el raise."""
    ini = fuente.index("desalineados = sorted(")
    fin = fuente.index("exigir_filas_con_cuenta(blocks)", ini)
    return fuente[ini:fin]


@pytest.fixture(scope="module")
def fuente() -> str:
    return inspect.getsource(scenarios_api.import_gl_detail)


def test_el_ano_del_bloque_se_compara_contra_el_del_escenario(fuente):
    """La comparacion que faltaba."""
    assert 'blk["year"] != forced.year' in fuente, (
        "volvio a desaparecer la comparacion de ano. Sin ella, el selector de "
        "version manda un archivo de 2025 al escenario de 2026 y NADA avisa: "
        "el P&L cuadra consigo mismo porque los dos lados salen del archivo."
    )
    assert "gl.ano_no_coincide" in fuente


def test_se_niega_antes_de_escribir_una_sola_fila(fuente):
    """Si bloquea, no quedo nada que deshacer.

    Es la misma regla que la verificacion y la moneda: el chequeo va en la
    puerta. Aca importa mas todavia, porque lo que se escribiria son doce meses
    en el ano equivocado — y para deshacerlo hay que saber que paso.
    """
    corte = fuente.index('blk["year"] != forced.year')
    # `results = []` abre el bucle que escribe. Todo lo que valida va antes.
    assert corte < fuente.index("results = []"), (
        "el chequeo de ano quedo DESPUES del bucle que escribe"
    )
    # Y antes de la verificacion y de la moneda, que ya consolidan el bloque:
    # consolidar un archivo que va al ano equivocado no informa nada.
    assert corte < fuente.index("aviso_de_moneda(con[")


def test_no_tiene_salida_de_emergencia(fuente):
    """A proposito, y por eso se prueba.

    `confirmar_diferencias` existe porque una propiedad PUEDE tener tarifas
    fuera de rango y saberlo — hay una version legitima de ese caso. De un ano
    equivocado no hay version legitima: el bloque dice de que ano es. Si de
    verdad hay que mover el dato, se cambia la etiqueta en el Excel.
    """
    # Se miran las LINEAS DE CODIGO, no los comentarios: el tramo explica por
    # que NO usa `confirmar_diferencias`, asi que el nombre aparece ahi escrito.
    codigo = [l for l in _tramo(fuente).splitlines()
              if not l.lstrip().startswith("#")]
    assert not [l for l in codigo if "confirmar_diferencias" in l], (
        "le pusieron salida de emergencia al chequeo de ano"
    )


def test_el_mensaje_existe_en_los_dos_idiomas():
    assert "gl.ano_no_coincide" in MENSAJES
    params = dict(anio_archivo="2025", anio_destino=2026,
                  destino="ACTUAL Final 2026", bloques="«Actual Final 2025» (2025)")
    for loc in ("es", "en"):
        msg = texto(loc, "gl.ano_no_coincide", **params)
        assert "2025" in msg and "2026" in msg
        # Que diga que NO se cargo nada: el usuario tiene que saber si quedo
        # algo a medias o no quedo nada.
        assert ("No se cargó nada" in msg) or ("Nothing was loaded" in msg)


def test_el_bloque_del_archivo_trae_el_ano(tmp_path):
    """La comparacion necesita que el bloque sepa de que ano es. Lo sabe: sale
    de la etiqueta («Actual Final 2025»), y es lo mismo que `_match_block_target`
    usa cuando NO hay escenario forzado."""
    from app.export.detail_excel import build_detail_workbook
    from app.importers.gl_detail_importer import parse_gl_detail

    etiqueta = "Actual Final 2025"
    xls = build_detail_workbook(
        [etiqueta],
        [{"clase": "Revenue", "grupo": "ROOMS", "dept_code": "0110",
          "cuenta": "4000", "nombre": "Rooms",
          "vals": {(etiqueta, 1): 1000.0}, "orden": None}],
        {}, {"0110": "Habitaciones"})
    bloques = parse_gl_detail(xls)
    assert bloques, "la plantilla no produjo ningun bloque"
    assert bloques[0]["year"] == 2025, (
        f"el bloque no trae el ano: {bloques[0].get('year')!r}"
    )


def test_no_abre_el_panel_con_boton_de_saltarse_la_regla(fuente):
    """El 409 NO manda «bloques», y eso es una decision.

    `lib/api.ts` abre el panel rojo —con su boton «subir igual»— en cuanto el
    detalle del 409 trae la clave `bloques`:

        if (j?.detail?.bloques) throw new ErrorDeVerificacion(...)

    Ese boton manda `confirmar_diferencias=true`, que a este chequeo no lo
    abre. Mandar `bloques` pondria en pantalla un boton que promete saltarse la
    regla y despues falla igual — y la tabla se dibujaria con «no trae bloque de
    verificacion», que no tiene nada que ver con lo que paso.
    """
    assert '"bloques": [' not in _tramo(fuente), (
        "el 409 del ano volvio a mandar «bloques»: la pantalla va a ofrecer "
        "«subir igual» para una regla que no tiene salida de emergencia"
    )
