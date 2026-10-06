# -*- coding: utf-8 -*-
"""Un mes cerrado no se edita. Ni el checkbook, ni la planilla, ni el ingreso.

Owner, 2026-08-20: *«este mensaje no me gusta, que sigue editable. Para mí debe
enllavarse el checkbook, no debe dejar que se edite.»*

## Por qué en el ORM y no en los endpoints

Medido: **109 rutas de escritura llevan `scenario_id` y sólo 9 llevan el mes en
la URL**. Las demás lo mandan en el cuerpo, y los guardados en grilla mandan
**los doce meses siempre** (`OpexBulkRow` tiene `jan..dec` con default 0). Un
candado que rechazara «el cuerpo trae un mes cerrado» bloquearía **toda**
edición, incluida la de diciembre.

Lo que hay que mirar no es si el mes VIAJA: es si su valor **cambia**. Eso el
ORM lo sabe exactamente —`attrs.<col>.history`— y lo sabe para todos los
escritores a la vez, los de hoy y los que se agreguen mañana.

⚠️ **Los nueve modelos con columnas de mes se DERIVAN del mapeo**, no se
escriben acá. Este proyecto ya pagó dos veces por una lista a mano (el Club
Madresal y siete líneas de ingreso en Master Data): una tabla nueva con meses
queda cubierta sola.

## Qué cuenta como cerrado

La regla canónica ya existe: `engine/meses_cerrados.meses_cerrados`. Acá se usa
**sólo para FORECAST** (`1..actuals_through`), a propósito:

* En un **ACTUAL**, «cerrado» es «tiene dato» — aplicarlo impediría corregir un
  histórico, que es un trabajo normal y otra conversación.
* Un **BUDGET** no cierra meses.

## Qué se bloquea

* **Cambiar** el valor de un mes cerrado.
* **Crear** una fila con monto en un mes cerrado.
* **Borrar** una fila que tiene monto en un mes cerrado.

Y lo que NO: reguardar el mismo valor. Sin eso, un guardado de grilla que
reenvía los doce meses fallaría siempre aunque sólo se hubiera tocado diciembre.

⚠️ **El recálculo no se ve afectado**: ya saltea los meses cerrados por su
cuenta (`recalculate.py`, `if cerrados and (i + 1) in cerrados: continue`).
Esto cierra el otro camino, el de la edición a mano.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy.orm import Session

from app.db import Base, SesionFinPlan
from app.errores import ErrorApi

#: Los sufijos de mes tal como los escribe el esquema: `jan`, `crc_jan`,
#: `fte_jan`.
MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]

_MAPA: dict[type, dict[str, int]] | None = None


def columnas_de_mes() -> dict[type, dict[str, int]]:
    """`{modelo: {columna: mes}}`, derivado del mapeo.

    Sólo entran los modelos que además tienen `scenario_id`: sin escenario no
    hay corte contra el cual comparar.
    """
    # ⚠️ **No se cachea un mapa VACÍO.** Si esto corriera antes de que los
    # modelos estén importados, guardar el vacío dejaría el candado apagado para
    # siempre y en silencio — que es peor que no tenerlo, porque parece puesto.
    global _MAPA
    if _MAPA:
        return _MAPA
    fuera: dict[type, dict[str, int]] = {}
    for mapper in Base.registry.mappers:
        cols = {c.key for c in mapper.columns}
        if "scenario_id" not in cols:
            continue
        por_col = {c: i + 1 for i, m in enumerate(MESES) for c in cols
                   if c == m or c.endswith(f"_{m}")}
        if por_col:
            fuera[mapper.class_] = por_col
    if fuera:
        _MAPA = fuera
    return fuera


def _cerrados(session: Session, scenario_id: str | None) -> set[int]:
    """Los meses cerrados del escenario de esta fila. Vacío si no aplica."""
    if not scenario_id:
        return set()
    from app.models.scenario import Scenario

    with session.no_autoflush:
        sc = session.get(Scenario, scenario_id)
    if sc is None or (getattr(sc, "type", "") or "").upper() != "FORECAST":
        return set()
    corte = int(getattr(sc, "actuals_through", 0) or 0)
    return set(range(1, corte + 1))


#: Medio centimo: el error MAXIMO de redondear a dos decimales. Una diferencia
#: de hasta esto NO es una edicion, es el viaje de ida y vuelta de la plantilla.
#:
#: ⚠️ El Excel de Detalle exporta `round(float(v), 2)` —dos decimales— y las
#: columnas de mes son `Numeric(..., 4)`. Un ingreso en dolares sale del GL
#: dividido por el tipo de cambio, asi que casi siempre trae cuatro decimales:
#: 176,9961 baja a la plantilla como 176,99 y vuelve DISTINTO. Comparando exacto,
#: bajar la plantilla y subirla SIN TOCAR NADA disparaba el 409.
#:
#: Owner, 2026-10-06, con la plantilla recien bajada: «VUELVE A SALIR». Y el
#: mensaje mandaba a reabrir el periodo, que es destruir un mes cerrado y bueno
#: para arreglar un redondeo de medio centimo.
TOLERANCIA = Decimal("0.005")


def es_edicion(antes: Decimal, ahora: Decimal) -> bool:
    """¿Esto es una edicion de verdad, o el redondeo del viaje de la plantilla?

    Funcion aparte y publica a proposito: la decision que separa «te frenan el
    cierre» de «paso sin avisar» tiene que poder probarse con numeros, no
    leyendo el codigo de `_revisar`.
    """
    # `>` y no `>=`: el error MAXIMO de redondear a dos decimales es
    # exactamente medio centimo (1234,565 → 1234,56). Con `>=` ese caso
    # —el peor del redondeo, y el mas probable de aparecer— se frenaba.
    return abs(antes - ahora) > TOLERANCIA


def _numero(v) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except Exception:                                   # noqa: BLE001
        return Decimal("0")


def _revisar(session: Session) -> None:
    mapa = columnas_de_mes()

    def frenar(obj, mes: int, col: str, verbo: str,
               antes: Decimal | None = None, ahora: Decimal | None = None) -> None:
        from app.models.scenario import Scenario

        with session.no_autoflush:
            sc = session.get(Scenario, getattr(obj, "scenario_id", None))
        # ⚠️ El mensaje lleva LOS NUMEROS. Sin ellos decia «enero esta cerrado» y
        # no habia forma de saber si el archivo cambiaba medio centimo o doce mil
        # dolares — se discutia a ciegas y la unica salida que el texto ofrecia
        # era reabrir el periodo. Owner, 2026-10-06: «SIGUE SALIENDO».
        detalle = f"{verbo} {type(obj).__name__}.{col}"
        if antes is not None and ahora is not None:
            detalle += (f": {antes} → {ahora}"
                        f" (diferencia {abs(ahora - antes)})")
        cuenta = getattr(obj, "account_code", None) or getattr(obj, "line", None)
        if cuenta:
            detalle += f" · {cuenta}"
            dept = getattr(obj, "dept_code", None)
            if dept:
                detalle += f" en {dept}"
        raise ErrorApi(
            409, "escenario.mes_cerrado",
            mes=MESES[mes - 1].capitalize(),
            escenario=(f"{sc.type} {sc.version} {sc.year}" if sc else "?"),
            detalle=detalle)

    for obj in list(session.dirty):
        cols = mapa.get(type(obj))
        if not cols:
            continue
        cerrados = _cerrados(session, getattr(obj, "scenario_id", None))
        if not cerrados:
            continue
        estado = sa_inspect(obj)
        for col, mes in cols.items():
            if mes not in cerrados:
                continue
            hist = estado.attrs[col].history
            # ⚠️ `has_changes()` es cierto también cuando se reasigna el MISMO
            # valor. Se comparan los números: sin esto, un guardado de grilla
            # que reenvía los doce meses fallaría siempre.
            if not hist.has_changes():
                continue
            antes = _numero(hist.deleted[0]) if hist.deleted else Decimal("0")
            ahora = _numero(hist.added[0]) if hist.added else Decimal("0")
            if es_edicion(antes, ahora):
                frenar(obj, mes, col, "cambiar", antes, ahora)
            elif antes != ahora:
                # Menos de medio centimo: es el redondeo de la plantilla, no una
                # edicion. Se DEVUELVE el valor guardado en vez de dejarlo pasar:
                # dejarlo pasar escribiria el redondeo en un mes cerrado y, carga
                # tras carga, el mes se iria moviendo solo. Un mes cerrado no se
                # toca — ni siquiera un poquito.
                setattr(obj, col, antes)

    for obj in list(session.new):
        cols = mapa.get(type(obj))
        if not cols:
            continue
        cerrados = _cerrados(session, getattr(obj, "scenario_id", None))
        for col, mes in cols.items():
            if mes in cerrados and _numero(getattr(obj, col, 0)):
                frenar(obj, mes, col, "crear con monto en")

    for obj in list(session.deleted):
        cols = mapa.get(type(obj))
        if not cols:
            continue
        cerrados = _cerrados(session, getattr(obj, "scenario_id", None))
        for col, mes in cols.items():
            if mes in cerrados and _numero(getattr(obj, col, 0)):
                frenar(obj, mes, col, "borrar con monto en")


@event.listens_for(SesionFinPlan, "before_flush")
def _antes_de_guardar(session, flush_context, instances):  # noqa: ANN001
    """La única puerta. Se engancha a la sesión DE LA APP, así que cubre a todo
    el que escriba —endpoint, script o motor— sin que nadie se acuerde de nada.

    ⚠️ **A `SesionFinPlan` y no al `Session` global.** Registrado en el global
    disparaba también en sesiones sueltas —una prueba que arma un SQLite en
    memoria con dos tablas— y ahí la consulta del escenario revienta porque
    `scenarios` no existe."""
    _revisar(session)
