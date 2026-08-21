# -*- coding: utf-8 -*-
"""El candado de las versiones, en un solo lugar.

Enllavar un escenario (status='locked') significa que sus números ya no cambian:
un Budget Final aprobado, un Draft cerrado. Antes el candado vivía solo en el
modelo y casi ningún endpoint lo consultaba, así que una carga masiva o un
cambio de fila lo pisaba igual.

Uso:
    await candado(db, scenario_id)          # sesión inyectada (Depends(get_db))
    await candado(session, scenario_id)     # sesión abierta a mano

Lanza ScenarioLockedError, que `main.py` convierte en un 409 con el motivo.
"""

from app.errores import ErrorApi
from app.models.scenario import Scenario


async def candado(session, scenario_id: str) -> Scenario:
    """Devuelve el escenario si se puede editar; si no, corta."""
    s = await session.get(Scenario, scenario_id)
    if not s:
        raise ErrorApi(404, "escenario.no_encontrado")
    s.assert_editable()
    return s
