# -*- coding: utf-8 -*-
"""EL AUDIT CONSOLIDA EL DEPARTAMENTO Y APAREA EL INGRESO POR RENGLON.

Dos reportes del owner el 2026-09-10, con UNA causa cada uno:

  * *«hay spa department 0130 y spa 0140, la vista debe ser consolidada no
    separada»*. El Spa son TRES departamentos —0132 planilla, 0130 gerencia,
    0140 el padre— y el tab los dibujaba como tres bloques: uno con el
    ingreso, otro con la planilla. Los tres correctos por separado, y ninguno
    el Spa. La causa: `consolidate_dept` sube UN escalon y la cadena tiene dos.

  * *«veo que transportation no tiene revenue en forecast ni budget»*. Lo
    tenia —229.805,70 al anio en el Budget, medido contra el reporte que ya
    estaba extraido— pero la fila del checkbook se creaba con el departamento
    VACIO y con la llave del driver (`transport`) en vez de una cuenta. El
    Audit apareaba `|transport|` contra el `0152|4500|` del Actual y no
    encontraba nada.

Los dos fallaban EN SILENCIO: cada version por separado mostraba su numero
correcto. Es el modo de falla que este tab existe para cazar, y lo tenia
adentro.
"""
import io
import os
import re

RAIZ = os.path.join(os.path.dirname(__file__), "..", "..")
API = os.path.join(os.path.dirname(__file__), "..", "app", "api", "auditoria_api.py")
AUD = os.path.join(RAIZ, "frontend", "app", "month-end", "pl", "Auditoria.tsx")


def _leer(p):
    return io.open(p, encoding="utf-8").read()


# ── La cadena de padres sube COMPLETA ────────────────────────────────────────

def test_la_cadena_del_spa_sube_hasta_la_raiz():
    from app.engine import pl_engine
    # Un escalon no alcanza: 0132 se queda en 0130 y el Spa sigue partido.
    assert pl_engine.consolidate_dept("0132") == "0130"
    # La raiz junta los tres.
    for d in ("0130", "0132", "0140"):
        assert pl_engine.consolidate_dept_raiz(d) == "0140", d


def test_la_raiz_no_se_cuelga_con_un_ciclo():
    """Un padre mal declarado en el catalogo no puede colgar la peticion."""
    from app.engine import pl_engine
    pl_engine.set_dept_catalog([
        {"dept_code": "0A", "default_pl_group": "SPA", "parent_dept_code": "0B"},
        {"dept_code": "0B", "default_pl_group": "SPA", "parent_dept_code": "0A"},
    ])
    try:
        assert pl_engine.consolidate_dept_raiz("0A") in ("0A", "0B")
    finally:
        pl_engine.reset_dept_catalog()
    assert pl_engine.consolidate_dept_raiz("0132") == "0140"


def test_los_departamentos_de_un_grupo_caen_todos_en_la_misma_raiz():
    """Consolidar de a un escalon dejaria familias partidas en otros lados."""
    from app.engine import pl_engine
    for hijo, padre in (("0112", "0110"), ("0113", "0110"), ("0122", "0120"),
                        ("0184", "0180"), ("0191", "0190")):
        assert pl_engine.consolidate_dept_raiz(hijo) == padre, hijo


# ── El endpoint usa la raiz, y en los dos lugares ────────────────────────────

def test_el_audit_muestra_la_raiz_y_no_el_departamento_crudo():
    src = _leer(API)
    assert "raiz = pl_engine.consolidate_dept_raiz(e.dept_code)" in src
    # El bloque de opciones no usadas tambien: si usara el crudo, dibujaria un
    # bloque «0130» que ya no existe, con subtotal propio y nada al lado.
    assert "raiz = pl_engine.consolidate_dept_raiz(dept)" in src
    # Y el nombre sale de la raiz: decir 0140 y rotularlo «Spa (gerencia)»
    # seria peor que no consolidar.
    assert 'nombres.get(raiz, raiz)' in src
    assert 'por_depto.setdefault(raiz' in src


def test_ninguna_fila_del_audit_se_queda_con_el_departamento_crudo():
    """Ninguna fila de salida puede llevar el departamento DEL ASIENTO.

    `e.dept_code` es lo que trajo el asiento —puede ser 0132 o 0130—; lo que
    sale a la pantalla tiene que ser la raiz. La matriz por departamento
    (`for dept in sorted(por_depto)`) no cuenta: `por_depto` ya se llena con la
    raiz, asi que ahi `dept` ES la raiz.
    """
    src = _leer(API)
    crudos = re.findall(r'"dept_code":\s*e\.dept_code', src)
    assert crudos == [], f"quedo una fila con el departamento del asiento: {crudos}"
    # La matriz se llena desde `por_depto`, y `por_depto` desde la raiz.
    assert "por_depto.setdefault(raiz" in src
    assert "for dept in sorted(por_depto):" in src


# ── El ingreso: departamento propio y apareo por renglon ─────────────────────

def test_el_ingreso_del_checkbook_recibe_su_departamento():
    src = _leer(API)
    # Sale del mapeo, no de una lista escrita en el modulo.
    assert "dept_de_linea" in src
    assert 'AccountMapping.report_line_code.like("REV_%")' in src
    assert 'dept_de_linea.get(linea, "")' in src
    # Y ya no se crea con el departamento en blanco.
    assert '_AsientoDeCheckbook(\n                    "", cuenta' not in src


def test_el_ingreso_se_junta_por_renglon_no_por_cuenta():
    src = _leer(API)
    assert "es_ingreso = tipo == pl_engine.TIPO_INGRESO" in src
    assert '"account_code": "" if es_ingreso else e.account_code' in src


def test_la_llave_de_la_pantalla_incluye_la_linea():
    """Sin la linea, las tres lineas de A&B de un depto se pisan entre ellas."""
    src = _leer(AUD)
    assert '${f.linea || ""}' in src
    assert "linea: string | null" in src


def test_las_filas_que_colapsan_al_consolidar_se_suman():
    """Dos renglones identicos con montos distintos es peor que no consolidar."""
    from app.api.auditoria_api import _acumular
    destino, indice = [], {}
    base = {"dept_code": "0140", "account_code": "7065", "outlet": "",
            "tipo": "Opex", "linea": "OPEX_SPA", "movimiento": False}
    _acumular(destino, indice, {**base, "monto": 100.0})
    _acumular(destino, indice, {**base, "monto": 25.5, "movimiento": True})
    assert len(destino) == 1
    assert destino[0]["monto"] == 125.5
    # Una opcion sin movimiento junto a una que si lo tuvo, se movio.
    assert destino[0]["movimiento"] is True
    # Dos cuentas que van a RENGLONES distintos NO son la misma fila: juntarlas
    # esconderia justamente eso.
    _acumular(destino, indice, {**base, "linea": "OPEX_ROOMS", "monto": 9.0})
    assert len(destino) == 2
