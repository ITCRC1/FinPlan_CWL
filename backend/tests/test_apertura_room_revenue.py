# -*- coding: utf-8 -*-
"""
LA 4000 SE ABRE EN TRES CUENTAS Y LAS TRES CONSOLIDAN EN ROOMS.

Decisión del owner (2026-08-12). El GL traía todo el room revenue en la cuenta
`4000`, con un nombre distinto por archivo —«Cancellations» en 2024, «No Show»
en 2025/2026, «Rooms» en el Budget 2026 Final—, así que no había forma de saber
cuánto era cada cosa. Ahora son tres:

    4000  Room Revenue
    4001  Cancellations
    4002  No Show

**En el P&L consolidan las tres en Rooms** (`REV_ROOMS`): la apertura es por
CUENTA, no una línea nueva del estado de resultados. El signo lo trae el GL — si
una cancelación se contabiliza en negativo, el `SUM` la resta.

Esto es PREPARACIÓN: hasta que la contabilidad empiece a contabilizar en 4001 y
4002, las dos cuentas van en cero y nada cambia.

⚠️ **Ojo con el ADR:** el owner pidió que salga SOLO de la 4000. Hoy
`pl_api._pl_period` lo calcula como `REV_ROOMS / rooms_occupied`, o sea sobre la
línea consolidada — ver `docs/PENDIENTES.md` A4. Mientras las cuentas nuevas
estén vacías el ADR es correcto; el día que tengan dato, deja de serlo.
"""
import json
import pathlib

from app.engine import pl_engine

MAPEO = (pathlib.Path(pl_engine.__file__).parents[1]
         / "seed_data" / "mapping_pl.json")

APERTURA = {"4000": "Room Revenue", "4001": "Cancellations", "4002": "No Show"}


def _reglas() -> list[dict]:
    return json.loads(MAPEO.read_text(encoding="utf-8"))["account_mapping"]


def test_las_tres_cuentas_existen_en_el_master():
    reglas = {m["account_code"]: m for m in _reglas()
              if (m.get("dept_code") or "") == "0110"
              and m["account_code"] in APERTURA}
    assert set(reglas) == set(APERTURA), (
        f"faltan cuentas de la apertura de Rooms: {set(APERTURA) - set(reglas)}")
    for codigo, nombre in APERTURA.items():
        assert reglas[codigo]["account_name_example"] == nombre
        assert reglas[codigo]["active_status"] == "YES"


def test_las_tres_consolidan_en_rooms():
    """Una sola línea en el P&L. Si alguien les da línea propia, esto falla."""
    resolve = pl_engine.construir_resolvedor(_reglas())
    for codigo in APERTURA:
        regla, como = resolve("0110", codigo)
        assert como == "exact", (codigo, como)
        # 4001 y 4002 (Cancellations y No Show) pasaron a `REV_ROOMS_OTHER`
        # cuando el owner pidio separar «Other Rooms Revenue» (2026-08-14).
        # Siguen siendo Rooms: lo que importa es que no se vayan a otro
        # departamento.
        assert regla["report_line_code"].startswith("REV_ROOMS"), (
            codigo, regla["report_line_code"])


def test_caen_en_el_grupo_rooms_por_rango_tambien():
    """Aunque llegue una fila sin departamento, el rango 4000-4099 las salva."""
    for codigo in APERTURA:
        assert pl_engine.revenue_line_for_account(codigo) == "rooms"


def test_ninguna_otra_cuenta_les_pisa_el_codigo():
    """4001/4002 no las puede usar otro departamento sin decidirlo.

    En este sistema el par (departamento, cuenta) es lo que identifica la línea,
    y ya hubo un caso —4500/4501/4502 compartidas por Club, Innoceana y Claro
    Huerta— donde leer solo el número llevaba a la línea equivocada.
    """
    otros = [m for m in _reglas()
             if m["account_code"] in ("4001", "4002")
             and (m.get("dept_code") or "") != "0110"]
    assert not otros, f"otro departamento usa 4001/4002: {otros}"
