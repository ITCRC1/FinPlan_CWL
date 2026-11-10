# -*- coding: utf-8 -*-
"""CAFETERÍA Y LAVANDERÍA CIERRAN EN $0 AUNQUE OTRO REPARTO LES CARGUE ALGO.

**Lo que pasaba (Budget Working 2027, 2026-11-10).** El motor repartía en este
orden: cafetería → lavandería → salarios. Dos cosas entraban DESPUÉS de que su
departamento ya se había repartido, y se quedaban pegadas:

* el salario de ROOM ATTENDANT que una regla reasigna al 0220 → $1.261,54 al mes
  ($15.138 al año) quedaban en la cafetería;
* la parte de cafetería que le toca a la lavandería (6025 al 0161) → ~$300 al mes
  quedaban en la lavandería.

El total del hotel no cambiaba —por eso no saltaba ningún cuadre—, pero esa plata
se quedaba en overhead en vez de llegar a Rooms, A&B, Spa y Tours.

**El arreglo:** salarios primero; y el pote de cada depto de reparto incluye lo
que OTROS repartos ya le cargaron ese mes (`_recibido`). Si aun así algo queda,
el recálculo lo avisa.

La prueba contra la base real (con rollback) dio 0220 y 0161 en $0,00 los doce
meses, GOP y Net Profit sin cambio, y $14.443 que pasan de overhead a los deptos
operativos.
"""
import inspect
from decimal import Decimal

from app.api import allocation_api
from app.engine import recalculate as recalc
from app.engine.allocation_calculator import (
    calculate_cafeteria_distribution, calculate_laundry_distribution,
    calculate_salary_distribution, verify_allocation_nets_zero,
)

D = Decimal


def _src():
    return inspect.getsource(recalc._recalc_allocations)


# ── El orden ────────────────────────────────────────────────────────────────

def test_los_salarios_se_reasignan_antes_que_la_cafeteria():
    src = _src()
    sal = src.index('allocation_type="SALARY"')
    caf = src.index('allocation_type="CAFETERIA"')
    lau = src.index('allocation_type="LAUNDRY"')
    rooms = src.index('allocation_type="ROOMS"')
    assert sal < caf < lau < rooms, (
        "el orden tiene que ser salarios → cafetería → lavandería → Rooms: un "
        "reparto que cae en un depto ya repartido se queda ahí")


def test_el_pote_incluye_lo_recibido_de_otros_repartos():
    src = _src()
    assert 'caf_propio + _recibido("0220")' in src
    assert 'lau_propio + _recibido("0161")' in src


def test_lo_recibido_no_cuenta_el_credito_propio():
    """`source_dept != dept`: el crédito 4999 del propio reparto no es «recibido»;
    contarlo vaciaría el pote."""
    src = _src()
    i = src.index("def _recibido")
    cuerpo = src[i:i + 900]
    assert "e.target_dept == dept and e.source_dept != dept" in cuerpo
    assert "new_entries[desde:]" in cuerpo, "solo lo de ESTE mes"


def test_avisa_si_un_depto_de_reparto_no_cierra():
    src = _src()
    assert "no cerró en $0 después de repartir" in src


def test_los_avisos_de_rooms_no_pisan_la_lista_del_recalculo():
    """Con `filas, fte_set, avisos = ...` la lista del recálculo se reemplazaba y
    los avisos se perdían."""
    src = _src()
    assert "filas, fte_set, avisos =" not in src
    assert "avisos_mes = calculate_rooms_by_pct" in src


# ── El efecto, con las funciones puras del motor ────────────────────────────

def test_salario_a_la_cafeteria_cierra_en_cero_si_entra_al_pote():
    costo_propio = D("18688.80")
    sal = calculate_salary_distribution(D("1261.54"), D("1"), {"0220": D("5")}, "0113")
    recibido = sum(r["amount_usd"] for r in sal if r["target_dept"] == "0220")
    caf = calculate_cafeteria_distribution(costo_propio + recibido,
                                           {"0113": D("15"), "0122": D("14"), "0161": D("2")})
    credito = sum(r["amount_usd"] for r in caf if r["target_dept"] == "0220")
    assert costo_propio + recibido + credito == 0
    assert verify_allocation_nets_zero(sal + caf)


def test_sin_lo_recibido_quedaba_el_salario_pegado():
    """El defecto, reproducido: sin sumar lo recibido queda exactamente el salario."""
    costo_propio = D("18688.80")
    sal = calculate_salary_distribution(D("1261.54"), D("1"), {"0220": D("5")}, "0113")
    recibido = sum(r["amount_usd"] for r in sal if r["target_dept"] == "0220")
    caf = calculate_cafeteria_distribution(costo_propio, {"0113": D("15")})
    credito = sum(r["amount_usd"] for r in caf if r["target_dept"] == "0220")
    assert costo_propio + recibido + credito == D("1261.54")


def test_la_cafeteria_que_le_toca_a_lavanderia_se_reparte_con_ella():
    caf = calculate_cafeteria_distribution(D("1100"), {"0161": D("2"), "0113": D("20")})
    a_lav = sum(r["amount_usd"] for r in caf if r["target_dept"] == "0161")
    assert a_lav == D("100")
    propio = D("4835.31")
    lav = calculate_laundry_distribution(
        propio + a_lav, {"0110": D("2000")}, {"0113": D("15")}, D("800"), D("200"))
    credito = sum(r["amount_usd"] for r in lav["rows"] if r["target_dept"] == "0161")
    assert abs(propio + a_lav + credito) < D("0.01")


# ── La pantalla muestra el mismo pote ───────────────────────────────────────

def test_la_pantalla_del_pote_muestra_lo_recibido():
    src = inspect.getsource(allocation_api.costo_a_repartir)
    assert '"clase": "R"' in src
    assert "AllocationEntry.source_dept != dept" in src, (
        "mismo criterio que `_recibido`: si no, la pantalla y el motor dirían "
        "potes distintos")
