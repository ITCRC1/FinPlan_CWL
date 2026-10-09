# -*- coding: utf-8 -*-
"""El informe operativo: lo que no se puede romper sin que alguien se entere.

La especificacion vive en `informes/INFORME_OPERATIVO.md`. Estas pruebas
vigilan las partes de esa especificacion que el codigo puede violar en silencio.
"""
import inspect
import pathlib
import re

import pytest

from app.informes import armador, datos, extraccion, secciones, secciones2
from app.informes.armador import cargar_narrativa

RAIZ = pathlib.Path(__file__).resolve().parents[2]


# ── la regla que mas caro sale ──────────────────────────────────────────────

def test_los_totales_NO_se_recalculan():
    """Salen de `gasto_por_clase_api._por_mes`, la misma funcion de la pantalla.

    ⚠️ Reimplementar esa suma es la forma mas facil de que el informe diga un
    numero y la pantalla otro, y un informe que no coincide con la pantalla no
    se puede discutir en una reunion.
    """
    fuente = inspect.getsource(extraccion.extraer)
    assert "gasto_por_clase_api" in fuente
    assert "_por_mes" in fuente


def test_se_le_pasa_el_OBJETO_escenario_y_no_el_id():
    """De eso depende la regla de allocation.

    Sin el objeto el parametro queda en `None`, `_excluidos` cae al caso general
    y los totales se van: medido, $10.943,00 en el costo de setiembre 2026.
    """
    fuente = inspect.getsource(extraccion.extraer)
    assert re.search(r"_por_mes\([^)]*escenario=sc", fuente), (
        "La llamada a _por_mes tiene que llevar `escenario=sc`")
    assert "await db.get(Scenario, sid)" in fuente


def test_el_mayor_pasa_por_el_puente_y_por_la_consolidacion():
    """El mayor guarda el departamento de Integrity y el cuadro muestra el de
    FinPlan. Sin el puente, el 0128 (Private Bar) no aparea con el 0121."""
    fuente = inspect.getsource(extraccion.extraer)
    assert "_puente_de_departamentos" in fuente
    assert "consolidate_dept" in fuente


def test_las_cuentas_se_agrupan_por_depto_y_cuenta_NO_por_nombre():
    """El real escribe «UTILITIES - OIL» y el presupuesto «Oil (Boat and
    Equipment)» para la misma 7395. Si la llave incluyera el nombre, el cuadro
    mostraria DOS variaciones donde hay una, y ninguna de las dos seria la
    verdadera."""
    corte = {
        "meses": {}, "detalle": {}, "pl": {}, "deptos": {}, "mayor": [],
        "payroll": {}, "stats": {"ACT": []}, "avisos": [],
        "escenarios": {"ACT": {"id": "a", "rotulo": "ACTUAL"},
                       "BUD": {"id": "b", "rotulo": "BUDGET"}},
        "lineas": {"opex": [
            {"esc": "ACT", "dept_code": "0210", "account_code": "7395",
             "account_name": "UTILITIES - OIL", "mes": 28640.26, "ytd": 0.0},
            {"esc": "BUD", "dept_code": "0210", "account_code": "7395",
             "account_name": "Oil (Boat and Equipment)", "mes": 16225.00,
             "ytd": 0.0}]},
    }
    D = datos.Datos(2026, 9, corte)
    pc = D.por_cuenta("opex")
    assert len(pc) == 1, "la misma cuenta quedo partida en dos filas"
    fila = pc[("0210", "7395")]
    assert fila["ACT"] == pytest.approx(28640.26)
    assert fila["BUD"] == pytest.approx(16225.00)
    # Y el rotulo que se muestra es el del mayor, en mayusculas.
    assert fila["nombre"] == "UTILITIES - OIL"


# ── el informe no puede escribir nada ───────────────────────────────────────

#: Lo que el informe NO puede tocar. Es un reporte: si empezara a escribir, el
#: mes tendria dos origenes y los totales cuadrarian igual.
PROHIBIDAS = ("Precierre", "PrecierreFila", "PrecierrePosicion", "ActualEntry",
              "ActualPLLine", "OpexEntry", "CostEntry", "RevenueAccountEntry",
              "PayrollConceptEntry", "Scenario", "MayorMovimiento")


@pytest.mark.parametrize("modulo", [extraccion, datos, armador, secciones,
                                    secciones2])
def test_el_informe_solo_LEE(modulo):
    fuente = inspect.getsource(modulo)
    for verbo in ("session.add", "db.add", "db.commit", "session.commit",
                  ".delete(", "INSERT ", "UPDATE ", "DELETE "):
        assert verbo not in fuente, (
            f"{modulo.__name__} parece escribir ({verbo}): el informe solo lee")


# ── la narrativa y los departamentos tienen que hablarse ────────────────────

def test_las_claves_de_narrativa_son_departamentos_que_existen():
    """Si alguien renombra un departamento en `datos.py`, las claves de la
    narrativa dejan de aparear y el analisis DESAPARECE en silencio — sale
    [PENDIENTE] donde habia tres parrafos escritos."""
    validos = {n for n, _ in datos.OPERATIVOS} | {n for n, _ in datos.OVERHEAD}
    nar = cargar_narrativa(2026, 9)
    assert nar, "falta la narrativa de setiembre 2026, que es el modelo"
    huerfanas = set(nar.get("dept", {})) - validos
    assert not huerfanas, (
        f"Claves de narrativa sin departamento: {sorted(huerfanas)}. "
        f"Departamentos validos: {sorted(validos)}")


def test_setiembre_2026_tiene_el_analisis_completo():
    """Es el modelo de referencia de la especificacion: si se queda sin alguna
    de sus partes, deja de servir de modelo."""
    nar = cargar_narrativa(2026, 9)
    for clave in ("resumen", "hallazgos", "contexto", "dept_resumen", "agenda",
                  "brechas", "clasificacion", "opex_favorables", "opex_impactos",
                  "payroll_conceptos", "propiedad_notas", "sin_presupuesto"):
        assert nar.get(clave), f"setiembre 2026 perdio «{clave}»"
    assert len(nar["hallazgos"]) >= 5, "la seccion 2 pide entre cinco y siete"
    # Cada departamento con analisis trae comentario y preguntas.
    for dep, bloque in nar["dept"].items():
        assert bloque.get("comentario"), f"{dep} sin comentario"
        assert bloque.get("preguntas"), f"{dep} sin preguntas al gerente"


def test_la_especificacion_existe_y_nombra_las_reglas():
    """El `.md` es lo que hace que el informe salga igual todos los meses.
    Si se borra o se vacia, el informe deja de ser reproducible."""
    md = RAIZ / "informes" / "INFORME_OPERATIVO.md"
    assert md.exists(), "falta informes/INFORME_OPERATIVO.md"
    t = md.read_text(encoding="utf-8")
    for pieza in ("Las reglas que hacen que los números aten",
                  "Lista de verificación antes de entregar",
                  "Las claves de narrativa",
                  "escenario", "4999"):
        assert pieza in t, f"la especificacion ya no menciona «{pieza}»"


# ── el endpoint ─────────────────────────────────────────────────────────────

def test_el_endpoint_no_llama_a_ningun_modelo():
    """Owner, 2026-10-08: *«si solo quiero que me generes los cuadros y despues
    lo subo aca y me lo analizas»*.

    El boton saca los cuadros y nada mas: sin llave de API, sin costo y sin
    riesgo de que un modelo escriba una cifra que no existe.
    """
    from app.api import informe_api
    fuente = inspect.getsource(informe_api)
    for prohibido in ("anthropic", "Anthropic", "cliente_ia", "ANTHROPIC_API_KEY"):
        assert prohibido not in fuente


def test_el_endpoint_manda_el_cuadre_en_la_cabecera():
    """Quien baje el informe tiene que poder verificarlo sin volver a preguntar."""
    from app.api import informe_api
    fuente = inspect.getsource(informe_api.operativo)
    for cabecera in ("X-Informe-Cuadra", "X-Informe-GOP-Reporte",
                     "X-Informe-GOP-Motor", "X-Informe-Con-Analisis"):
        assert cabecera in fuente
    # Y expuestas, o el navegador no las deja leer.
    assert "Access-Control-Expose-Headers" in fuente


def test_el_endpoint_esta_registrado_y_pide_token():
    """⚠️ `app.routes` NO sirve: los routers incluidos quedan envueltos en
    `_IncludedRouter` y no se aplanan. Se mira el esquema, que es lo que de
    verdad se publica.

    Y pedir token no es formalidad: el informe trae salarios por departamento y
    proveedores con monto.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    cliente = TestClient(app, raise_server_exceptions=False)
    rutas = cliente.app.openapi()["paths"]
    assert "/api/informes/operativo/{anio}/{mes}/" in rutas
    assert "/api/informes/operativo/{anio}/{mes}/estado/" in rutas
    assert cliente.get("/api/informes/operativo/2026/9/").status_code in (401, 403)
    assert cliente.get(
        "/api/informes/operativo/2026/9/estado/").status_code in (401, 403)


def test_el_cuadre_compara_contra_el_credito_de_allocation():
    """⚠️ El GOP del reporte y el del motor difieren por el credito 4999 que el
    tab descarta. Si la diferencia NO es exactamente ese credito, hay otra causa
    y el informe no se publica."""
    fuente = inspect.getsource(armador.cuadre)
    assert "creditos_allocation" in fuente
    assert '"cuadra"' in fuente


def test_falta_de_precierre_se_DICE_no_se_revienta():
    """Un mes sin Pre-Cierre tiene que contestar que falta, no un 500."""
    fuente = inspect.getsource(extraccion.extraer)
    assert "raise FaltaDato" in fuente
    from app.api import informe_api
    assert "FaltaDato" in inspect.getsource(informe_api.operativo)
    assert "FaltaDato" in inspect.getsource(informe_api.estado)
