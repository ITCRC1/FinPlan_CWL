# -*- coding: utf-8 -*-
"""La clase de la cuenta manda: dónde puede caer cada una en el P&L.

**La regla, en palabras del owner (2026-08-14):**

    «Las cuentas 4 son revenue a excepción de los allocations.
     5 costo, 6 planilla, 7 opex y 8 gastos de propiedad.»

Es la regla que define todo el mapeo. Contra ella, de las 1,172 reglas del
sistema había exactamente **cuatro** que no la cumplían: las 4500–4503 del
departamento 0205, llamadas «Ingreso Claro Huerta 1..4», mapeadas a
`OH_CLARO_HUERTA` —una línea de GASTO— con naturaleza «Expense».

**Por qué nadie lo había visto.** Un ingreso que resta gasto tiene el mismo
efecto sobre el GOP que un ingreso que suma: el resultado salía bien. Lo que
quedaba torcido era el ingreso del hotel, el overhead, y todos los porcentajes
sobre venta. El número que se mira estaba bien y la estructura no.

Estas pruebas convierten la regla en algo que el sistema vigila solo.
"""
import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SEED = RAIZ / "app" / "seed_data" / "mapping_pl.json"

# Las de reparto son clase 4 y NO son ingreso: son el crédito con el que un
# departamento de servicio interno se vacía contra los que lo consumen. Es la
# única excepción que el owner nombró, y está también en
# `pl_engine.ALLOCATION_ACCOUNTS`.
REPARTO = {"4900", "4901", "4999"}


def _reglas():
    return json.loads(SEED.read_text(encoding="utf-8"))["account_mapping"]


def _violaciones(prueba):
    return sorted({(r.get("dept_code") or "", str(r["account_code"]),
                    r["report_line_code"])
                   for r in _reglas() if prueba(str(r["account_code"]),
                                                r["report_line_code"])})


def test_toda_cuenta_clase_4_va_a_ingreso_salvo_los_repartos():
    """El caso de Claro del Bosque, hecho regla."""
    malas = _violaciones(
        lambda c, l: c[:1] == "4" and c not in REPARTO and not l.startswith("REV_"))
    assert not malas, (
        f"cuentas de INGRESO mandadas a una línea de gasto: {malas}. "
        "El GOP va a salir bien igual —un ingreso que resta gasto da lo mismo— "
        "pero el ingreso del hotel y todos los % sobre venta quedan mal."
    )


def test_ningun_reparto_se_cuenta_como_ingreso():
    """El otro lado: si el crédito del reparto entrara al ingreso, la venta del
    año subiría por algo que no se le vendió a nadie."""
    malas = _violaciones(lambda c, l: c in REPARTO and l.startswith("REV_"))
    assert not malas, f"cuentas de reparto contadas como ingreso: {malas}"


def test_toda_cuenta_clase_5_va_a_una_linea_de_costo():
    malas = _violaciones(
        lambda c, l: c[:1] == "5" and not l.startswith(("COS_", "COH_")))
    assert not malas, f"costo de ventas fuera de una línea de costo: {malas}"


def test_la_planilla_y_el_opex_van_a_la_linea_de_su_departamento():
    """Clases 6 y 7 comparten línea a propósito: el P&L está cortado por
    DEPARTAMENTO, no por naturaleza. El corte por naturaleza que pidió el owner
    vive en el pie del cierre de mes (`gasto_por_clase_api`), que es otro eje."""
    malas = _violaciones(
        lambda c, l: c[:1] in "67" and not l.startswith(("OPEX_", "OH_")))
    assert not malas, f"planilla u opex fuera de la línea de su depto: {malas}"


def test_el_gasto_de_propiedad_no_se_mete_en_lo_operativo():
    malas = _violaciones(
        lambda c, l: c[:1] == "8"
        and l.startswith(("REV_", "OPEX_", "OH_", "COS_", "COH_")))
    assert not malas, (
        f"gasto de propiedad dentro de una línea operativa: {malas}. "
        "Bajaría el GOP por algo que va debajo del GOP."
    )


def test_claro_del_bosque_quedo_como_ingreso():
    """El caso concreto, para que el arreglo no se deshaga sin que nadie note."""
    por_cuenta = {str(r["account_code"]): r for r in _reglas()
                  if (r.get("dept_code") or "") == "0205"
                  and str(r["account_code"]).startswith("45")}
    assert set(por_cuenta) == {"4500", "4501", "4502", "4503"}
    for cta, r in por_cuenta.items():
        assert r["report_line_code"] == "REV_CLARO_HUERTA", cta
        assert r["financial_nature"] == "Revenue", cta


def test_la_utilidad_de_claro_del_bosque_no_resta_su_gasto_dos_veces():
    """⚠️ El 0205 es un departamento de OVERHEAD: su gasto ya se resta en
    `TOTAL_OVERHEAD_EXPENSES`, y el GOP es `OPERATING_PROFIT − overhead`. Si
    `PROFIT_CLARO_HUERTA` también restara `OH_CLARO_HUERTA`, ese gasto se
    contaría dos veces y el GOP bajaría por su monto completo.

    Mismo patrón que `PROFIT_SUSTAINABILITY` y `PROFIT_AREC`.
    """
    cfg = {r["line_code"]: r for r in
           json.loads(SEED.read_text(encoding="utf-8"))["report_line_config"]}
    f = cfg["PROFIT_CLARO_HUERTA"]["calculation_logic"].strip()
    assert f == "REV_CLARO_HUERTA", (
        f"quedó como «{f}»: si resta el gasto del 0205, se cuenta dos veces")


def test_la_naturaleza_declarada_coincide_con_la_clase():
    """La columna «Naturaleza» del mapeo es redundante —se deduce de la clase—
    pero existe y se muestra. Si dice una cosa y la clase otra, alguien va a
    revisar el mapeo por la columna equivocada."""
    malas = []
    for r in _reglas():
        cta, nat = str(r["account_code"]), r.get("financial_nature")
        esperada = "Revenue" if (cta[:1] == "4" and cta not in REPARTO) else "Expense"
        if nat != esperada:
            malas.append((r.get("dept_code"), cta, nat, esperada))
    assert not malas, f"naturaleza que no coincide con la clase: {malas[:10]}"


# ─────────────────────────────────────────────────────────────────────────────
# Las reglas que vivían solo en la base
# ─────────────────────────────────────────────────────────────────────────────

def test_villas_y_residencias_estan_en_el_seed():
    """⚠️ 96 reglas de los deptos 0115 (Villas) y 0116 (Residencias) existían
    SOLO en la base: alguien las creó a mano o por migración y nunca volvieron
    al repositorio (owner, 2026-08-14 — lo delató que `REV_ROOMS` salía con dos
    nombres distintos en el mapeo exportado).

    El seed es lo que arma una instalación nueva. Sin estas reglas, una
    propiedad nueva nace con el ingreso y el gasto de Villas cayendo en la nada
    —o peor, en la línea de otro departamento por fallback—. Corcovado no lo
    nota porque su base ya las tiene: el hueco solo se ve el día que se abre
    otro hotel, que es tarde.
    """
    por_dep = {}
    for r in _reglas():
        d = str(r.get("dept_code") or "")
        if d in ("0115", "0116"):
            por_dep[d] = por_dep.get(d, 0) + 1
    assert por_dep.get("0115", 0) >= 48, (
        f"Villas quedó con {por_dep.get('0115', 0)} reglas en el seed")
    assert por_dep.get("0116", 0) >= 48, (
        f"Residencias quedó con {por_dep.get('0116', 0)} reglas en el seed")


def test_villas_y_residencias_rutean_a_rooms():
    """Son sets hijos de Habitaciones: su ingreso y su gasto son de Rooms."""
    for r in _reglas():
        if str(r.get("dept_code") or "") not in ("0115", "0116"):
            continue
        cta, ln = str(r["account_code"]), r["report_line_code"]
        if cta[:1] == "4" and cta not in REPARTO:
            assert ln.startswith("REV_ROOMS"), (r["dept_code"], cta, ln)
        elif cta[:1] in "4567":
            assert ln == "OPEX_ROOMS", (r["dept_code"], cta, ln)


# ─────────────────────────────────────────────────────────────────────────────
# El nombre de la línea
# ─────────────────────────────────────────────────────────────────────────────

def _config():
    return {r["line_code"]: r for r in
            json.loads(SEED.read_text(encoding="utf-8"))["report_line_config"]}


def test_ninguna_linea_tiene_dos_nombres():
    """⚠️ `REV_ROOMS` salía como «Rooms Pure» en el depto 0110 y como «Rooms» en
    Villas y Residencias (owner, 2026-08-14 — lo vio en la pantalla).

    Cada regla del mapeo lleva una COPIA del nombre de su línea, así que se
    desincroniza sola: quien renombra la línea toca `report_line_config` y las
    1,172 copias se quedan con el nombre viejo. Eran once las desalineadas, no
    solo las dos de Rooms.

    Importa más de lo que parece: el mapeo se revisa POR NOMBRE. Dos nombres
    para la misma línea hacen creer que son dos líneas distintas, y —al revés—
    el mismo nombre en dos códigos distintos hace creer que son la misma.
    """
    por_codigo = {}
    for r in _reglas():
        por_codigo.setdefault(r["report_line_code"], set()).add(r.get("report_line_name"))
    malos = {k: sorted(v) for k, v in por_codigo.items() if len(v) > 1}
    assert not malos, f"líneas con más de un nombre en el mapeo: {malos}"


def test_el_nombre_del_mapeo_es_el_que_declara_el_reporte():
    """El nombre vive en `report_line_config` —eso es lo que se muestra— y el
    del mapeo es la copia. Si discrepan, manda el reporte."""
    cfg = _config()
    malos = []
    for r in _reglas():
        code = r["report_line_code"]
        if code in cfg and r.get("report_line_name") != cfg[code]["line_name"]:
            malos.append((code, r.get("report_line_name"), cfg[code]["line_name"]))
    assert not malos, (
        f"el mapeo dice un nombre y el reporte otro: {sorted(set(malos))[:8]}")
