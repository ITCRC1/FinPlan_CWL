# -*- coding: utf-8 -*-
"""Todo auxiliar contra el GL — D-8 del owner (2026-08-20).

Textual: «todos los auxiliares deben amarrar con el GL, en todos los tabs, y
las estadísticas. Cada despliegue siempre debe cuadrar.»

⚠️ **No se inventó un cuadre nuevo.** El motor ya compara Detalle (GL) contra
Resumen (P&L) sobre siete totales de control, con tolerancia, evidencia y
respetando los meses propios de cada escenario. Esto lo corre sobre todos.
"""
from app.guillermo.cuadre import CONOCIDAS, CuadreEscenario, resumen


def _f(nombre, estado, difs=None, conocida=""):
    return CuadreEscenario(escenario=nombre, estado=estado, manda="", motivo="",
                           diferencias=difs or [], conocida=conocida)


def test_SIN_VERIFICAR_NO_CUENTA_COMO_CUADRA():
    """⚠️ **El error que esto evita.** Un escenario sin detalle del mayor no
    tiene contra qué compararse. Contarlo como «cuadra» haría que **catorce
    presupuestos** salieran al día sin que nadie haya comparado nada — medido
    en producción el 2026-08-20.
    """
    r = resumen([_f("A", "sin_verificar"), _f("B", "sin_verificar")])
    assert r["cuadran"] == 0
    assert r["sin_verificar"] == 2
    assert r["hay_ciegos"] is True


def test_un_descuadre_CONOCIDO_no_frena_pero_se_ve():
    """Los dos descuadres documentados —ACTUAL 2024 y FORECAST April— no pueden
    frenar cada despliegue. Pero tampoco pueden desaparecer: si se escondieran,
    uno nuevo se perdería entre ellos."""
    dif = [{"total": "TOTAL_GOP", "resumen": 1.0, "detalle": 2.0,
            "diferencia": -43698.37}]
    r = resumen([_f("ACTUAL/2024/actual", "no_cuadra", dif, "documentado")])
    assert r["todo_cuadra"] is True
    assert r["descuadres_conocidos"] == 1
    assert r["no_cuadran"] == 1


def test_un_descuadre_NUEVO_SI_frena():
    dif = [{"total": "TOTAL_REVENUES", "resumen": 1.0, "detalle": 2.0,
            "diferencia": 153902.69}]
    r = resumen([_f("ACTUAL/2026/actual", "no_cuadra", dif)])
    assert r["todo_cuadra"] is False
    assert r["descuadres_nuevos"] == 1


def test_todo_cuadra_exige_que_no_haya_ciegos_visibles():
    """`todo_cuadra` mira los descuadres nuevos; `hay_ciegos` es una señal
    aparte. Fundirlas en un solo booleano perdería una de las dos: o se frena
    por no poder verificar, o se da por bueno lo que no se miró."""
    r = resumen([_f("A", "cuadra"), _f("B", "sin_verificar")])
    assert r["todo_cuadra"] is True
    assert r["hay_ciegos"] is True


def test_las_conocidas_dicen_POR_QUE():
    """Una excepción sin motivo escrito es una excepción que nadie puede
    revisar — y con el tiempo, una que nadie recuerda por qué está."""
    assert CONOCIDAS
    for clave, motivo in CONOCIDAS.items():
        assert len(motivo) > 40, f"{clave} no explica nada"
        assert any(c.isdigit() for c in motivo), (
            f"{clave} no dice de cuánto es la diferencia")


def test_la_peor_diferencia_mira_el_VALOR_ABSOLUTO():
    """Un descuadre de −$199.667 es tan grave como uno de +$199.667. Ordenar
    por el valor con signo pondría los peores al final."""
    difs = [{"total": "A", "resumen": 0, "detalle": 0, "diferencia": -199667.97},
            {"total": "B", "resumen": 0, "detalle": 0, "diferencia": 100.0}]
    assert _f("X", "no_cuadra", difs).peor_diferencia == 199667.97


def test_no_se_invento_un_cuadre_paralelo():
    """⚠️ El motor YA decide qué fuente manda comparando los siete totales.
    Escribir otra comparación daría dos respuestas para la misma pregunta, y
    tarde o temprano se contradicen."""
    import inspect

    from app.guillermo import cuadre

    fuente = inspect.getsource(cuadre.cuadre_de_todos)
    assert "veredicto_del_detalle" in fuente


# ── Dónde vive el descuadre ─────────────────────────────────────────────────

def _con_meses(solo_detalle=None, culpables=None):
    return CuadreEscenario(
        escenario="ACTUAL/2026/actual", estado="no_cuadra", manda="resumen",
        motivo="", diferencias=[{"total": "EBT", "resumen": 1.0,
                                 "detalle": 2.0, "diferencia": -199667.97}],
        meses_culpables=culpables or [], en_el_detalle_no_en_el_resumen=solo_detalle or [])


def test_EL_AVISO_DICE_QUE_HACER_no_solo_cuanto():
    """⚠️ «Descuadra en 7 totales por $199.667,97» manda a abrir una
    investigación. «Subí el resumen de junio» se resuelve en un minuto.

    Medido en producción el 2026-08-20: el descuadre entero de ACTUAL 2026 era
    junio — el detalle del mayor cargado y su resumen no. Sacando junio, los
    siete totales cuadran **al centavo**.
    """
    from app.guillermo.cuadre import que_hacer

    texto = que_hacer(_con_meses(solo_detalle=[6]))
    assert "junio" in texto
    assert "RESUMEN" in texto


def test_cuando_NO_se_puede_nombrar_el_mes_NO_se_inventa_una_accion():
    """⚠️ Inventar una acción para un descuadre cuya causa no se midió es peor
    que no dar ninguna: manda a alguien a arreglar lo que no está roto.

    Es el caso de ACTUAL 2024 y del Forecast April: su diferencia no se explica
    por un mes que falte.
    """
    from app.guillermo.cuadre import que_hacer

    texto = que_hacer(_con_meses())
    assert "no se explica por un mes que falte" in texto
    assert "Subí" not in texto


def test_un_escenario_que_cuadra_no_recibe_instrucciones():
    from app.guillermo.cuadre import que_hacer

    assert que_hacer(_f("A", "cuadra")) == ""
    assert que_hacer(_f("B", "sin_verificar")) == ""


def test_los_meses_se_miden_POR_VALOR_y_no_por_presencia():
    """⚠️ **El falso positivo que esto atrapa.** El detalle del mayor guarda los
    doce meses en COLUMNAS, así que «tiene filas» es cierto para todos aunque
    valgan cero. La primera versión acusaba a julio, agosto y hasta diciembre de
    faltar, y habría mandado a subir resúmenes de meses sin actividad.

    Se reusa `meses_con_dato_por_fuente`, que ya medía por valor — en vez de
    escribir una segunda forma de contestar la misma pregunta.
    """
    import inspect

    from app.guillermo import cuadre

    fuente = inspect.getsource(cuadre._donde_vive_el_descuadre)
    assert "meses_con_dato_por_fuente" in fuente
    assert "actual_rows_for_month" not in fuente


def test_la_funcion_partida_sigue_dando_lo_mismo_que_antes():
    """`meses_con_dato` ahora es la unión de las dos fuentes. Si dejara de
    serlo, el corte de meses cerrados cambiaría en silencio — y ése decide qué
    protege el recálculo."""
    import inspect

    from app.engine import meses_cerrados

    fuente = inspect.getsource(meses_cerrados.meses_con_dato)
    assert "meses_con_dato_por_fuente" in fuente
    assert "resumen | detalle" in fuente
