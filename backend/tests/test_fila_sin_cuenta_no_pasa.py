# -*- coding: utf-8 -*-
"""Una fila con monto y sin número de cuenta NO entra, y da error.

**Cómo apareció (owner, 2026-08-14).** Comparando el Actual 2024 contra su
auxiliar: el sistema decía que el gasto de Habitaciones era $394,940.48 y el
auxiliar decía $354,327.21. La diferencia —$40,613.30— resultó ser **dos
renglones del Excel, en noviembre y diciembre, sin número de cuenta**:

    Departamento de Habitaciones · (sin cuenta) · nov −28,957.30 · dic −11,656.00

El importador los descartó porque sin código no sabe a qué línea del P&L van. Y
lo hizo **en silencio**: ni siquiera los contaba, mientras que las otras
exclusiones (`nodept`, `allocation`, `payroll_noconcept`) sí llevaban contador.

Es el peor modo de fallar de este proyecto, y ya lo vimos tres veces hoy: el
resultado cuadra consigo mismo, nada avisa, y el error solo aparece cuando
alguien lo compara a mano contra otra fuente. Meses después.

**La decisión del owner fue que dé ERROR**, no que avise. Una fila sin cuenta que
lleva plata nunca es formato.
"""
import io
import inspect
import pathlib

BACK = pathlib.Path(__file__).resolve().parents[1] / "app"


def test_el_bloque_junta_las_filas_sin_cuenta():
    """Antes ni se contaban: el `continue` era mudo."""
    src = io.open(BACK / "importers" / "gl_detail_importer.py", encoding="utf-8").read()
    assert '"sin_cuenta": []' in src, "el bloque no reserva dónde juntarlas"
    assert 'blk["sin_cuenta"].append(' in src, "no se registra ninguna"


def test_solo_se_registran_las_que_traen_monto():
    """Un encabezado o una línea en blanco tampoco tienen cuenta, y saltarlos
    está bien. Lo que no se puede saltar callado es la plata."""
    src = io.open(BACK / "importers" / "gl_detail_importer.py", encoding="utf-8").read()
    trozo = src.split("code = _acct_code(cell(r0, acct_col))")[1].split("cls = code[0]")[0]
    assert "if montos:" in trozo, (
        "se estarían registrando también los encabezados, y el aviso se volvería ruido"
    )


def test_se_registran_por_bloque_con_sus_propias_columnas():
    """Cada versión del archivo tiene sus propias columnas de mes. Leer las del
    bloque equivocado daría montos de otra versión."""
    src = io.open(BACK / "importers" / "gl_detail_importer.py", encoding="utf-8").read()
    trozo = src.split("code = _acct_code(cell(r0, acct_col))")[1].split("cls = code[0]")[0]
    assert "for blk in blocks:" in trozo
    assert 'blk["colmap"].items()' in trozo


def test_el_helper_devuelve_todo_plano_y_con_la_version():
    from app.importers.gl_detail_importer import filas_sin_cuenta
    bloques = [
        {"label": "Actual 2024", "sin_cuenta": [
            {"fila": 120, "departamento": "Habitaciones", "descripcion": "",
             "meses": {11: -28957.30, 12: -11656.00}, "total": -40613.30}]},
        {"label": "Budget 2025", "sin_cuenta": []},
    ]
    r = filas_sin_cuenta(bloques)
    assert len(r) == 1
    assert r[0]["version"] == "Actual 2024", (
        "sin la versión, quien corrige el Excel no sabe en cuál de los bloques mirar"
    )
    assert r[0]["total"] == -40613.30


def test_el_importador_se_niega_y_no_carga_nada():
    """El texto ya no vive en el `raise`: vive en el catálogo bilingüe
    (`app/errores.py`), porque este mensaje lo lee gente que trabaja en los dos
    idiomas. Lo que sigue sin negociarse es el 422 y el «no se cargó nada»."""
    from app.api.scenarios_api import import_gl_detail as _endpoint  # noqa: F401
    from app.errores import MENSAJES
    src = io.open(BACK / "api" / "scenarios_api.py", encoding="utf-8").read()
    trozo = src.split("huerfanas = filas_sin_cuenta(blocks)")[1][:2000]
    assert "raise ErrorApi(" in trozo
    assert "422" in trozo
    for clave in ("gl.fila_sin_cuenta", "gl.filas_sin_cuenta", "gl.filas_sin_cuenta_y_mas"):
        assert clave in trozo, f"no se usa la clave {clave}"
        assert "No se cargo nada" in MENSAJES[clave]["es"], (
            "tiene que decir que no escribió nada")
        assert "Nothing was loaded" in MENSAJES[clave]["en"], (
            "y tiene que decirlo también en inglés")


def test_el_error_dice_donde_esta_el_problema():
    """Un «hay filas sin cuenta» sin decir cuáles obliga a buscarlas a mano en un
    archivo de miles de renglones."""
    src = io.open(BACK / "api" / "scenarios_api.py", encoding="utf-8").read()
    trozo = src.split("huerfanas = filas_sin_cuenta(blocks)")[1][:2500]
    for dato in ("fila", "departamento", "MESES_ES", "total"):
        assert dato in trozo, f"el error no menciona {dato}"


def test_la_vista_previa_tambien_se_niega():
    """Previsualizar un archivo que va a perder plata no sirve de nada: el
    chequeo corre ANTES de mirar `dry_run`."""
    src = io.open(BACK / "api" / "scenarios_api.py", encoding="utf-8").read()
    pos_check = src.index("huerfanas = filas_sin_cuenta(blocks)")
    pos_dry = src.index("dry_run", pos_check)
    assert pos_check < pos_dry, "el chequeo tiene que correr antes de ramificar por dry_run"


def test_el_caso_real_del_actual_2024_queda_documentado():
    """Que el porqué no se pierda: dentro de seis meses, «filas sin cuenta» sin
    contexto parece una validación paranoica."""
    src = io.open(BACK / "importers" / "gl_detail_importer.py", encoding="utf-8").read()
    assert "40,613.30" in src or "40613.30" in src


def test_la_carga_combinada_valida_antes_de_escribir_el_resumen():
    """El archivo trae DOS hojas: Resumen y Detalle. El combinado escribe el
    resumen primero y hace commit.

    Si el GL se negara despues, quedaria el resumen cargado y el detalle no —
    media importacion, con un mensaje diciendo «no se cargo nada». Por eso la
    validacion del GL corre ANTES del snapshot.
    """
    src = io.open(BACK / "api" / "scenarios_api.py", encoding="utf-8").read()
    trozo = src.split("async def import_upload")[-1] if "async def import_upload" in src else src
    pos_val = src.rindex("exigir_filas_con_cuenta(parse_gl_detail(data))")
    pos_snap = src.index("pl = await import_pl_snapshot(", pos_val - 3000)
    assert pos_val < pos_snap, (
        "la validacion del GL tiene que correr antes de escribir el snapshot"
    )


def test_la_validacion_es_una_sola_para_los_dos_caminos():
    """Dos copias de la misma regla se desincronizan: una se arregla y la otra no."""
    src = io.open(BACK / "api" / "scenarios_api.py", encoding="utf-8").read()
    assert src.count("def exigir_filas_con_cuenta") == 1
    assert src.count("exigir_filas_con_cuenta(") >= 3, (
        "los dos caminos de carga tienen que llamar a la misma funcion"
    )
