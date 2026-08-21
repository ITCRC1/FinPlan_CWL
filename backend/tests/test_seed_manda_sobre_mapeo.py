# -*- coding: utf-8 -*-
"""El JSON del seed es la fuente de verdad de `account_mapping` y
`report_line_config`. Una decisión que viva solo en una migración se revierte.

**Cómo se descubrió.** Las migraciones 093/094/095 escribieron esas dos tablas,
corrieron bien, se midió el efecto contra producción y quedó verificado. El
siguiente deploy las revirtió enteras y nadie se enteró: `backend/Procfile`
arranca con `alembic upgrade head && python -m app.seed && uvicorn`, y
`app/seed_mapping.py` re-afirma **campo por campo** cada fila desde
`app/seed_data/mapping_pl.json`. El seed imprime «N actualizados» y sigue.

Es el modo de falla más caro que tiene el sistema: **el total sigue cuadrando**,
así que no hay error, no hay alerta, y la plata cambia de línea sola. Se ve solo
mirando el P&L por departamento.

Esta prueba clava en el JSON las decisiones que ya se tomaron. Si alguien las
cambia, tiene que cambiarlas acá también — que es exactamente el punto.
"""
import json
import pathlib

import pytest

SEED = (pathlib.Path(__file__).resolve().parents[1]
        / "app" / "seed_data" / "mapping_pl.json")


@pytest.fixture(scope="module")
def datos():
    if not SEED.exists():
        pytest.skip(f"no está {SEED}")
    return json.loads(SEED.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def lineas(datos):
    return {r["line_code"]: r for r in datos["report_line_config"]}


@pytest.fixture(scope="module")
def reglas(datos):
    return datos["account_mapping"]


# ── Área Recreativa es overhead (decisión D4, migración 094) ─────────────────

def test_area_recreativa_es_una_linea_de_overhead(lineas):
    assert "OH_AREC" in lineas, "el seed volvería a poner el costo en el bloque operativo"
    assert lineas["OH_AREC"]["section"] == "OVERHEAD EXPENSES"


def test_ya_no_existe_la_linea_vieja(lineas):
    """Si `OPEX_AREC` vuelve al JSON, el seed la re-inserta y quedan LAS DOS:
    `TOTAL_OPERATING_EXPENSES = SUM(OPEX_*)` se lleva el costo de vuelta al
    bloque operativo y `OH_AREC` cuelga vacía del overhead. Ya pasó."""
    assert "OPEX_AREC" not in lineas


def test_las_reglas_del_270_apuntan_al_overhead(reglas):
    del_270 = [r for r in reglas if r.get("report_line_code") in ("OPEX_AREC", "OH_AREC")]
    assert del_270, "desapareció el mapeo del departamento 270"
    assert all(r["report_line_code"] == "OH_AREC" for r in del_270)


def test_la_utilidad_de_area_recreativa_no_resta_un_costo_que_se_fue(lineas):
    """Su costo ya está en el overhead. Restarlo otra vez acá lo contaría dos
    veces — es el bug de la fila 942 del Excel, con otro disfraz."""
    assert lineas["PROFIT_AREC"]["calculation_logic"] == "REV_AREC"


# ── La cuenta 8020 y las líneas sin regla (migración 093) ────────────────────

def test_la_8020_tiene_escrito_que_lleva_las_dos_lineas(reglas):
    filas = [r for r in reglas if r.get("account_code") == "8020"]
    assert filas, "desapareció la regla de la 8020"
    assert all(r.get("notes") for r in filas), (
        "sin la nota, el próximo que la mire vuelve a encontrar tres verdades")


@pytest.mark.parametrize("linea", ["LARGE_CAPEX", "ASSET_LOSS"])
def test_las_lineas_sin_cuenta_dicen_por_que(lineas, linea):
    """No es un mapeo olvidado: comparten cuenta con su hermana (8020 / 8040) y
    el GL no las separa. Sin eso escrito, alguien les inventa una regla."""
    logica = lineas[linea]["calculation_logic"] or ""
    assert "propósito" in logica or "Sin regla de cuenta" in logica


def test_ninguna_cuenta_esta_mapeada_a_large_capex(reglas):
    activas = [r for r in reglas if r.get("active_status", "YES") == "YES"]
    assert not [r for r in activas if r.get("report_line_code") == "LARGE_CAPEX"]


# ── Honorarios: una regla por (departamento, cuenta) (migración 095) ─────────

def test_la_8005_no_tiene_dos_reglas_activas_para_el_mismo_departamento(reglas):
    """El resolvedor se queda con UNA por par. Con dos activas ganaba la fila
    que estuviera físicamente primero, y ese orden cambia con cada recarga.

    Se mide por par **y por momento**: dos reglas que nunca rigen el mismo mes
    no son ambiguas. Es lo que permite que D9 mueva la cuenta 7120 de línea sin
    reescribir los períodos ya enviados a SCP.
    """
    def se_pisan(a, b) -> bool:
        a_ini, a_fin = a.get("vigente_desde") or "0000-00", a.get("vigente_hasta") or "9999-99"
        b_ini, b_fin = b.get("vigente_desde") or "0000-00", b.get("vigente_hasta") or "9999-99"
        return a_ini <= b_fin and b_ini <= a_fin

    por_par: dict[tuple, list] = {}
    for r in reglas:
        if r.get("active_status", "YES") != "YES":
            continue
        clave = (r.get("dept_code") or r.get("source_department") or "", r.get("account_code"))
        por_par.setdefault(clave, []).append(r)

    ambiguos = {}
    for k, v in por_par.items():
        chocan = sorted({x["report_line_code"] for i, a in enumerate(v)
                         for b in v[i + 1:] if se_pisan(a, b)
                         for x in (a, b)})
        if chocan:
            ambiguos[k] = chocan
    assert not ambiguos, f"pares con más de una línea vigente a la vez: {ambiguos}"


# ── La regla general ─────────────────────────────────────────────────────────

def test_el_motor_y_el_seed_dicen_lo_mismo_de_las_cuentas_8xxx(reglas):
    """`pl_engine.NONOP_ACCOUNT_LINE` es el espejo de estas reglas. Si se
    separan, el motor viejo manda la plata a otra línea sin avisar."""
    from app.engine.pl_engine import NONOP_ACCOUNT_LINE

    del_seed: dict[str, set] = {}
    for r in reglas:
        acct = (r.get("account_code") or "").strip()
        if not acct.startswith("8") or r.get("active_status", "YES") != "YES":
            continue
        if r.get("report_line_code"):
            del_seed.setdefault(acct, set()).add(r["report_line_code"])

    assert del_seed, "el seed no trae ninguna cuenta 8xxx"
    for acct, lineas_ in sorted(del_seed.items()):
        motor = NONOP_ACCOUNT_LINE.get(acct)
        assert motor is not None, f"la {acct} está en el seed y no en el motor"
        assert motor in lineas_, f"la {acct}: motor dice {motor}, seed dice {sorted(lineas_)}"


# ── Administración: una sola familia (migración 112) ─────────────────────────
#
# Owner (2026-08-14): «0180 es el departamento madre, 0181 y 0184 son hijos;
# 0181 y 0184 solo tienen planilla, no tienen cuentas de gastos porque sus
# gastos se postean en la 0180».
#
# El seed re-afirma `account_mapping` fila por fila en cada arranque, así que
# esta decisión solo sobrevive si vive en el JSON. Estas pruebas la clavan ahí.

CUENTAS_DEL_COMEDOR = {
    # El juego de un comedor de empleados; las 15 existen también en la
    # Cafetería 0220 y NINGUNA existe en la madre 0180. Sacarlas del 0181 no
    # las manda a Administración: caen en Habitaciones y en A&B por descarte.
    # Se quedan hasta que el owner diga si se van a la 0220 o si se le abren
    # al 0180. Hoy dan 0,00 en los 12 escenarios.
    "7060", "7065", "7140", "7195", "7235", "7275", "7295", "7300", "7310",
    "7350", "7460", "7490", "7695", "5700", "5701",
}


def _por_dept(reglas, dept):
    return [r for r in reglas if (r.get("dept_code") or "").strip() == dept]


@pytest.mark.parametrize("hijo", ["0181", "0184"])
def test_los_hijos_de_administracion_solo_llevan_planilla(reglas, hijo):
    """Salvo las 15 del comedor, que están declaradas arriba con su motivo."""
    gasto = [r["account_code"] for r in _por_dept(reglas, hijo)
             if r["account_code"][:1] in ("5", "7")
             and r["account_code"] not in CUENTAS_DEL_COMEDOR]
    assert not gasto, (
        f"el {hijo} volvió a tener cuentas de gasto propias: {sorted(gasto)}. "
        "Sus gastos se postean en la 0180.")


@pytest.mark.parametrize("hijo", ["0181", "0184"])
def test_los_hijos_conservan_las_17_cuentas_de_planilla(reglas, hijo):
    """Es lo único que tienen. Si se van, la planilla del hijo cae por descarte
    en Habitaciones — que es de dónde salió la migración 092."""
    planilla = {r["account_code"] for r in _por_dept(reglas, hijo)
                if r["account_code"].startswith("6")}
    assert len(planilla) == 17, f"el {hijo} tiene {len(planilla)} cuentas de planilla"


def test_la_gerencia_0181_suma_en_administracion(reglas):
    """Estaba en `OH_EMPLOYEE_BENEFITS`, una línea aparte que daba 0,00 en los
    12 escenarios. Es hijo de Administración, no una línea propia."""
    lineas = {r["account_code"]: r["report_line_code"] for r in _por_dept(reglas, "0181")}
    fuera = {a: l for a, l in lineas.items()
             if l != "OH_ADMIN" and a not in CUENTAS_DEL_COMEDOR}
    assert not fuera, f"el 0181 volvió a sumar fuera de Administración: {fuera}"
    assert lineas.get("4901") == "OH_ADMIN", (
        "el 4901 es el crédito de reparto del 0181: tiene que netear sobre la "
        "MISMA línea que sus débitos, o le resta a otro departamento")


def test_las_cuentas_que_se_sacaron_las_tiene_la_madre(reglas):
    """La única razón por la que sacarlas no mueve nada: el hijo las hereda del
    0180 por la cadena de padres y aterriza en la misma línea. Si mañana alguien
    le saca una de estas a la madre, el hijo la pierde a Habitaciones."""
    from app.engine import pl_engine
    from app.seed_department_catalog import build_rows

    pl_engine.set_dept_catalog(build_rows())
    resolve = pl_engine.construir_resolvedor(reglas)
    de_la_madre = {r["account_code"] for r in _por_dept(reglas, "0180")}
    assert len(de_la_madre) >= 53, f"la 0180 quedó con {len(de_la_madre)} cuentas"
    for hijo in ("0181", "0184"):
        for cuenta in sorted(de_la_madre):
            regla, modo = resolve(hijo, cuenta)
            assert regla and regla["report_line_code"] == "OH_ADMIN", (
                f"{hijo}/{cuenta} → {regla and regla['report_line_code']} ({modo})")
            assert modo in ("exact", "parent"), f"{hijo}/{cuenta} llega por {modo}"


def test_el_nombre_del_0181_dice_lo_mismo_en_los_dos_lados(reglas):
    """`DEPT_NAMES` decía «Management» y el mapeo «Departamento de Beneficios
    Empleados»: dos verdades para el mismo código. Manda la planilla, que es la
    que tiene gente — GERENTE GENERAL y Gerencia Operaciones."""
    from app.seed_department_catalog import DEPT_NAMES

    assert DEPT_NAMES["0181"] == "Gerencia (Management)"
    nombres = {r["source_department"] for r in _por_dept(reglas, "0181")
               if r["account_code"] not in CUENTAS_DEL_COMEDOR}
    assert nombres == {"Gerencia (Management)"}, nombres
