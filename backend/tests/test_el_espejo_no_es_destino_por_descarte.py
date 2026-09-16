# -*- coding: utf-8 -*-
"""«Pasar a Final» escribe en el ACTUAL de verdad, no en el espejo.

## Lo que pasaba

El espejo del Pre-Cierre es un escenario `type="ACTUAL"`, `year=2026`,
`es_precierre=True`. `_match_block_target` filtraba por tipo y año y NADA MAS,
y desempataba por `created_at` descendente.

El espejo se creo el 2026-09-10 — mas nuevo que el Actual de verdad. Ganaba
siempre.

Consecuencia: `pasar_a_final` llama a `import_gl_detail` con
`scenario_id=None`, asi que el destino salia de ese desempate... y el mes se
escribia EN EL ESPEJO, que es el mismo lugar que ya mira la pantalla de
revision. El Actual nunca lo recibia.

Owner, 2026-09-15: «el pase a final no funciona.. solo voy y busco la
informacion y no veo nada». No veia nada porque no habia nada.

## La regla

Al espejo se le escribe NOMBRANDOLO (`scenario_id`), que es lo que hace
`_reflejar`. Nunca por descarte.
"""
from datetime import datetime

from app.api.scenarios_api import _match_block_target


class _Esc:
    def __init__(self, id, typ, year, pre, creado):
        self.id, self.type, self.year = id, typ, year
        self.es_precierre, self.created_at = pre, creado
        self.is_current_forecast = False


REAL = _Esc("real", "ACTUAL", 2026, False, datetime(2026, 1, 5))
ESPEJO = _Esc("espejo", "ACTUAL", 2026, True, datetime(2026, 9, 10))


def test_gana_el_actual_de_verdad_aunque_el_espejo_sea_mas_nuevo():
    assert _match_block_target([REAL, ESPEJO], "ACTUAL", 2026).id == "real"
    # Y en el otro orden, por si alguien reordena la consulta.
    assert _match_block_target([ESPEJO, REAL], "ACTUAL", 2026).id == "real"


def test_sin_actual_de_verdad_no_hay_destino():
    """Mejor sin destino —el bloque se salta y se avisa— que escribir en el
    espejo creyendo que se cerro el mes."""
    assert _match_block_target([ESPEJO], "ACTUAL", 2026) is None


def test_el_espejo_sigue_siendo_alcanzable_nombrandolo():
    """`_reflejar` le pasa `scenario_id=esp.id`, y ese camino no pasa por el
    desempate: si se rompiera, la pantalla de Pre-Closing se quedaria sin datos."""
    import inspect
    from app.api import precierre_api
    src = inspect.getsource(precierre_api._reflejar)
    assert "scenario_id=esp.id" in src


def test_pasar_a_final_NO_nombra_escenario():
    """Por eso dependia del desempate, y por eso el filtro tiene que estar en
    `_match_block_target` y no en el que llama."""
    import inspect
    from app.api import precierre_api
    src = inspect.getsource(precierre_api.pasar_a_final)
    assert "scenario_id=None" in src
