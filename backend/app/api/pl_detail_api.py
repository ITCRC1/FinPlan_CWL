# -*- coding: utf-8 -*-
"""Los tres P&L Detail del owner: Consolidado, Hotel y Club.

Owner, 2026-08-27, entregando `BUDGET 2026-AMA formato.xlsx`: *«lee bien estos
formatos de excel uno a uno, creálos en Reporting … con la información de
presupuesto Budget 2026»*.

Son tres hojas de ese libro —`P&L Detail Owners Full`, `P&L Detail Hotel` y
`P&L Detail Club`—. La cuarta, `P&L Full Detail`, **ya existía**:
`pl_full_detail_api.py` se construyó con este mismo formato, cuenta por cuenta.

## Los tres son el MISMO reporte con un ámbito distinto

Medido contra el libro del owner, celda por celda:

    Consolidado   TOTAL REVENUES  547,078.00   GOP  -312,617.08
    Hotel         TOTAL REVENUES  397,038.00   GOP  -255,895.89
    Club          TOTAL REVENUES  150,040.00   NET   -56,721.19

    547,078.00 - 150,040.00 = 397,038.00          ✔ el ingreso se parte
    -312,617.08 - (-56,721.19) = -255,895.89      ✔ y el resultado también

Ésa es la propiedad que hace que esto sea UN reporte y no tres: **el Hotel es el
Consolidado menos el Club**, y por debajo de Operating Profit todo se corre por
el resultado del Club. El overhead NO se parte —administración, ventas y
mantenimiento sirven a los dos— y en el Excel del owner el total de overhead es
idéntico en las dos hojas, que es lo que lo confirma.

Escribirlos como tres plantillas sueltas habría dejado tres verdades que hay que
mantener sincronizadas a mano; la primera vez que alguien agregue una línea de
ingreso, dos de las tres se quedan viejas y ninguna avisa.

## De dónde sale cada número

Del MISMO motor que Cierre de Mes, el P&L y la Junta: `_monthly_results`. No se
recalcula nada acá — un reporte que calcula por su cuenta es un segundo motor
que hay que mantener, y el día que discrepan nadie sabe cuál creer.

⚠️ **Antes leía la tabla `pl_lines`, y era un defecto.** Esa tabla es una FOTO:
sólo existe si alguien apretó «Recalcular». Con los actuales de 2026 —el mayor
cargado, 115 filas de marzo a julio— estos tres reportes salían en CERO porque
el escenario nunca se había recalculado. El dato estaba y el reporte decía que
no había nada, que es peor que un error: un cero se lee como una respuesta.

## El bloque de control, al pie

El Excel del owner cierra con cuatro totales por naturaleza —planilla, opex,
costo y propiedad— y una línea `Variance 0`. No es decoración: es su cuadre.
Acá se replica y **se calcula la diferencia de verdad**, así que si algún día no
cierra, se ve. Un reporte de control que no se controla a sí mismo no controla
nada.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.auth import get_current_user
from app.db import get_session
from app.errores import ErrorApi
from app.models.club_membership_stat import ClubMembershipStat
from app.models.scenario import Scenario
from app.models.scenario_stat import ScenarioStat

router = APIRouter(tags=["pl-detail"])

AMBITOS = ("consolidado", "hotel", "club")

#: Las líneas del Club. En el ámbito `hotel` se restan; en `club` son lo único.
CLUB = {"revenue": "REV_CLUB", "opex": "OPEX_CLUB",
        "cost": "COS_CLUB", "profit": "PROFIT_CLUB"}

#: (tipo, rótulo, [códigos que suma]). `tipo`:
#:   sec   encabezado de sección, sin números
#:   det   línea de detalle
#:   sub   subtotal
#:   tot   total fuerte
#:   esp   espacio en blanco (el Excel los usa para respirar)
#:
#: ⚠️ Los rótulos son los del owner, **con sus erratas incluidas** («Total
#: Operationg expenses», «Miscellaneous  Revenue» con dos espacios). Corregirlas
#: rompería el cotejo contra su libro, que es para lo que sirve este reporte.
CONSOLIDADO: list[tuple] = [
    ("sec", "REVENUES", []),
    ("det", "Rooms", ["REV_ROOMS", "REV_ROOMS_OTHER"]),
    ("det", "F&B", ["REV_FB", "REV_FB_BEV", "REV_FB_MISC"]),
    ("det", "SPA", ["REV_SPA"]),
    ("det", "Tours", ["REV_TOURS"]),
    ("det", "Retail-Gift Shop", ["REV_RETAIL", "REV_TIENDA"]),
    ("det", "Madresal Club", ["REV_CLUB"]),
    ("det", "Laundry", ["REV_LAUNDRY"]),
    ("det", "Private Bar", ["REV_PRIVATE_BAR"]),
    ("det", "Miscellaneous  Revenue", ["REV_MISC_OTHER", "REV_SUSTAINABILITY",
                                       "REV_TRANSPORTATION", "REV_INNOCEANA"]),
    ("esp", "", []),
    ("tot", "TOTAL REVENUES", ["TOTAL_REVENUES"]),
    ("esp", "", []),
    ("sec", "Operating Expenses", []),
    ("det", "Rooms", ["OPEX_ROOMS"]),
    ("det", "F&B", ["OPEX_FB", "COS_FB_FOOD", "COS_FB_BEV", "COS_FB_MISC"]),
    ("det", "SPA", ["OPEX_SPA", "COS_SPA"]),
    ("det", "Tours", ["OPEX_TOURS", "COS_TOURS"]),
    ("det", "Retail-Gift Shop", ["OPEX_RETAIL", "COS_RETAIL",
                                 "OPEX_TIENDA", "COS_TIENDA"]),
    ("det", "Madresal Club", ["OPEX_CLUB", "COS_CLUB"]),
    ("det", "Laundry", ["OPEX_LAUNDRY", "COS_LAUNDRY"]),
    ("det", "Private Bar", ["OPEX_PRIVATE_BAR", "COS_PRIVATE_BAR"]),
    ("det", "Miscellaneous  Revenue", ["OPEX_MISCELLANEOUS", "OPEX_TRANSPORTATION",
                                       "COS_TRANSPORTATION", "OPEX_INNOCEANA",
                                       "COS_INNOCEANA"]),
    ("esp", "", []),
    ("tot", "Total Operationg expenses", ["TOTAL_OPERATING_EXPENSES"]),
    ("esp", "", []),
    ("sec", "Operating Profit", []),
    ("det", "Rooms", ["PROFIT_ROOMS"]),
    ("det", "F&B", ["PROFIT_FB"]),
    ("det", "SPA", ["PROFIT_SPA"]),
    ("det", "Tours", ["PROFIT_TOURS"]),
    ("det", "Retail-Gift Shop", ["PROFIT_RETAIL", "PROFIT_TIENDA"]),
    ("det", "Madresal Club", ["PROFIT_CLUB"]),
    ("det", "Laundry", ["PROFIT_LAUNDRY"]),
    ("det", "Private Bar", ["PROFIT_PRIVATE_BAR"]),
    ("det", "Miscellaneous  Revenue", ["PROFIT_MISC_OTHER", "PROFIT_SUSTAINABILITY",
                                       "PROFIT_TRANSPORTATION", "PROFIT_INNOCEANA"]),
    ("esp", "", []),
    ("tot", "OPERATING PROFIT", ["OPERATING_PROFIT"]),
    ("esp", "", []),
    ("sec", "OVERHEAD EXPENSES", []),
    # ⚠️ Cada renglón suma `OH_` **y** `COH_`. El overhead tiene costo de ventas
    # propio y vive en su propio código: en julio 2026, Sistemas daba 5.019,44
    # por `OH_` y el libro del owner decía 5.956,77 — los 937,33 que faltaban
    # eran `COH_INFORMATION_SYSTEM`. Como el TOTAL sí los incluía, los renglones
    # no sumaban su propio total y nada lo avisaba.
    ("det", "Administrations", ["OH_ADMIN", "COH_ADMIN"]),
    ("det", "Sales & Marketing", ["OH_SALES_MARKETING", "COH_SALES_MARKETING"]),
    ("det", "Maintenance", ["OH_MAINTENANCE", "COH_MAINTENANCE"]),
    ("det", "Information System", ["OH_INFORMATION_SYSTEM",
                                   "COH_INFORMATION_SYSTEM"]),
    ("det", "Utilities", ["OH_UTILITIES", "COH_UTILITIES"]),
    ("det", "Claro Huerta", ["OH_CLARO_HUERTA", "COH_CLARO_HUERTA"]),
    # Los dos departamentos de REPARTO. Su renglón es el SOBRANTE que no
    # alcanzó a repartirse (owner, 2026-08-28: «si tiene saldo que aparezca esa
    # diferencia en overhead»). Faltaban en la plantilla, así que en julio 2026
    # los 1.121,36 de lavandería estaban dentro del total y en NINGÚN renglón.
    ("det", "Cafeteria", ["OH_CAFETERIA", "COH_CAFETERIA"]),
    ("det", "Laundry", ["OH_LAUNDRY", "COH_LAUNDRY"]),
    ("det", "Employee Benefits", ["OH_EMPLOYEE_BENEFITS",
                                  "COH_EMPLOYEE_BENEFITS"]),
    ("det", "Area Recreativa", ["OH_AREC", "COH_AREC"]),
    ("esp", "", []),
    ("tot", "TOTAL OVERHEAD EXPENSES", ["TOTAL_OVERHEAD"]),
    ("esp", "", []),
    ("tot", "TOTAL GROSS OPERATING PROFIT", ["GOP"]),
    ("esp", "", []),
    ("det", "Rent", ["RENT"]),
    ("det", "Management Fees (5%)", ["MGMT_FEE_5_ROYALTIES", "MGMT_FEE_3"]),
    ("sub", "TOTAL RENT AND MANAGEMENT FEES", ["TOTAL_RENT_MGMT_FEES"]),
    ("esp", "", []),
    ("det", "Property Insurance", ["PROPERTY_INSURANCE"]),
    ("sub", "PROPERTY INSURANCE", ["TOTAL_PROPERTY_INSURANCE"]),
    ("esp", "", []),
    ("det", "Other Expenses", ["OTHER_EXPENSES"]),
    ("sub", "TOTAL OTHER EXPENSES", ["TOTAL_OTHER_EXPENSES"]),
    ("esp", "", []),
    ("tot", "TOTAL NON OP EXPENSES", ["TOTAL_NON_OP"]),
    ("esp", "", []),
    ("tot", "EBITDA BEFORE CAPITAL", ["EBITDA_BEFORE"]),
    ("esp", "", []),
    ("det", "Capital Reserve", ["CAPITAL_RESERVE"]),
    ("det", "Large Improvement", ["LARGE_CAPEX"]),
    ("sub", "CAPITAL EXPENSE", ["CAPITAL_EXPENSE"]),
    ("esp", "", []),
    ("tot", "EBITDA AFTER CAPITAL", ["EBITDA_AFTER"]),
    ("esp", "", []),
    ("det", "Financial Loss", ["FINANCIAL_LOSSES", "BANK_INTEREST", "LEASINGS_RENTS"]),
    ("sub", "FINANCIAL EXPENSES", ["FINANCIAL_EXPENSES"]),
    ("esp", "", []),
    ("det", "Depreciation", ["DEPRECIATION", "ASSET_LOSS"]),
    ("sub", "TOTAL DEPRECIATIONS", ["TOTAL_DEPRECIATIONS"]),
    ("esp", "", []),
    ("tot", "EARNINGS BEFORE INCOME TAXES", ["EBT"]),
    ("det", "Income Taxes (30%)", ["INCOME_TAXES"]),
    ("esp", "", []),
    ("tot", "NET PROFIT", ["NET_PROFIT"]),
]

#: Lo que cambia en la hoja `P&L Detail Hotel`: el Club sale del detalle, y el
#: overhead lista los tres departamentos de servicio que el consolidado resume.
HOTEL_QUITA = {"Madresal Club"}
HOTEL_OVERHEAD = [
    ("det", "Claro Huerta", ["OH_CLARO_HUERTA"]),
    ("det", "Cafeteria", ["OH_CAFETERIA"]),
    ("det", "Laundry", ["OH_LAUNDRY"]),
]

#: `P&L Detail Club`: el departamento 260 solo, con la planilla abierta como en
#: el libro del owner (salario, cargas y beneficios).
CLUB_FILAS: list[tuple] = [
    ("sec", "REVENUES", []),
    ("det", "Cuotas", ["REV_CLUB"]),
    ("esp", "", []),
    ("tot", "TOTAL REVENUES", ["REV_CLUB"]),
    ("esp", "", []),
    ("sec", "Salary and Benefits", []),
    ("esp", "", []),
    ("det", "Total Salary", ["@CLUB_SALARIO"]),
    ("det", "Payroll Taxes", ["@CLUB_CARGAS"]),
    ("det", "Employee Benefits", ["@CLUB_BENEFICIOS"]),
    ("esp", "", []),
    ("sub", "Total Slary and Benefits", ["@CLUB_PLANILLA"]),
    ("esp", "", []),
    ("sec", "Operating Expenses", []),
    # ⚠️ **Sin la planilla.** `OPEX_CLUB` del motor YA la contiene: es el gasto
    # del departamento, no el gasto no-salarial. Listar las dos cosas y sumarlas
    # contaba la planilla dos veces —279,184 de gasto donde el motor dice
    # 187,079— y el reporte cerraba igual contra su propio total. Lo delató el
    # cuadre contra la utilidad del motor.
    ("det", "Operating Expenses", ["@CLUB_OPEX_SIN_PLANILLA"]),
    ("esp", "", []),
    ("sub", "Total Operating Expenses", ["@CLUB_OPEX_SIN_PLANILLA"]),
    ("esp", "", []),
    ("tot", "Total Gastos", ["OPEX_CLUB", "COS_CLUB"]),
    ("esp", "", []),
    ("tot", "NET PROFIT", ["PROFIT_CLUB"]),
    ("esp", "", []),
    # El seguro de propiedad va DEBAJO del GOP en el motor, así que no entra en
    # la utilidad del departamento. Se muestra como memo —el owner lo tiene
    # adentro en su hoja— para que la diferencia contra su libro se vea, en vez
    # de meterlo acá y que las dos cuadren por construcción sin ser lo mismo.
    ("det", "Property Insurance (memo, va bajo GOP)", ["@CLUB_SEGURO"]),
]

MESES = list(range(1, 13))


def _serie(por_codigo: dict[str, list[float]], codigos: list[str]) -> list[float]:
    """Los doce meses de la suma de `codigos`. Un código que no existe suma 0.

    No se rompe si falta: una propiedad puede no tener Private Bar, y ahí el
    renglón tiene que salir en cero — no tumbar el reporte.
    """
    out = [0.0] * 12
    for c in codigos:
        for i, v in enumerate(por_codigo.get(c, [0.0] * 12)):
            out[i] += v
    return out


MAX_VERSIONES = 4          # la del owner: Forecast, Budget, Reforecast y Actual LY


@router.get("/reports/pl-detail/{ambito}/")
async def pl_detail(
    ambito: str,
    scenario_id: str = Query(...),
    comparar: str | None = Query(
        None, description="hasta 3 versiones mas, separadas por coma"),
    _=Depends(get_current_user),
):
    """El P&L Detail del owner, en uno de sus tres ambitos y hasta 4 versiones.

    Owner, 2026-08-27: *«aca tiene que haber al menos 2 versiones mas —actual,
    budget, forecast, actual del año pasado— pero escogibles»*. Su cuadro de
    Full Year lleva exactamente eso: `Forecast 2026 | Budget 2026 | Variance $ |
    Variance % | Reforecast 2026 | Actual 2025`.

    Devuelve los doce meses de cada fila POR VERSION. Los cortes —Mes, YTD,
    Año— y las variaciones se arman en el cliente: mandar cada corte ya hecho
    seria mandar tres veces el mismo dato y un viaje por boton.

    Todas las versiones se rearman con la MISMA plantilla del ambito. Comparar
    dos cascadas distintas daria filas que no se corresponden y una variacion
    que no significa nada.
    """
    if ambito not in AMBITOS:
        raise ErrorApi(422, "reporte.ambito_desconocido", ambito=ambito)

    ids = [scenario_id] + [x.strip() for x in (comparar or "").split(",") if x.strip()]
    # Sin repetidos y conservando el orden: una version comparada contra si
    # misma da una columna de ceros que se lee como «no cambio nada».
    vistos, orden = set(), []
    for i in ids:
        if i not in vistos:
            vistos.add(i)
            orden.append(i)
    ids = orden[:MAX_VERSIONES]

    async with get_session() as s:
        escenarios = []
        for sid in ids:
            e = await s.get(Scenario, sid)
            if e is None:
                raise ErrorApi(404, "escenario.no_encontrado")
            escenarios.append(e)

        plantilla = None
        series: list[list[list[float] | None]] = []
        for e in escenarios:
            plantilla, cascada = await _cascada(s, e.id, ambito)
            series.append(cascada)

        filas = []
        for j, (tipo, rotulo, _cods) in enumerate(plantilla):
            if tipo in ("esp", "sec"):
                filas.append({"tipo": tipo, "rotulo": rotulo if tipo == "sec" else "",
                              "series": [None] * len(ids)})
                continue
            filas.append({
                "tipo": tipo, "rotulo": rotulo,
                "series": [[round(v, 2) for v in serie[j]] for serie in series],
            })

        principal = escenarios[0]
        return {
            "ambito": ambito,
            "scenario_id": principal.id,
            "escenario": _nombre(principal),
            "year": principal.year,
            "versiones": [{"scenario_id": e.id, "escenario": _nombre(e),
                           "kpis": await _kpis(s, e.id)} for e in escenarios],
            "club": await _socios(s, principal.id) if ambito == "club" else None,
            "filas": filas,
            "clases": [await _clases_de(s, e.id) for e in escenarios],
            "control": _control(
                [{"rotulo": f["rotulo"], "meses": f["series"][0],
                  "full": round(sum(f["series"][0]), 2) if f["series"][0] else None}
                 for f in filas], ambito),
        }


#: Los rotulos del cuadro de cierre, en el orden del owner.
CLAVE_CIERRE = [
    "TOTAL REVENUES", "Total Operationg expenses", "OPERATING PROFIT",
    "TOTAL OVERHEAD EXPENSES", "TOTAL GROSS OPERATING PROFIT",
    "TOTAL NON OP EXPENSES", "EBITDA BEFORE CAPITAL", "EBITDA AFTER CAPITAL",
    "EARNINGS BEFORE INCOME TAXES", "NET PROFIT",
]
CLASES_ROTULOS = [("payroll", "Total Payroll and Benefits"),
                  ("opex", "Total Operating Expenses"),
                  ("cost", "Total Cost"),
                  ("property", "Total Property Expenses")]
_NOTA_AMBITO = {"consolidado": "Hotel + Club Madresal",
                "hotel": "Sin el Club Madresal",
                "club": "Solo el departamento 260"}
_TITULO_AMBITO = {"consolidado": "Consolidado", "hotel": "Hotel",
                  "club": "Club Madresal"}


@router.get("/reports/pl-detail/{ambito}/excel/")
async def pl_detail_excel(
    ambito: str,
    scenario_id: str = Query(...),
    comparar: str | None = Query(None),
    mes: int = Query(12, ge=1, le=12),
    _=Depends(get_current_user),
):
    """El mismo reporte, en Excel y con su forma.

    Owner, 2026-08-27: *«el excel no baja lo que esta viendo en la pantalla,
    abre cualquier cosa»* y *«que se baje super nitido y profesional»*.

    Antes bajaba por el exportador GENERICO, que arma una tabla plana. Este
    cuadro tiene encabezados de dos pisos —el bloque `Mayo`/`YTD`/`Full Year` y
    adentro cada version— y aplanarlo daba columnas seguidas sin decir a que
    bloque pertenece cada una: por eso «abria cualquier cosa».

    Se recalcula del lado del servidor con los MISMOS parametros de la pantalla,
    en vez de mandarle el cuadro ya armado. Asi no hay dos formas de llegar al
    numero, que es como empiezan a diferir.
    """
    from app.export.pl_detail_excel import export_pl_detail
    from fastapi import Response

    datos = await pl_detail(ambito, scenario_id, comparar, _)
    datos["clave"] = CLAVE_CIERRE
    datos["clases_rotulos"] = CLASES_ROTULOS
    datos["titulo_ambito"] = _TITULO_AMBITO[ambito]
    datos["nota_ambito"] = _NOTA_AMBITO[ambito]

    nombre = (f"PL_Detail_{_TITULO_AMBITO[ambito].replace(' ', '_')}"
              f"_{datos['year']}.xlsx")
    return Response(
        content=export_pl_detail(datos, mes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


def _nombre(e) -> str:
    return f"{e.type} {e.version} {e.year}"


async def _cascada(s, scenario_id: str, ambito: str):
    """La plantilla del ambito y, en el mismo orden, los doce meses de cada fila.

    Devuelve las dos cosas juntas a proposito: la fila `j` de la salida es la
    fila `j` de la plantilla, y separarlas invita a que alguien las recorra en
    ordenes distintos.
    """
    por_codigo = await _serie_por_codigo(s, scenario_id)
    club_profit = _serie(por_codigo, [CLUB["profit"]])

    if ambito == "club":
        plantilla = CLUB_FILAS
        derivadas = await _derivadas_del_club(s, scenario_id, por_codigo)
    else:
        plantilla = list(CONSOLIDADO)
        derivadas = {}
        if ambito == "hotel":
            plantilla = _plantilla_hotel(plantilla)

    salida: list[list[float] | None] = []
    for tipo, rotulo, codigos in plantilla:
        if tipo in ("esp", "sec"):
            salida.append(None)
            continue
        serie = _serie(por_codigo, [c for c in codigos if not c.startswith("@")])
        for c in codigos:
            if c.startswith("@"):
                for i, v in enumerate(derivadas.get(c, [0.0] * 12)):
                    serie[i] += v
        if ambito == "hotel":
            resta = _que_resta_el_hotel(rotulo, codigos, por_codigo, club_profit)
            if resta:
                serie = [a - b for a, b in zip(serie, resta)]
        salida.append(serie)
    return plantilla, salida


async def _clases_de(s, scenario_id: str) -> dict:
    """Los cuatro totales por NATURALEZA del pie del cuadro de cierre.

    Owner, 2026-08-27: su cuadro lleva planilla, opex, costo y gastos de
    propiedad — un corte por naturaleza, no por departamento.

    ⚠️ **Sale del MISMO `_por_mes` que el tab de Cierre de Mes.** Las lineas del
    P&L estan cortadas por departamento y sumarlas no da «todas las cuentas 7»:
    la planilla y el costo de esos mismos departamentos entran en la misma
    linea. Es otro eje, y ya tiene quien lo calcule bien.
    """
    from app.api.gasto_por_clase_api import _por_mes

    meses = await _por_mes(s, scenario_id)
    return {c: [float(m[c]) for m in meses]
            for c in ("payroll", "cost", "opex", "property")}


async def _serie_por_codigo(s, scenario_id: str) -> dict[str, list[float]]:
    """Los doce meses de cada línea del P&L, CALCULADOS — no leídos de la tabla.

    ⚠️ **Antes esto leía `pl_lines`, y era un defecto.** El resto de la app
    —Cierre de Mes, el P&L, la Junta— calcula al vuelo con `_monthly_results`;
    `pl_lines` es una foto que sólo existe si alguien apretó «Recalcular».

    Se vio con los actuales de 2026: el mayor estaba cargado (115 filas, marzo a
    julio) y estos tres reportes salían en CERO, porque el escenario nunca se
    había recalculado. El dato estaba y el reporte decía que no había nada —
    peor que un error, porque un cero se lee como una respuesta.

    Ahora sale del mismo lugar que todo lo demás. Cuesta una pasada del motor
    por versión, que es exactamente lo que ya paga la pantalla de Cierre de Mes.
    """
    from app.api.pl_api import _monthly_results

    escenario = await s.get(Scenario, scenario_id)
    out: dict[str, list[float]] = {}
    for m in await _monthly_results(s, escenario):
        i = m["month"] - 1
        if not 0 <= i <= 11:
            continue
        for ln in m["lines"]:
            out.setdefault(ln.line_code, [0.0] * 12)[i] += float(ln.amount_usd or 0)
    return out


#: Los totales que, en el Hotel, se corren por el resultado del Club. Todo lo que
#: está POR DEBAJO de Operating Profit: el Club aporta su utilidad al
#: consolidado, así que sacarlo mueve toda la cascada por el mismo monto.
_DEBAJO_DEL_PROFIT = {
    "OPERATING PROFIT", "TOTAL GROSS OPERATING PROFIT", "EBITDA BEFORE CAPITAL",
    "EBITDA AFTER CAPITAL", "EARNINGS BEFORE INCOME TAXES", "NET PROFIT",
}


def _que_resta_el_hotel(rotulo, codigos, por_codigo, club_profit):
    """Qué se le saca a cada total para pasar del Consolidado al Hotel.

    **NO es una sola resta: son tres**, y confundirlas fue el primer bug de este
    archivo. Al ingreso se le saca el INGRESO del Club; al gasto operativo, su
    GASTO; y de Operating Profit para abajo, su RESULTADO — una sola vez, porque
    ahí ingreso y gasto ya vienen netos.

    Restar el resultado (que es negativo) del ingreso lo hacía SUBIR: 584,118
    donde tenían que ser 397,039. Y el reporte seguía cuadrando contra sí mismo
    —la diferencia daba 0— que es justo lo que hace que estos errores pasen
    desapercibidos. Lo que lo delató fue cotejar contra el libro del owner.
    """
    if codigos == ["TOTAL_REVENUES"]:
        return _serie(por_codigo, [CLUB["revenue"]])
    if codigos == ["TOTAL_OPERATING_EXPENSES"]:
        return _serie(por_codigo, [CLUB["opex"], CLUB["cost"]])
    if rotulo in _DEBAJO_DEL_PROFIT:
        return club_profit
    return None


def _plantilla_hotel(plantilla: list[tuple]) -> list[tuple]:
    """Saca el Club del detalle y abre los tres departamentos de servicio.

    El overhead NO se parte: administración, ventas y mantenimiento sirven al
    hotel y al Club por igual, y en el libro del owner el total de overhead es
    idéntico en las dos hojas.
    """
    out = []
    for fila in plantilla:
        tipo, rotulo, codigos = fila
        if tipo == "det" and rotulo in HOTEL_QUITA:
            continue
        if tipo == "det" and rotulo == "Area Recreativa":
            out.extend(HOTEL_OVERHEAD)
            continue
        out.append(fila)
    return out


async def _derivadas_del_club(s, scenario_id: str, por_codigo) -> dict:
    """Las filas del Club que el P&L no emite como línea propia.

    La planilla del Club se abre en salario / cargas / beneficios, que es como
    la mira el owner. Sale de `payroll_concept_entries` del depto 260 — la misma
    fuente que el checkbook, agrupada de otra forma.
    """
    from app.models.payroll_concept_entry import PayrollConceptEntry

    salario = [0.0] * 12
    cargas = [0.0] * 12
    beneficios = [0.0] * 12
    for e in (await s.execute(select(PayrollConceptEntry).where(
            PayrollConceptEntry.scenario_id == scenario_id,
            PayrollConceptEntry.dept_code == "260"))).scalars().all():
        if not 1 <= e.month <= 12:
            continue
        i = e.month - 1
        # El BRUTO gravable: lo que el owner llama «Total Salary».
        salario[i] += sum(float(getattr(e, c) or 0) for c in (
            "c6000_sw", "c6001_overtime", "c6002_day_off", "c6003_working_holiday",
            "c6010_commissions", "c6024_vacations_taken", "c6027_incentive_bonus"))
        # Las CARGAS de ley: CCSS y aguinaldo son las dos que el motor calcula.
        cargas[i] += sum(float(getattr(e, c) or 0) for c in (
            "c6020_ccss", "c6021_aguinaldo", "c6022_occ_hazard",
            "c6023_vacation_prov", "c6026_severance"))
        # Y el RESTO son beneficios al empleado.
        beneficios[i] += sum(float(getattr(e, c) or 0) for c in (
            "c6004_disabilities", "c6025_cafeteria", "c6028_housing",
            "c6029_transport", "c6030_other"))

    seguro = _serie(por_codigo, ["PROPERTY_INSURANCE"])
    opex = _serie(por_codigo, ["OPEX_CLUB", "COS_CLUB"])
    planilla = [a + b + c for a, b, c in zip(salario, cargas, beneficios)]
    return {
        "@CLUB_SALARIO": salario,
        "@CLUB_CARGAS": cargas,
        "@CLUB_BENEFICIOS": beneficios,
        "@CLUB_PLANILLA": planilla,
        "@CLUB_SEGURO": seguro,
        # El gasto del departamento MENOS su planilla: es la parte que el owner
        # lista aparte. Sumar `opex` entero al lado de la planilla la contaría
        # dos veces (ver `CLUB_FILAS`).
        "@CLUB_OPEX_SIN_PLANILLA": [o - p for o, p in zip(opex, planilla)],
    }


async def _kpis(s, scenario_id: str) -> dict:
    """Las siete estadísticas del encabezado del Excel, MES A MES.

    Owner, 2026-08-27: *«mete la estadística que estaba en el excel»*. Son las
    filas 3 a 9 de sus hojas.

    ⚠️ **Ocupación, ADR y RevPAR no se suman: se rederivan.** Son razones. El
    promedio simple de doce meses le daría el mismo peso a un mes lleno que a
    uno cerrado, y con enero a mayo en cero —que es el caso de Amarena— el ADR
    del año habría salido 5/12 más bajo. Por eso el cliente recibe los
    numeradores y denominadores por mes y arma cada corte con ellos.
    """
    stats = {x.month: x for x in (await s.execute(select(ScenarioStat).where(
        ScenarioStat.scenario_id == scenario_id))).scalars().all()}

    def serie(f):
        return [round(f(stats[m]), 4) if m in stats else 0.0 for m in MESES]

    avail = serie(lambda x: float(x.rooms_available or 0))
    occ = serie(lambda x: float(x.rooms_occupied or 0))
    guests = serie(lambda x: float(x.guests or 0))
    # El ingreso de habitaciones del mes, para poder rederivar ADR y RevPAR en
    # cualquier corte: ADR = ingreso / noches ocupadas.
    ingreso = [round(a * o, 2) for a, o in
               zip(serie(lambda x: float(x.adr or 0)), occ)]
    return {
        "rooms_available": avail,
        "rooms_occupied": occ,
        "guests": guests,
        "rooms_revenue": ingreso,
    }


async def _socios(s, scenario_id: str) -> dict | None:
    """Los cuatro conteos del Club. Ver `ClubMembershipStat`: el del período es
    el SALDO del último mes con dato, nunca la suma."""
    filas = sorted((await s.execute(select(ClubMembershipStat).where(
        ClubMembershipStat.scenario_id == scenario_id))).scalars().all(),
        key=lambda x: x.month)
    if not filas:
        return None
    def serie(campo):
        return [next((getattr(f, campo) for f in filas if f.month == m), 0)
                for m in MESES]
    con_dato = [f for f in filas if (f.total or f.pagando)]
    ultimo = con_dato[-1] if con_dato else filas[-1]
    return {
        "meses": {c: serie(c) for c in
                  ("total", "condicionados", "pagando", "acuerdo_pago")},
        "cierre": {c: getattr(ultimo, c) for c in
                   ("total", "condicionados", "pagando", "acuerdo_pago")},
    }


def _control(filas: list[dict], ambito: str = "consolidado") -> dict:
    """El cuadre del pie, con la diferencia CALCULADA.

    El Excel del owner cierra con una línea `Variance 0` escrita a mano. Acá la
    diferencia se computa: si algún día no cierra, se ve. Un reporte de control
    que no se controla a sí mismo no controla nada.
    """
    def total(rotulo: str) -> float:
        for f in filas:
            if f["rotulo"] == rotulo and f["meses"] is not None:
                return f["full"]
        return 0.0

    ingresos = total("TOTAL REVENUES")
    neto = total("NET PROFIT")
    if ambito == "club":
        # La hoja del Club tiene su propia cascada: un solo total de gasto, sin
        # overhead ni no-operativos. Sumar los rótulos del consolidado acá daba
        # gasto 0 y una diferencia de 187,079 — el reporte se acusaba a sí mismo
        # de un descuadre que era del control, no del dato.
        gastos = total("Total Gastos")
    else:
        gastos = (total("Total Operationg expenses") + total("TOTAL OVERHEAD EXPENSES")
                  + total("TOTAL NON OP EXPENSES") + total("CAPITAL EXPENSE")
                  + total("FINANCIAL EXPENSES") + total("TOTAL DEPRECIATIONS")
                  + total("Income Taxes (30%)"))
    return {
        "ingresos": round(ingresos, 2),
        "gastos": round(gastos, 2),
        "utilidad": round(neto, 2),
        "diferencia": round(ingresos - gastos - neto, 2),
    }
