# -*- coding: utf-8 -*-
"""La grilla de estadísticas: qué filas hay que llenar en cada escenario.

**El problema (owner, 2026-08-14).** Para cargar un actual, la combinación viene
con el dato: el archivo dice «9980, departamento 0122, posición 0122-01, 160
horas». Para **presupuestar** no: hay que poder escribir en cada casilla, así que
las filas tienen que existir ANTES de que alguien las llene.

**La combinación se GENERA, no se guarda.** Y sale del propio escenario:

* `DEPT` + `POSITION` → las posiciones de SU planilla (208 pares hoy)
* `DEPT`             → los departamentos habilitados de la propiedad
* `ROOMTYPE`         → sus tipos de habitación
* `OUTLET`           → sus puntos de venta de A&B

Guardarlas como cuentas del catálogo —una por combinación— daría **más de dos
mil cuentas** en vez de cuarenta, y con el producto completo (38 departamentos ×
195 posiciones) pasaría de cincuenta mil. Ese es el motivo por el que el catálogo
contable que le mandaron al owner traía 9,292 cuentas clase 9.

Pero el volumen no es lo que más pesa. Lo que decide es esto: **con las
permutaciones en el catálogo, contratar a alguien en una posición nueva obliga a
crear nueve cuentas antes de poder cargarle una hora.** Y si nadie las crea, esas
horas no se pueden subir — o caen en la posición equivocada por regla de
repuesto, que es exactamente lo que pasó con el SPA y el departamento 0130.

Generándola, una posición nueva **aparece sola** en el archivo del mes siguiente,
y un departamento apagado en Provisionamiento deja de aparecer. Nada que
mantener.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.models.department_catalog import DepartmentCatalog
from app.models.market_code import MarketCode
from app.models.payroll_position import PayrollPosition
from app.models.room_type_config import RoomTypeConfig
from app.models.stat_account import StatAccount


@dataclass(frozen=True)
class FilaGrilla:
    """Una fila a llenar: la cuenta y de quién es."""
    account_code: str
    account_name: str
    unidad: str
    dept_code: str = ""
    dept_name: str = ""
    position_code: str = ""
    position_name: str = ""
    room_type_code: str = ""
    room_type_name: str = ""
    dim_type: str = ""
    dim_code: str = ""

    @property
    def llave(self) -> tuple:
        """La misma llave que la restricción de unicidad de la tabla."""
        return (self.account_code, self.dept_code, self.position_code,
                self.room_type_code, self.dim_type, self.dim_code)


# Dimensiones cuya lista de valores todavia no esta decidida. Las cuentas que
# las usan NO generan filas: una fila con un codigo que nadie reconoce es peor
# que no tener la fila.
#
# ✅ CHANNEL y SEGMENT salieron de aca el 2026-08-14 (tabla de Market Codes del
# owner), y COUNTRY el 2026-08-18: el Country Mix ya tiene paises cargados, asi
# que la lista existe. No es un catalogo cerrado —`country_mix_entries` la lleva
# abierta— pero una lista que sale del dato es mejor que ninguna, y es
# exactamente la que el owner ve en su pantalla de Country Mix.
DIMS_SIN_DEFINIR: set[str] = set()


async def _paises(session, scenario_id: str) -> list[str]:
    """Los paises que este escenario ya tiene cargados en su Country Mix.

    La dimension COUNTRY no tiene catalogo cerrado —el owner define su lista al
    cargar—, asi que la lista sale del dato. «Others» incluido: es una fila
    legitima de su mix, no un descarte.
    """
    from app.models.country_mix import CountryMixEntry

    filas = (await session.execute(
        select(CountryMixEntry.country)
        .where(CountryMixEntry.scenario_id == scenario_id).distinct())).scalars().all()
    return sorted({c for c in filas if c})


async def _posiciones(session, scenario_id: str) -> list[tuple[str, str, str]]:
    """Los pares (departamento, posicion) DISTINTOS, con su nombre.

    ⚠️ Una posicion puede tener VARIAS personas: hay tres filas de «AGENTE DE
    RECEPCION 501» en el mismo departamento. Recorriendo las filas de planilla
    salian 126 llaves repetidas, y la grilla habria pedido el mismo dato tres
    veces — o peor, la carga habria guardado el ultimo y perdido los otros dos.

    Se saltan las que no tienen codigo de posicion: sin codigo no hay forma de
    identificarlas en un archivo.
    """
    filas = (await session.execute(
        select(PayrollPosition)
        .where(PayrollPosition.scenario_id == scenario_id)
        .order_by(PayrollPosition.dept_code, PayrollPosition.position_code)
    )).scalars().all()
    vistas: dict[tuple[str, str], str] = {}
    for p in filas:
        if not p.position_code:
            continue
        vistas.setdefault((p.dept_code, p.position_code), p.position_name or "")
    return [(d, c, n) for (d, c), n in vistas.items()]


async def _departamentos(session) -> list[DepartmentCatalog]:
    return list((await session.execute(
        select(DepartmentCatalog).order_by(DepartmentCatalog.dept_code)
    )).scalars().all())


async def _market_codes(session) -> list[MarketCode]:
    return list((await session.execute(
        select(MarketCode).where(MarketCode.activo.is_(True))
        .order_by(MarketCode.orden, MarketCode.code))).scalars().all())


async def _tipos_habitacion(session, hotel_id: str) -> list[RoomTypeConfig]:
    return list((await session.execute(
        select(RoomTypeConfig)
        .where(RoomTypeConfig.hotel_id == hotel_id)
        .order_by(RoomTypeConfig.code)
    )).scalars().all())


async def construir(session, scenario, cuentas: list[StatAccount] | None = None
                    ) -> list[FilaGrilla]:
    """Las filas que hay que llenar para este escenario.

    El orden es el del catálogo y, dentro de cada cuenta, el de la planilla —o
    sea el mismo que el owner ya conoce de sus otros archivos.
    """
    if cuentas is None:
        cuentas = list((await session.execute(
            select(StatAccount).where(StatAccount.activa.is_(True))
            .order_by(StatAccount.grupo, StatAccount.code))).scalars().all())

    posiciones = await _posiciones(session, scenario.id)
    deptos = await _departamentos(session)
    nombre_dep = {d.dept_code: d.dept_name for d in deptos}
    tipos = await _tipos_habitacion(session, scenario.hotel_id)
    mcodes = await _market_codes(session)
    paises = await _paises(session, scenario.id)
    # Los canales salen de los market codes, no de una lista aparte: asi no
    # pueden desincronizarse. Un codigo SIN canal no aporta canal.
    canales = sorted({m.canal for m in mcodes if m.canal})

    # Los departamentos que de verdad tienen gente. Un depto sin una sola
    # posición no va a tener horas: ponerle 9 filas en blanco es ruido.
    deptos_con_gente = sorted({d for d, _, _ in posiciones if d})

    filas: list[FilaGrilla] = []
    for c in cuentas:
        dims = c.dims_permitidas()
        base = dict(account_code=c.code, account_name=c.nombre_es, unidad=c.unidad)

        # Si la cuenta necesita una dimensión que todavía no está definida, no
        # se generan filas para ella. Ver `DIMS_SIN_DEFINIR`.
        if dims & DIMS_SIN_DEFINIR:
            continue

        if "SEGMENT" in dims:
            # El segmento de mercado ES el market code de Opera. Si la cuenta
            # ademas se abre por tipo de habitacion, se cruzan.
            for mc in mcodes:
                if "ROOMTYPE" in dims:
                    for t in tipos:
                        filas.append(FilaGrilla(
                            **base, room_type_code=t.code, room_type_name=t.name or "",
                            dim_type="SEGMENT", dim_code=mc.code))
                else:
                    filas.append(FilaGrilla(**base, dim_type="SEGMENT",
                                            dim_code=mc.code))
        elif "CHANNEL" in dims:
            for c in canales:
                filas.append(FilaGrilla(**base, dim_type="CHANNEL", dim_code=c))
        elif "COUNTRY" in dims:
            # Los paises son los que el escenario ya tiene en su Country Mix.
            # Si no hay ninguno, no se generan filas: pedir un pais que nadie
            # cargo es pedir que alguien lo invente.
            for pais in paises:
                filas.append(FilaGrilla(**base, dim_type="COUNTRY", dim_code=pais))
        elif "POSITION" in dims:
            # Una fila por POSICIÓN, que es como el owner presupuesta las horas
            # y el headcount (confirmado 2026-08-14).
            for dep, cod, nom in posiciones:
                filas.append(FilaGrilla(
                    **base, dept_code=dep, dept_name=nombre_dep.get(dep, ""),
                    position_code=cod, position_name=nom))
        elif "ROOMTYPE" in dims:
            for t in tipos:
                filas.append(FilaGrilla(**base, room_type_code=t.code,
                                        room_type_name=t.name or ""))
        elif "DEPT" in dims:
            # Solo los departamentos con gente para las de planilla; para el
            # resto (kilos, covers, tratamientos) el departamento de la cuenta
            # lo decide el mapeo, así que se ofrecen todos los del catálogo.
            # Lo que la cuenta declara; si no declara nada, los departamentos
            # con gente (planilla) o todo el catálogo.
            universo = c.deptos_propios() or (
                deptos_con_gente if c.grupo in ("9900", "9980")
                else [d.dept_code for d in deptos])
            for dep in universo:
                filas.append(FilaGrilla(**base, dept_code=dep,
                                        dept_name=nombre_dep.get(dep, "")))
        elif not dims:
            # Total del hotel: una sola fila.
            filas.append(FilaGrilla(**base))

    return filas
