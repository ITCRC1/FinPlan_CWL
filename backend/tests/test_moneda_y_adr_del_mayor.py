# -*- coding: utf-8 -*-
"""
EL ADR SALE DEL CÓDIGO DE CUENTA, Y UN ARCHIVO EN COLONES NO ENTRA CALLADO.

Dos defectos encontrados el 2026-09-05 auditando la producción de Oxygen, que
lleva su contabilidad en QuickBooks y en colones mientras la app reporta en
dólares.

**1 · El ADR se elegía por NOMBRE de cuenta.** La regla de A4 dice que de 2026 en
adelante el ADR sale sólo de la renta de habitación pura, y estaba implementada
como `account_name == "rooms"`. En el mayor de Oxygen esa cuenta se llama «Room
Revenue»: no hacía match y **el ADR quedaba en cero**. En producción, el ACTUAL
2026 tenía los siete meses con ingreso y noches cargados y ADR 0,00, mientras el
2025 —que va por la rama del departamento— estaba bien. El nombre ya había
cambiado tres veces en esa misma cuenta; el código no.

**2 · Nada detecta un archivo en la moneda equivocada.** El importador del mayor
no convierte ni tiene columna de moneda. Un archivo en colones entra 1:1, infla
todo ~500x, y no falla nada: el P&L cuadra consigo mismo y la verificación de
arriba contra abajo también, porque los dos lados salen del mismo archivo. Lo
único que delata la escala es el ADR.
"""
from decimal import Decimal

import pytest

from app.importers.gl_detail_importer import (
    ADR_USD_MAX, ADR_USD_MIN, CUENTA_ADR, aviso_de_moneda, consolidate_block,
)


def _bloque(revenue, occ=333, avail=496, year=2026, tipo="ACTUAL"):
    return {
        "year": year, "type": tipo, "label": f"{tipo} {year}",
        "revenue": revenue,
        "stats": {"rooms_available": {1: avail}, "rooms_occupied": {1: occ},
                  "guests": {1: 600}},
    }


def _adr(blk):
    return consolidate_block(blk, [], [])["stats"][1].get("adr")


# ── 1 · el ADR por código de cuenta ──────────────────────────────────────────

def test_el_adr_sale_de_la_4000_aunque_se_llame_room_revenue():
    """El caso exacto de produccion: la cuenta se llama «Room Revenue»."""
    blk = _bloque([{"account_code": "4000", "account_name": "Room Revenue",
                    "dept_code": "0110", "months": {1: 191713.05}}])
    assert _adr(blk) == pytest.approx(Decimal("575.71"), abs=Decimal("0.01"))


def test_el_no_show_no_infla_el_adr():
    """4001 y 4002 estan en el mismo departamento y consolidan en Rooms, pero un
    no-show NO ocupa habitacion: no puede entrar al numerador (A4)."""
    blk = _bloque([
        {"account_code": "4000", "account_name": "Room Revenue",
         "dept_code": "0110", "months": {1: 191713.05}},
        {"account_code": "4001", "account_name": "Cancellations",
         "dept_code": "0110", "months": {1: 9000.0}},
        {"account_code": "4002", "account_name": "No Show",
         "dept_code": "0110", "months": {1: 5000.0}},
    ])
    assert _adr(blk) == pytest.approx(Decimal("575.71"), abs=Decimal("0.01"))


def test_sin_codigo_de_cuenta_cae_al_nombre():
    """Respaldo para un archivo viejo sin numero de cuenta: peor criterio, pero
    mejor que un cero."""
    blk = _bloque([{"account_code": "", "account_name": "Rooms",
                    "dept_code": "0110", "months": {1: 191713.05}}])
    assert _adr(blk) == pytest.approx(Decimal("575.71"), abs=Decimal("0.01"))


def test_la_cuenta_del_adr_es_la_4000():
    """Si alguien la cambia, que se entere por una prueba y no por un reporte."""
    assert CUENTA_ADR == "4000"


# ── 2 · la guarda de moneda ──────────────────────────────────────────────────

def test_un_adr_normal_no_avisa_nada():
    stats = {m: {"adr": Decimal(v)} for m, v in
             enumerate(["612.00", "845.50", "1100.00", "1480.25"], start=1)}
    assert aviso_de_moneda(stats) is None


def test_un_archivo_en_colones_avisa_y_lo_dice():
    """375 x 500 = 187.500. El aviso tiene que nombrar la causa probable."""
    stats = {m: {"adr": Decimal(v)} for m, v in
             enumerate(["211735.00", "226550.00", "230115.00"], start=1)}
    av = aviso_de_moneda(stats)
    assert av is not None
    assert "COLONES" in av
    assert "3 de 3" in av


def test_sin_adr_medido_no_se_inventa_un_aviso():
    """Un bloque sin noches ocupadas no tiene ADR: no hay nada que juzgar."""
    assert aviso_de_moneda({1: {"rooms_available": 496}}) is None
    assert aviso_de_moneda({}) is None


def test_el_techo_es_ancho_porque_todavia_no_se_midio():
    """⚠️ En esta propiedad el ADR real no se pudo medir, asi que el techo esta
    alto a proposito: un 409 falso le rechazaria al owner una subida legitima.

    Lo que la guarda TIENE que seguir atrapando es el error de escala. Un archivo
    en colones infla por ~500, asi que se cae del rango por dos ordenes de
    magnitud aunque el techo sea generoso — eso es lo que se comprueba aca."""
    assert Decimal("8000") < ADR_USD_MAX, (
        "el tarifario de referencia llega a 8.000: un techo por debajo "
        "rechazaria una subida buena")
    en_colones = {m: {"adr": Decimal("400") * 500} for m in (1, 2, 3)}
    assert aviso_de_moneda(en_colones) is not None
