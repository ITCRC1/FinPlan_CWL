# -*- coding: utf-8 -*-
"""Los Gastos de Propiedad salen completos, y con el nombre bueno.

«Gastos de la propiedad son muchos detalles, por qué no están todas las cuentas,
aunque no tengan saldo… deben estar» (owner, 2026-08-12). El bloque mostraba dos
de once: las que tenían movimiento. Parecía que el resto no existiera, cuando lo
que pasa es que no se han presupuestado — la misma confusión entre «no aplica» y
«todavía no lo cargué» que había en las secciones de los departamentos.

Estas cuentas NO llevan departamento (son de la compañía, no de una operación),
así que a diferencia de OPEX y costos no hay que sembrar filas: la lista sale del
catálogo y ya.
"""
import inspect

from app.api import pl_full_detail_api as mod


def test_el_bloque_lista_todas_las_cuentas_del_catalogo():
    src = inspect.getsource(mod.pl_full_detail)
    assert "_cuentas_de_propiedad(db)" in src
    assert "ya_estan" in src, "y no repite las que ya tienen fila"


def test_las_cuentas_agregadas_no_mueven_el_total():
    """Están para que se vea qué falta, no para cambiar la cifra."""
    src = inspect.getsource(mod.pl_full_detail)
    i_add = src.index("_cuentas_de_propiedad(db)")
    i_tot = src.index('"TOTAL GASTOS DE PROPIEDAD"')
    assert i_add < i_tot, "el total se calcula después, sobre filas en cero"


def test_el_bloque_va_ordenado_por_cuenta():
    """Si no, las que se agregaron en cero quedan al final y el bloque parece
    dos listas pegadas en vez de un mayor."""
    src = inspect.getsource(mod.pl_full_detail)
    assert 'propiedad.sort(key=lambda f: ((f.get("cuenta") or "zzzz")' in src


def test_solo_toma_las_de_clase_8():
    src = inspect.getsource(mod._cuentas_de_propiedad)
    assert '_clase((m.account_code or "").strip()) == "8"' in src


def test_el_rotulo_sale_de_la_misma_fuente_que_el_resto():
    """Sacándolo de otra parte, la misma cuenta se llamaría distinto según en
    qué bloque aparezca."""
    src = inspect.getsource(mod.pl_full_detail)
    assert "nombres_cuenta.get(cuenta) or cuenta" in src


# ── El nombre de la cuenta ───────────────────────────────────────────────────

def _mejor(nombres):
    """La misma elección que hace `_nombres_de_cuenta`, aislada para probarla."""
    import re
    limpios = [n for n in nombres if not n[-1:].isdigit()]
    if limpios:
        return sorted(limpios, key=lambda n: (-len(n), n))[0]
    troncos = {re.sub(r"\s*\d+$", "", n).strip() for n in nombres}
    if len(troncos) == 1:
        unico = troncos.pop()
        if unico:
            return unico
    return sorted(nombres, key=lambda n: (-len(n), n))[0]


def test_prefiere_la_variante_sin_el_digito_pegado():
    """El catálogo guarda «RENT1 | RENT»; se tomaba la primera y el reporte
    decía «RENT1»."""
    assert _mejor({"RENT1", "RENT"}) == "RENT"
    assert _mejor({"DEPRECIATION1", "DEPRECIATION2", "DEPRECIATION"}) == "DEPRECIATION"
    assert _mejor({"OWNERS FEE1", "OWNERS FEES"}) == "OWNERS FEES"


def test_si_todas_van_numeradas_usa_el_tronco():
    """La 8015 tiene «PROPERTY INSURANCE1» hasta la 5: es la misma cuenta
    repetida, no cinco seguros distintos."""
    assert _mejor({f"PROPERTY INSURANCE{i}" for i in range(1, 6)}) == "PROPERTY INSURANCE"


def test_no_mutila_un_nombre_que_de_verdad_lleva_numero():
    """Si los troncos difieren, no hay un nombre común que inventar."""
    assert _mejor({"COSTOS 1", "GASTOS 2"}) in {"COSTOS 1", "GASTOS 2"}


def test_la_eleccion_no_cambia_entre_recargas():
    """Antes ganaba la primera fila que devolviera la consulta, y ese orden no
    está garantizado: el mismo reporte podía rotular distinto dos veces
    seguidas. Es el mismo defecto que tenía el FALLBACK del resolvedor."""
    nombres = {"OWNERS FEE1", "OWNERS FEES", "OWNERS FEE"}
    assert len({_mejor(set(nombres)) for _ in range(20)}) == 1
    src = inspect.getsource(mod._nombres_de_cuenta)
    assert "code not in out" not in src, "eso dependía del orden de la consulta"


# ── Lo que no pasa por una cuenta ────────────────────────────────────────────

def test_las_lineas_calculadas_por_driver_entran_al_bloque():
    """«Yo ya tengo fees y capital para 2027, ¿por qué no están acá?»

    El honorario de administración y la reserva de capital salen de un PORCENTAJE
    sobre los ingresos: el motor los siembra a nivel de LÍNEA y nunca existe una
    fila de cuenta con ese monto. El bloque leía cuentas, así que no los veía —
    el resumen decía $842,577 abajo del GOP y el detalle mostraba $414,000.
    """
    src = inspect.getsource(mod.pl_full_detail)
    assert "pl_engine._NONOP_LINE_TO_BUCKET" in src
    assert "(calculado)" in src, "la fila tiene que decir que no sale de una cuenta"


def test_el_monto_calculado_sale_del_motor_no_de_una_cuenta_inventada():
    """Tomándolo del motor, el bloque cierra contra el P&L por construcción y no
    por coincidencia."""
    src = inspect.getsource(mod.pl_full_detail)
    assert "meses_linea = pl.get(code)" in src
    assert "resto[i] -= f[\"meses\"][i]" in src, "se agrega solo lo que falta"


def test_el_bloque_de_propiedad_se_audita():
    """No lo hacía, y por eso el faltante vivió ahí sin que nada lo señalara: el
    cuadre solo miraba ingresos y gastos operativos."""
    src = inspect.getsource(mod.pl_full_detail)
    assert "dif_bg" in src and '"dif_propiedad": dif_bg' in src
    assert "ing_ok and gas_ok and bg_ok" in src, "y cuenta para el semáforo"


def test_el_impuesto_de_renta_queda_fuera_por_LOS_DOS_lados():
    """Va abajo del GOP pero no es un gasto de la propiedad. Sacarlo de un solo
    lado descuadra el bloque: en el Actual 2026 eran $123,179 que salían en el
    detalle y no del otro lado."""
    src = inspect.getsource(mod.pl_full_detail)
    assert src.count("LINEA_IMPUESTO") >= 5, (
        "tiene que excluirse del acumulador, del mini-checkbook, del catálogo, "
        "del relleno por driver y del cuadre")
    assert 'LINEA_IMPUESTO = "INCOME_TAXES"' in src
