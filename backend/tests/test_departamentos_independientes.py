# -*- coding: utf-8 -*-
"""
CADA DEPARTAMENTO INDEPENDIENTE SE QUEDA CON LO SUYO.

Cinco departamentos que el owner declaró independientes (2026-08-13) perdían
gasto hacia otro — casi siempre Habitaciones. El caso que lo destapó fue el
Spa, y está contado en detalle abajo porque los otros cuatro son el mismo
patrón con otros números.

## El Spa

**Decisión del owner (2026-08-13):** el padre del Spa es `0140` y de él cuelgan
`0130` (gerencia) y `0132` (planilla). «Son historias distintas»: nada del Spa
puede terminar sumado al gasto de Habitaciones.

## Qué estaba pasando

El Spa tiene tres códigos de departamento, y las 51 reglas de mapeo estaban en
`0130` mientras el dato entraba por `0140`. Peor: había **dos importadores** y
cada uno mandaba «spa» a un departamento distinto —
`gl_detail_importer` al `0140` y `actual_pl_importer` al `0130`— así que el
mismo Spa entraba por un lado o por el otro según cómo se cargara.

Un renglón del mayor que dijera «Spa · 7065 Cleaning Supplies» entraba con
`0140`, que no tenía regla para la 7065 ni padre del cual heredar. El
resolvedor caía al FALLBACK, que agarra la regla de esa cuenta del departamento
de código **menor** — el `0110`, Habitaciones.

## Por qué nadie lo vio

Porque el GOP no se mueve. La plata no se pierde: se sienta en la línea de al
lado. Habitaciones inflado y Spa desinflado, exactamente en el mismo monto, con
todos los totales cuadrando. El tab de Control decía «$0 se pierde», y tenía
razón.

Es el mismo patrón de los $92,108 del crédito de reparto de Rooms (mig 089) y
de la planilla de RRHH del `0184` (mig 092). Por eso esta prueba mira la
propiedad de verdad —«ninguna cuenta del Spa termina en Habitaciones»— y no una
lista de cuentas, que se queda corta apenas contabilidad use una nueva.
"""
import json
import pathlib

import pytest

from app.engine import pl_engine
from app.seed_department_catalog import build_rows

MAPEO = (pathlib.Path(pl_engine.__file__).parents[1] / "seed_data" / "mapping_pl.json")

PADRE = "0140"
HIJOS = ("0130", "0132")


@pytest.fixture(scope="module")
def mapeo():
    reglas = json.loads(MAPEO.read_text(encoding="utf-8"))["account_mapping"]
    pl_engine.set_dept_catalog(build_rows())
    return pl_engine.construir_resolvedor(reglas), reglas


def test_ninguna_cuenta_del_spa_termina_en_habitaciones(mapeo):
    """La propiedad que importa, sobre TODAS las cuentas del catálogo."""
    resolve, reglas = mapeo
    cuentas = sorted({m["account_code"] for m in reglas if m.get("account_code")})
    fugas = []
    for dept in (PADRE, *HIJOS):
        for cuenta in cuentas:
            regla, modo = resolve(dept, cuenta)
            if regla and regla["report_line_code"] == "OPEX_ROOMS":
                fugas.append(f"{dept}/{cuenta} → OPEX_ROOMS ({modo})")
    assert not fugas, (
        "gasto del Spa aterrizando en Habitaciones — el GOP cuadra igual, así "
        f"que no da error:\n  " + "\n  ".join(fugas[:20]))


def test_las_reglas_viven_en_el_padre(mapeo):
    """En el padre, no en un hijo: la herencia va de hijo a padre. Con las
    reglas en `0130`, el `0140` no heredaba nada — que es de dónde salió todo
    esto."""
    _, reglas = mapeo
    del_padre = [m for m in reglas if (m.get("dept_code") or "") == PADRE]
    assert len(del_padre) >= 50, (
        f"el {PADRE} tiene {len(del_padre)} reglas; las del Spa deberían estar acá")


def test_los_hijos_heredan_del_padre(mapeo):
    """`0130` y `0132` no necesitan reglas propias: cuelgan del `0140`."""
    resolve, _ = mapeo
    for hijo in HIJOS:
        assert PADRE in pl_engine._cadena_de_padres(hijo), (
            f"{hijo} no cuelga de {PADRE}: sin la cadena de padres no hereda nada")
        for cuenta in ("6000", "7065", "7400", "7105"):
            regla, modo = resolve(hijo, cuenta)
            assert regla["report_line_code"] == "OPEX_SPA", (hijo, cuenta, modo)
            assert modo in ("exact", "parent"), (hijo, cuenta, modo)


def test_los_dos_importadores_mandan_el_spa_al_mismo_lado():
    """Mandaban «spa» a departamentos distintos, así que el mismo Spa entraba
    por uno o por otro según cómo se cargara el dato."""
    from app.importers.actual_pl_importer import _DEPT_KEYWORDS as ACTUALES
    from app.importers import gl_detail_importer as gl

    destino_actuales = next(d for k, d in ACTUALES if k == "spa")
    assert destino_actuales == PADRE, (
        f"actual_pl_importer manda «spa» a {destino_actuales} y no a {PADRE}")

    # El del GL tiene la tabla dentro de la función, así que se lee del fuente.
    texto = pathlib.Path(gl.__file__).read_text(encoding="utf-8")
    assert f'("spa", "{PADRE}")' in texto, (
        f"gl_detail_importer no manda «spa» a {PADRE}")


def test_el_credito_de_reparto_del_spa_se_anula_sobre_su_linea(mapeo):
    """La 4999 de un departamento va a la MISMA línea que sus débitos, para que
    el asiento de reparto netee ahí y no le reste a otro. Sin regla propia, la
    del Spa le restaba a Habitaciones."""
    resolve, _ = mapeo
    regla, modo = resolve(PADRE, "4999")
    assert regla["report_line_code"] == "OPEX_SPA", (regla["report_line_code"], modo)


# ─────────────────────────────────────────────────────────────────────────────
# Los otros departamentos independientes, mismo criterio (owner, 2026-08-13).
#
#   0210 Utilities        · overhead, solo. Sus 8 reglas vivían en el 0205.
#   0205 Claro del Bosque · overhead, solo. Compartía dept_code con Utilities.
#   0151 Tienda · 0165 Gift Shop · operativos y generadores de ingreso: van
#        ARRIBA del GOP, no en overhead. Desde el 2026-08-13 cada uno con su
#        propia linea de ingreso, gasto y utilidad — antes compartian una sola
#        llamada «Retail-Gift Shop», que los mostraba sumados.
#   0121 Private Bar      · operativo, aparte de A&B.
#
# A todos les faltaba el núcleo de cuentas que cualquier departamento usa
# —planilla, suministros, uniformes, capacitación y la 4999 del reparto— así
# que por esas cuentas caían en Habitaciones.
SIN_NUCLEO_A_PROPOSITO = {
    "280": "Miscelaneos es SOLO ingreso y no tiene costo (owner, 2026-08-13)",
    # «0250 no hay planilla, solo gastos de la propiedad» (owner, 2026-08-14).
    # Es el espejo del 280: aquel es solo ingreso, este es solo gasto de la
    # propiedad (8xxx, below-GOP). No tiene personal ni opex propio, así que no
    # le falta ninguna regla — le sobrarían.
    "0250": "Property Expenses es SOLO below-GOP (8xxx): no tiene planilla ni "
            "opex propio (owner, 2026-08-14)",
    # «0162 no hace nada aca, no tiene gastos» (owner, 2026-08-14). Es la otra
    # mitad de una decision ya tomada: el 0162 es el INGRESO de lavanderia y el
    # 0161 es el que lleva el gasto y lo reparte. El 0162 arrastraba trece
    # reglas de gasto que nunca recibieron un colon, y mientras existieran el
    # checkbook de Opex lo ofrecia como si tuviera donde poner un gasto.
    "0162": "Laundry Revenue es SOLO ingreso: el gasto de lavanderia vive en el "
            "0161, que lo reparte (owner, 2026-08-14)",
    # «Utilities no tiene payroll, solo cuentas especificas» y, viendo el
    # Account Mapping: «esto esta malo» (owner, 2026-08-18). Arrastraba 29
    # reglas —la planilla entera, la 4999 y once cuentas de opex ajenas— que
    # NUNCA recibieron un colon en Actual 2024, 2025 ni 2026. Lo unico con
    # movimiento son cuatro: Electricity, Gas, Oil & Gas y Water/Sewer.
    "0210": "Utilities es SOLO consumo (energia, agua, combustibles): no tiene "
            "planilla ni el opex generico (owner, 2026-08-18)",
}


INDEPENDIENTES = {
    "0210": "OH_UTILITIES",
    "0205": "OH_CLARO_HUERTA",
    "0151": "OPEX_TIENDA",       # cada tienda con su propia linea
    "0165": "OPEX_RETAIL",       # el Gift Shop se queda con RETAIL
    "0121": "OPEX_PRIVATE_BAR",
}

# El vocabulario que comparte todo departamento, tenga la actividad que tenga.
NUCLEO = ("6000", "6020", "6021", "6025", "6026", "7105", "7110", "7150",
          "7175", "7185", "7380", "7400", "7665", "7680", "7685", "4999")


@pytest.mark.parametrize("dept,linea", sorted(INDEPENDIENTES.items()))
def test_cada_departamento_independiente_se_queda_con_lo_suyo(mapeo, dept, linea):
    # Un departamento que a proposito NO tiene el nucleo no puede perderlo:
    # no lo tiene. La lista de por que esta en `SIN_NUCLEO_A_PROPOSITO`.
    if dept in SIN_NUCLEO_A_PROPOSITO:
        pytest.skip(SIN_NUCLEO_A_PROPOSITO[dept])
    resolve, _ = mapeo
    fugas = []
    for cuenta in NUCLEO:
        regla, modo = resolve(dept, cuenta)
        if regla["report_line_code"] != linea:
            fugas.append(f"{cuenta} -> {regla['report_line_code']} ({modo})")
    assert not fugas, (
        f"el {dept} pierde estas cuentas hacia otro departamento:\n  "
        + "\n  ".join(fugas))


def test_las_dos_tiendas_van_arriba_del_gop_y_no_en_overhead():
    """Son operativas y generan ingreso: su gasto va en OPERATING EXPENSES, no
    en el bloque de overhead."""
    from app.seed_department_catalog import build_rows as _filas
    catalogo = {r["dept_code"]: r for r in _filas()}
    for dept in ("0151", "0165"):
        fila = catalogo[dept]
        assert fila["pl_kind"] == "OPERATING", (dept, fila["pl_kind"])
        assert fila["is_revenue_dept"] is True, dept
        assert fila["parent_dept_code"] is None, (
            f"{dept} es un departamento individual, no cuelga de nadie")
    assert "RETAIL" in pl_engine.OPERATING_GROUP_ORDER


def test_utilities_y_claro_del_bosque_son_overhead_y_no_cuelgan_de_nadie():
    from app.seed_department_catalog import build_rows as _filas
    catalogo = {r["dept_code"]: r for r in _filas()}
    for dept in ("0205", "0210"):
        fila = catalogo[dept]
        assert fila["pl_kind"] == "OVERHEAD", (dept, fila["pl_kind"])
        assert fila["parent_dept_code"] is None, (
            f"{dept} es independiente, no puede colgar de otro departamento")
        assert not pl_engine._cadena_de_padres(dept), dept


def test_utilities_dejo_de_compartir_codigo_con_claro_del_bosque(mapeo):
    """Las 8 reglas de Utility vivían con dept_code 0205, que es Claro del
    Bosque. Dos departamentos distintos amontonados bajo el mismo código."""
    _, reglas = mapeo
    del_0205 = {m["report_line_code"] for m in reglas
                if (m.get("dept_code") or "") == "0205"}
    # `COH_CLARO_HUERTA` es la linea de COSTO del mismo departamento, no de
    # otro: se acepta la familia, no un codigo suelto.
    # Se compara la RAIZ del departamento y no el codigo completo: el 0205
    # tiene ahora tres lineas propias -- ingreso, gasto y costo -- y las tres
    # son suyas. Lo que esta prueba cuida es que no aparezca una linea de OTRO
    # departamento, que fue el bug original con Utilities.
    assert {c.split("_", 1)[1] for c in del_0205} == {"CLARO_HUERTA"}, (
        f"el 0205 todavia lleva reglas de otro departamento: {del_0205}")


def test_cada_tienda_tiene_su_ingreso_su_gasto_y_su_utilidad(mapeo):
    """Las dos compartían UNA línea llamada «Retail-Gift Shop», así que en el
    P&L se veían sumadas. El owner las quiere separadas (2026-08-13): cada una
    con su ingreso, su gasto y su utilidad departamental.

    El Gift Shop se queda con `RETAIL` porque toda la cañería de presupuesto,
    drivers e importadores ya cuelga de él; mover las dos habría tocado veinte
    archivos para el mismo resultado.
    """
    _, reglas = mapeo
    por_dept = {}
    for m in reglas:
        d = (m.get("dept_code") or "").strip()
        if d in ("0151", "0165"):
            por_dept.setdefault(d, set()).add(m["report_line_code"])

    # Cada tienda con LO SUYO. Desde 2026-08-14 hay tambien una linea de
    # costo por departamento, asi que se compara el sufijo y no el conjunto
    # exacto: lo que la prueba cuida es que la Tienda no toque al Gift Shop.
    assert {c.split("_", 1)[1] for c in por_dept["0151"]} == {"TIENDA"}, por_dept["0151"]
    assert {c.split("_", 1)[1] for c in por_dept["0165"]} == {"RETAIL"}, por_dept["0165"]

    # Y ninguna comparte línea con la otra.
    assert not (por_dept["0151"] & por_dept["0165"])


def test_las_tres_lineas_de_la_tienda_existen_en_el_reporte():
    """Sin la fila en `report_line_config`, la línea no aparece en ningún
    reporte por más que el mapeo la nombre."""
    datos = json.loads(MAPEO.read_text(encoding="utf-8"))
    codigos = {l["line_code"] for l in datos["report_line_config"]}
    for code in ("REV_TIENDA", "OPEX_TIENDA", "PROFIT_TIENDA"):
        assert code in codigos, f"falta {code} en report_line_config"


def test_el_motor_emite_las_tres_lineas_de_la_tienda():
    """El motor habla su propio vocabulario (`REV_*`/`OPEXP_*`/`OPPROFIT_*`) y
    `_MOTOR_TO_CANON` lo traduce al del reporte. Un grupo nuevo sin su entrada
    en ese puente calcula bien y no se ve en ningún lado."""
    puente = pl_engine._MOTOR_TO_CANON
    assert puente["REV_TIENDA"] == ("REV_TIENDA", "REVENUES")
    assert puente["OPEXP_TIENDA"] == ("OPEX_TIENDA", "OPERATING EXPENSES")
    assert puente["OPPROFIT_TIENDA"] == ("PROFIT_TIENDA", "OPERATING PROFIT")


def test_la_tienda_se_lee_antes_del_gift_shop():
    orden = pl_engine.OPERATING_GROUP_ORDER
    assert orden.index("TIENDA") < orden.index("RETAIL")
    assert pl_engine.GROUP_NAMES["TIENDA"] == "Tienda"
    assert pl_engine.GROUP_NAMES["RETAIL"] == "Gift Shop"
    assert pl_engine.group_for_dept("0151") == "TIENDA"
    assert pl_engine.group_for_dept("0165") == "RETAIL"


# ─────────────────────────────────────────────────────────────────────────────
# LA REGLA GENERAL, sobre TODOS los departamentos (owner, 2026-08-13).
#
# Lo de arriba nació caso por caso —Spa, Utilities, Claro del Bosque, las dos
# tiendas— hasta que se midió el sistema entero y aparecieron 21 con la misma
# fuga. Esta prueba deja de perseguirlos de a uno: ninguno puede perder una
# cuenta del núcleo hacia otro departamento.
#
# El núcleo son las cuentas que usa cualquier departamento tenga la actividad
# que tenga: planilla, cargas, cafetería, cesantía, servicios contratados,
# suscripciones, entretenimiento, misceláneos, suministros, capacitación,
# uniformes, y la 4999 del reparto.
#
# La 4999 era la más cara: el crédito de reparto de CUALQUIER departamento le
# restaba a Habitaciones. Es el mismo error de los $92,108 de la migración 089,
# que se había arreglado solo para Rooms, Cafetería y Lavandería.

# Departamentos que a propósito no llevan el núcleo, con su motivo. Sin motivo
# escrito, esta lista se convierte en el lugar donde se esconde el trabajo que
# no se hizo.


def _departamentos_activos():
    return {r["dept_code"]: r for r in build_rows() if r.get("active", True)}


def test_ningun_departamento_pierde_cuentas_del_nucleo(mapeo):
    resolve, _ = mapeo
    fugas = []
    for dept, fila in sorted(_departamentos_activos().items()):
        if dept in SIN_NUCLEO_A_PROPOSITO:
            continue
        perdidas = [c for c in NUCLEO if resolve(dept, c)[1] == "FALLBACK"]
        if perdidas:
            destino = resolve(dept, perdidas[0])[0]["report_line_code"]
            fugas.append(f"{dept} {fila['dept_name']}: {len(perdidas)} cuentas "
                         f"-> {destino} (ej. {', '.join(perdidas[:4])})")
    assert not fugas, (
        "estos departamentos pierden gasto hacia otro. No da error y el GOP "
        "cuadra igual — solo queda un departamento inflado y el otro "
        "desinflado:\n  " + "\n  ".join(fugas))


def test_el_credito_de_reparto_nunca_le_resta_a_otro_departamento(mapeo):
    """La 4999 de un departamento tiene que caer en SU propia línea, para que
    el débito y el crédito del reparto se anulen sobre la misma."""
    resolve, _ = mapeo
    fugas = []
    for dept, fila in sorted(_departamentos_activos().items()):
        if dept in SIN_NUCLEO_A_PROPOSITO:
            continue
        regla, modo = resolve(dept, "4999")
        if modo == "FALLBACK":
            fugas.append(f"{dept} {fila['dept_name']} -> {regla['report_line_code']}")
    assert not fugas, (
        "el credito de reparto de estos departamentos le resta a otro:\n  "
        + "\n  ".join(fugas))


@pytest.mark.parametrize("dept", sorted(SIN_NUCLEO_A_PROPOSITO))
def test_las_excepciones_del_nucleo_siguen_existiendo(dept):
    assert dept in _departamentos_activos(), (
        f"{dept} esta en la lista de excepciones pero ya no existe: sacalo")


def test_ventas_remoto_cuelga_de_ventas():
    """`0191` no tenía reglas ni padre, así que TODO lo suyo caía en
    Habitaciones. Colgarlo es mejor que darle reglas propias: hoy no se usa, y
    si mañana se usa hereda las de su padre sin que nadie se tenga que
    acordar (owner, 2026-08-13)."""
    assert pl_engine._cadena_de_padres("0191") == ["0190"]


def test_la_lavanderia_separa_ingreso_de_gasto(mapeo):
    """La norma del owner: `0162` es el departamento de INGRESO y `0161` lleva
    el gasto y desde ahí reparte a todos — al cierre del mes `0161` queda en
    cero. Por eso `0162` NO cuelga de `0161`: el reparto los separa a propósito
    (le manda a `0162` el costo de huésped en la 5301) y consolidarlos
    desharía esa separación."""
    resolve, _ = mapeo
    for acc in ("4700", "4701", "4702"):
        regla, modo = resolve("0162", acc)
        assert regla["report_line_code"] == "REV_LAUNDRY", (acc, regla["report_line_code"])
        assert modo == "exact", (acc, modo)
    assert not pl_engine._cadena_de_padres("0162"), (
        "0162 no puede colgar de 0161: el reparto de lavanderia los separa")
