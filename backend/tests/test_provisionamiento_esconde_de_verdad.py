# -*- coding: utf-8 -*-
"""El provisionamiento tiene que ESCONDER, no solo anotar la decisión.

La matriz se construyó a medias: la capa que registra funcionaba —guardaba,
validaba datos, se copiaba entre propiedades— y la que aplica nunca se cableó.
Se podía desmarcar un departamento, guardarlo, y seguía apareciendo en todos los
selectores. El síntoma es cruel porque no hay error: la pantalla dice «✓ 1
casilla apagada» y no pasa nada.

Estas pruebas cuidan las dos mitades: que la regla exista en un solo lugar, y
que las pantallas de carga la pidan.
"""
import inspect
import io
import os

from app.api import _apagados


def _pantalla(ruta: str) -> str:
    p = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ruta)
    return io.open(p, encoding="utf-8").read()


def test_sin_fila_significa_prendido():
    """La tabla es esparsa: una propiedad recién creada no tiene ninguna fila y
    le tiene que funcionar todo. Por eso se pregunta quién está APAGADO."""
    src = inspect.getsource(_apagados)
    assert "enabled.is_(False)" in src
    assert "enabled.is_(True)" not in src, (
        "si se preguntara por los prendidos, una propiedad sin filas no vería nada")


def test_la_dimension_no_se_desborda():
    """Apagar un departamento para OPEX no puede esconderlo de planilla: son
    cinco decisiones distintas, no un interruptor."""
    src = inspect.getsource(_apagados.dept_apagado)
    assert "if dimension:" in src, "la dimensión tiene que poder filtrar"
    assert "DeptEnablement.dimension == dimension" in src


def test_el_catalogo_viaja_con_lo_apagado():
    """`/departments/` es el embudo por donde pasan todos los selectores. Si lo
    apagado viniera en otra llamada, una pantalla podría pintar la lista antes
    de saber qué esconder."""
    from app.api import audit_api
    src = inspect.getsource(audit_api.listar_departamentos)
    assert '"apagados"' in src
    assert "apagados_por_dimension(db, hotel_id)" in src


# ── Las pantallas de carga ───────────────────────────────────────────────────
# Cada una pide SU dimensión. Sin esto, la matriz se llena y no pasa nada.

def _llamadas_sin_dimension(ruta: str, dim: str) -> list[str]:
    """Las líneas que llaman a `mergeDepts` sin pedir su dimensión.

    Se mira línea por línea y no con una expresión regular sobre todo el
    archivo: la llamada lleva paréntesis adentro
    —`mergeDepts(raw.map(x => x.dept_code), "OPEX")`— y cualquier patrón que
    intente cerrar en el primer `)` se corta a la mitad.
    """
    return [ln.strip() for ln in _pantalla(ruta).splitlines()
            if "mergeDepts(" in ln and f'"{dim}"' not in ln]


def test_el_checkbook_de_opex_filtra_por_opex():
    assert 'mergeDepts(' in _pantalla("app/opex/checkbook/page.tsx")
    sueltas = _llamadas_sin_dimension("app/opex/checkbook/page.tsx", "OPEX")
    assert not sueltas, f"selectores que siguen mostrando todo: {sueltas}"


def test_el_checkbook_de_costos_filtra_por_costos():
    assert 'mergeDepts(' in _pantalla("app/costs/checkbook/page.tsx")
    sueltas = _llamadas_sin_dimension("app/costs/checkbook/page.tsx", "COST")
    assert not sueltas, f"selectores que siguen mostrando todo: {sueltas}"


def test_el_checkbook_de_planilla_filtra_por_planilla():
    """Planilla no usa `mergeDepts` —sus sub-depts (0111, 0122…) no están en el
    catálogo y saldrían como «código — código»—, así que filtra sobre la lista
    de la base."""
    src = _pantalla("app/payroll/checkbook/page.tsx")
    assert 'estaApagado(d.dept_code, "PAYROLL")' in src
    assert "cargarDepartamentos()" in src, (
        "sin cargar el catálogo, `estaApagado` contesta siempre que no")


def test_un_depto_escondido_no_vuelve_por_la_puerta_de_atras():
    """`mergeDepts` deja pasar códigos que ni están en el catálogo, para no
    ocultar datos huérfanos. Esa puerta no puede colar justo a los escondidos."""
    src = _pantalla("lib/cwl-depts.ts")
    assert "!(dim && estaApagado(c, dim))" in src


def test_si_la_api_falla_se_muestra_de_mas_y_no_de_menos():
    """Una pantalla a la que le faltan departamentos por un error de red es peor
    que una con departamentos que sobran: el usuario no sabe que le falta."""
    src = _pantalla("lib/cwl-depts.ts")
    assert "let APAGADOS: Partial<Record<Dimension, string[]>> = {};" in src, (
        "el default tiene que ser «nada escondido»")


def test_esconder_no_resta_del_pl():
    """La regla de oro de esta matriz. Si apagar un departamento borrara plata
    del estado de resultados, esconder algo sería una forma de mover números sin
    dejar rastro."""
    from app.engine import pl_engine, recalculate
    for mod in (pl_engine, recalculate):
        assert "DeptEnablement" not in inspect.getsource(mod), (
            f"{mod.__name__} está mirando el provisionamiento: eso es cálculo, "
            "no visibilidad")


# ── El esqueleto de carga ────────────────────────────────────────────────────
# «Lo que está desplegado va a existir, entonces debe tener planilla, opex,
# costo y todo lo que corresponda» (owner, 2026-08-12).

def test_planilla_ofrece_todos_los_departamentos():
    """El selector salía solo con los que YA tenían gente, más dos escritos a
    mano. Con eso, empezar la planilla de un departamento nuevo era imposible
    desde la pantalla: no aparecía hasta que alguien le metiera una posición."""
    src = _pantalla("app/payroll/checkbook/page.tsx")
    assert "departamentos()" in src, "los extras salen del catálogo, no de una lista"
    assert "EXTRA_PAYROLL_DEPTS" not in src, "ya no hay lista escrita a mano"


def test_los_subdepartamentos_conservan_su_nombre():
    """0111 Front Desk y 0122 Cocina NO están en el catálogo: si el selector se
    armara desde el catálogo solo, saldrían como «código — código»."""
    src = _pantalla("app/payroll/checkbook/page.tsx")
    i_db = src.index("const have = new Set(dbDepts.map")
    i_extra = src.index("const extra = departamentos()")
    assert i_db < i_extra, "los de la base van primero, con su nombre"
    assert "[...dbDepts, ...extra]" in src


def test_no_se_siembran_filas_de_planilla_en_blanco():
    """Una línea de OPEX vacía es una cuenta esperando un monto; una fila de
    planilla vacía sería una persona que no existe."""
    src = _pantalla("app/payroll/checkbook/page.tsx")
    assert "empleado fantasma" in src, "la decisión tiene que estar escrita"


# ── En los REPORTES ──────────────────────────────────────────────────────────
# «Se revisa que el departamento esté en 0 y después se esconde; se esconde
# porque no se usa para ese hotel» (owner, 2026-08-12).

def test_el_reporte_esconde_solo_lo_que_esta_en_cero():
    """Un departamento apagado que TIENE plata se muestra igual. Si se
    escondiera, el reporte mostraría menos de lo que el P&L cobra — la única
    cosa que un reporte de auditoría no puede hacer."""
    import inspect

    from app.api import pl_full_detail_api as mod
    src = inspect.getsource(mod.pl_full_detail)
    assert "if apagados_del_hotel and dept in apagados_del_hotel:" in src
    assert "if not any(abs(v) > 0.005 for v in ingreso + gasto):" in src
    assert "escondidos_con_plata.append" in src, "y el que tiene plata se avisa"


def test_para_el_reporte_apagado_significa_en_TODAS_las_dimensiones():
    """En las pantallas de carga la pregunta es por dimensión —el 0180 no lleva
    planilla porque la gente vive en sus hijos— pero sí tiene OPEX. Con «apagado
    en alguna», el 0180 se caería del reporte teniendo $406,696 de gasto."""
    import inspect

    from app.api import pl_full_detail_api as mod
    src = inspect.getsource(mod.pl_full_detail)
    assert "n >= len(DIMS_DEPT)" in src
