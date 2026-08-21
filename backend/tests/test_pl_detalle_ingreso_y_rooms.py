# -*- coding: utf-8 -*-
"""El detalle por departamento cierra con utilidad, y Rooms se abre en sus sets.

**El defecto que arreglan.** Los bloques por departamento mostraban solo el
gasto en los escenarios armados en la app: el ingreso se presupuesta a nivel de
línea (rate cards, capture rate, cuota) y el reporte solo sabía leer cuentas.
Rooms salía con «utilidad −$645,551», que es su costo con el signo cambiado. Un
bloque que enseña la mitad de la ecuación no se puede leer.

**Y el que casi introducen.** Al abrir Rooms en Standard / Villas / Residencias
aparecen cuatro tarjetas del mismo tamaño. Si alguien las suma, Rooms cuenta dos
veces — las tres de abajo son el consolidado ABIERTO, no departamentos más.
"""
import inspect

from app.api import pl_full_detail_api as mod


def test_el_ingreso_del_checkbook_entra_en_los_bloques():
    """Sin esto, un departamento presupuestado en la app muestra puro gasto."""
    src = inspect.getsource(mod.pl_full_detail)
    assert "_ingreso_de_checkbook(db, scenario" in src


def test_no_se_prorratea_el_ingreso_por_cuenta():
    """El ingreso del checkbook NO tiene apertura por cuenta. Repartirlo entre
    cuentas para que «se vea completo» sería dibujar precisión que el dato no
    tiene; entra como una fila por línea."""
    src = inspect.getsource(mod._ingreso_de_checkbook)
    assert "REVENUE_LINE_LABELS" in src, "la fila se rotula con la línea"
    assert "prorrat" in src.lower(), "la decisión tiene que estar escrita"


def test_el_ingreso_va_al_departamento_del_grupo_no_al_del_mapeo():
    """El Spa factura por la 0130 y su gasto vive en la 0140: yendo por la regla
    de mapeo, la 0130 quedaría de puro ingreso al lado de otra de puro gasto."""
    src = inspect.getsource(mod._ingreso_de_checkbook)
    assert "REVENUE_LINE_TO_GROUP" in src
    assert "OPERATING_DEPT_GROUPS" in src
    assert "con_gasto" in src, "gana el departamento del grupo que tenga gasto"


def test_el_ingreso_sin_grupo_no_se_pierde():
    """Sustainability y Misceláneos no son departamentos operativos: son $251k en
    el Budget 2027, demasiado para dejarlos en un cajón sin nombre."""
    src = inspect.getsource(mod._ingreso_de_checkbook)
    assert "depto_de_linea_pl" in src, "hay que preguntarle al catálogo"
    assert "SIN_DEPTO" in src, "y si nada lo ubica, va al cajón — pero se ve"


def test_solo_los_escenarios_de_checkbook_reciben_ingreso_por_linea():
    """Un escenario importado ya trae el ingreso abierto por cuenta desde el GL.
    Meterle además la línea del checkbook lo contaría dos veces."""
    src = inspect.getsource(mod._ingreso_de_checkbook)
    assert 'source_mode", "imported") != "checkbook"' in src
    assert "return {}" in src


# ── Rooms en cuatro bloques ──────────────────────────────────────────────────

def test_los_sets_no_se_suman_a_ningun_total():
    """La trampa de las cuatro tarjetas iguales."""
    src = inspect.getsource(mod._bloques_de_rooms)
    assert '"es_apertura": True' in src
    total = inspect.getsource(mod.pl_full_detail)
    assert "tot_ingreso[i] += ingreso[i]" in total
    # El acumulado corre en el bucle de departamentos, ANTES de abrir Rooms:
    # los sets se generan después y no pasan por ahí.
    assert total.index("tot_ingreso[i] += ingreso[i]") < total.index("_bloques_de_rooms(")


def test_el_consolidado_incluye_a_los_sets():
    """Cuando el reparto está activo el costo de las villas vive en su propio
    departamento. Sin sumarlos, el «consolidado» era la parte que se quedó."""
    src = inspect.getsource(mod.pl_full_detail)
    assert "acum.por_deptos(deptos_rooms)" in src
    assert "con_datos - deptos_rooms" in src, "y los sets no llevan bloque suelto"


def test_la_apertura_no_aplica_a_los_importados():
    """Los sets se calculan con los auxiliares de la app; un escenario importado
    tiene su P&L en el GL. Son dos fuentes distintas del mismo departamento."""
    src = inspect.getsource(mod._bloques_de_rooms)
    assert 'source_mode", "imported") != "checkbook"' in src
    assert "apertura_no_aplica" in src


def test_sin_ingreso_por_set_no_hay_apertura():
    """Si no hay tarifas por categoría, cada set saldría con su costo y cero
    ingreso: el mismo defecto que se vino a arreglar, un nivel más abajo."""
    src = inspect.getsource(mod._bloques_de_rooms)
    assert 'if not any(any(f["revenue"]) for f in filas_set):' in src


def test_la_apertura_avisa_cuando_no_da_lo_mismo_que_el_consolidado():
    """En el Budget 2027 Working son $326,712 de Villas y Residencias que los
    drivers facturan y la línea del checkbook no tiene. Esconderlo taparía el
    hallazgo; el consolidado sigue siendo el que manda."""
    src = inspect.getsource(mod._bloques_de_rooms)
    assert "apertura_no_cuadra" in src
    aviso = inspect.getsource(mod.pl_full_detail)
    assert "NO suma lo " in aviso and "El consolidado es el que manda" in aviso


def test_cada_set_trae_estadisticas_ingreso_y_costo():
    """El owner pidió el detalle completo: «desde las estadísticas, revenue,
    planilla, opex y net profit»."""
    src = inspect.getsource(mod._bloques_de_rooms)
    for pedazo in ("Noches disponibles", "Noches ocupadas", "Ocupación", "ADR",
                   "RevPAR", "INGRESOS", "UTILIDAD NETA"):
        assert pedazo in src, f"falta «{pedazo}» en la apertura"


def test_el_credito_de_reparto_no_se_pierde_en_los_sets():
    """La 4999 es gasto que SE FUE. Su cuenta es de clase 4, así que el recorrido
    de 5/6/7 la deja fuera: sin recogerla aparte, Rooms Standard mostraría el
    costo entero, incluido el que entregó."""
    src = inspect.getsource(mod._bloques_de_rooms)
    assert "REPARTOS" in src
    assert 'if _clase(c) == "4"' in src


def test_el_detalle_por_cuenta_del_set_sale_del_mismo_recorrido():
    """Dos cálculos del mismo costo se separan. El detalle se llena en `cargar`,
    junto a los cubos."""
    from app.api import rooms_sets_api
    src = inspect.getsource(rooms_sets_api.rooms_por_set)
    assert "detalle[destino].setdefault" in src
    i_cubo = src.index('costo[destino][cubo][mes_idx] += v')
    i_det = src.index("detalle[destino].setdefault")
    assert abs(i_det - i_cubo) < 400, "se llenan en el mismo lugar"


def test_las_estadisticas_no_se_exportan_como_dolares():
    """Noches con formato de moneda se leen «$12,410» — el mismo error que el
    Excel original cometía con los ratios."""
    from app.export import pl_full_detail_excel as xl
    assert "stat" in xl.ESTILO
    assert 'FMT_STAT if f["tipo"] == "stat"' in inspect.getsource(xl._fila)


def test_el_excel_marca_las_hojas_de_apertura():
    """En un libro de veinte pestañas iguales nada distingue una apertura."""
    from app.export import pl_full_detail_excel as xl
    src = inspect.getsource(xl.build_pl_full_detail_workbook)
    assert 'b.get("es_apertura")' in src
    assert "NO se suma aparte" in src


# ── Secciones abiertas pero en cero ──────────────────────────────────────────

def test_una_seccion_sembrada_en_cero_no_desaparece():
    """«¿Hay alguna razón por que Club Madresal no tiene las cuentas OPEX?»

    Sí las tenía —23 de OPEX y 2 de costo— pero en cero, y `_Acum.add` descarta
    los ceros: la sección entera se caía del bloque y el departamento parecía no
    gastar en eso. No es lo mismo «no gasta» que «todavía no lo presupuesté».
    """
    src = inspect.getsource(mod.pl_full_detail)
    assert "configuradas = await _clases_configuradas(db, scenario)" in src
    assert "abierta = clase in configuradas.get(dept, set())" in src
    assert "not abierta" in src, "la sección abierta tiene que sobrevivir al filtro"


def test_solo_cuenta_lo_que_esta_abierto_en_el_checkbook():
    """La señal es «hay cuentas sembradas», no «existe el departamento»: si
    saliera de la existencia del depto, todos mostrarían las cuatro secciones y
    la información se perdería en el ruido."""
    src = inspect.getsource(mod._clases_configuradas)
    assert "OpexEntry" in src and "CostEntry" in src
    assert "consolidate_dept" in src, "los sub-departamentos van a su padre"
