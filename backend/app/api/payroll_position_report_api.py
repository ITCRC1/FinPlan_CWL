"""Planilla por CÓDIGO DE POSICIÓN — el reporte que hace útil al código.

El owner le puso un código único a cada posición (`0111-01`, `0111-02`…). Ese
código solo vale la pena si se puede reportar por él: cuánto gana bruto esa
posición, cuánto se le va en comisiones, en horas extra, en feriados; y cuánto
cuesta de verdad una vez que se le suman las cargas.

Los 17 conceptos de nómina CR se agrupan en tres:

  DEVENGADO   lo que recibe la persona (6000 salario, 6001 horas extra,
              6002 día libre, 6003 feriado laborado, 6010 comisiones,
              6024 vacaciones tomadas, 6027 bono, 6004 incapacidades).
  CARGAS      lo que cuesta tenerla, sin que ella lo reciba en el mes
              (6020 CCSS, 6021 aguinaldo, 6022 INS, 6023 provisión de
              vacaciones, 6026 cesantía).
  BENEFICIOS  especie y reembolsos (6025 cafetería, 6028 vivienda,
              6029 transporte, 6030 otros).

La suma de los tres es el COSTO de la posición — el mismo número que viaja al
P&L. Se separan porque «cuánto gana» y «cuánto cuesta» son dos preguntas
distintas y mezclarlas es la forma más rápida de discutir con un número que no
es el que se estaba pensando.

El reporte trae ADEMÁS su propia auditoría de códigos: sin código y códigos
repetidos. Un código repetido no da error en ningún lado — simplemente junta dos
posiciones en un renglón y el reporte queda mintiendo sin avisar.
"""
from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errores import ErrorApi
from app.db import get_db
from app.models.scenario import Scenario
from app.models.payroll_position import PayrollPosition
from app.models.payroll_concept_entry import PayrollConceptEntry

router = APIRouter(tags=["payroll-report"])

ZERO = Decimal("0")
MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]

# Marcador de las filas sintéticas del GL en los escenarios de actuales: una por
# departamento, sin persona detrás. Aportan costo pero no headcount, y por eso
# el resto del sistema también las trata aparte (`payroll_api`).
CODIGO_GL = "GL"

# (columna, código GL, etiqueta, grupo)
CONCEPTOS: list[tuple[str, str, str, str]] = [
    ("c6000_sw",              "6000", "Salario bruto",         "DEVENGADO"),
    ("c6001_overtime",        "6001", "Horas extra",           "DEVENGADO"),
    ("c6002_day_off",         "6002", "Día libre",             "DEVENGADO"),
    ("c6003_working_holiday", "6003", "Feriado laborado",      "DEVENGADO"),
    ("c6010_commissions",     "6010", "Comisiones",            "DEVENGADO"),
    ("c6024_vacations_taken", "6024", "Vacaciones tomadas",    "DEVENGADO"),
    ("c6027_incentive_bonus", "6027", "Bono",                  "DEVENGADO"),
    ("c6004_disabilities",    "6004", "Incapacidades",         "DEVENGADO"),
    ("c6020_ccss",            "6020", "CCSS patronal",         "CARGAS"),
    ("c6021_aguinaldo",       "6021", "Aguinaldo",             "CARGAS"),
    ("c6022_occ_hazard",      "6022", "INS riesgos",           "CARGAS"),
    ("c6023_vacation_prov",   "6023", "Vacaciones (provisión)", "CARGAS"),
    ("c6026_severance",       "6026", "Cesantía",              "CARGAS"),
    ("c6025_cafeteria",       "6025", "Cafetería",             "BENEFICIOS"),
    ("c6028_housing",         "6028", "Vivienda",              "BENEFICIOS"),
    ("c6029_transport",       "6029", "Transporte",            "BENEFICIOS"),
    ("c6030_other",           "6030", "Otros beneficios",      "BENEFICIOS"),
]
COLS = [c[0] for c in CONCEPTOS]
GRUPO_DE = {c[0]: c[3] for c in CONCEPTOS}


def _cero12() -> list[float]:
    return [0.0] * 12


@router.get("/reports/payroll-by-position/{scenario_id}/")
async def planilla_por_posicion(
    scenario_id: str,
    dept: str = Query("", description="Filtra por departamento; vacío = todos"),
    db: AsyncSession = Depends(get_db),
):
    scenario = await db.get(Scenario, scenario_id)
    if scenario is None:
        raise ErrorApi(404, "escenario.no_encontrado")

    posiciones = (await db.execute(
        select(PayrollPosition)
        .where(PayrollPosition.scenario_id == scenario_id)
        .order_by(PayrollPosition.dept_code, PayrollPosition.position_code)
    )).scalars().all()
    if dept:
        posiciones = [p for p in posiciones if p.dept_code == dept]

    ids = {p.id for p in posiciones}
    entradas = [e for e in (await db.execute(
        select(PayrollConceptEntry).where(
            PayrollConceptEntry.scenario_id == scenario_id))).scalars()
        if e.position_id in ids and 1 <= (e.month or 0) <= 12]

    por_posicion: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {c: _cero12() for c in COLS})
    for e in entradas:
        fila = por_posicion[e.position_id]
        for c in COLS:
            fila[c][e.month - 1] += float(getattr(e, c) or 0)

    filas = []
    for p in posiciones:
        meses = por_posicion.get(p.id) or {c: _cero12() for c in COLS}
        anual = {c: round(sum(meses[c]), 2) for c in COLS}
        # El costo se arma sumando los conceptos YA REDONDEADOS: así el renglón
        # cuadra contra sus propias columnas y no hay que explicar centavos.
        grupos = {g: round(sum(v for c, v in anual.items() if GRUPO_DE[c] == g), 2)
                  for g in ("DEVENGADO", "CARGAS", "BENEFICIOS")}
        fte = [float(getattr(p, f"fte_{m}") or 0) for m in MESES]
        filas.append({
            "position_id": p.id,
            "position_code": (p.position_code or "").strip(),
            "position_name": p.position_name,
            "employee_name": p.employee_name,
            "dept_code": p.dept_code,
            "dept_name": p.dept_name or "",
            "salary_amount": float(p.salary_amount or 0),
            "salary_currency": p.salary_currency,
            "fte": [round(v, 4) for v in fte],
            "fte_prom": round(sum(fte) / 12, 4),
            "anual": anual,
            "meses": {c: [round(v, 2) for v in meses[c]] for c in COLS},
            "devengado": grupos["DEVENGADO"],
            "cargas": grupos["CARGAS"],
            "beneficios": grupos["BENEFICIOS"],
            "costo": round(sum(grupos.values()), 2),
        })

    total_anual = {c: round(sum(f["anual"][c] for f in filas), 2) for c in COLS}
    total_meses = {c: [round(sum(f["meses"][c][m] for f in filas), 2) for m in range(12)]
                   for c in COLS}

    # ── Auditoría del código ────────────────────────────────────────────────
    # Se corre SIEMPRE, no bajo pedido: el reporte entero se apoya en que el
    # código sea único, así que si deja de serlo hay que verlo acá y no
    # descubrirlo cuando dos posiciones aparezcan sumadas en una fila.
    sin_codigo = [{"dept_code": f["dept_code"], "position_name": f["position_name"],
                   "employee_name": f["employee_name"]}
                  for f in filas if not f["position_code"]]
    por_codigo: dict[str, list[dict]] = defaultdict(list)
    for f in filas:
        # `GL` NO es el código de una posición: es el marcador de las filas
        # sintéticas «(Actual GL)» que traen la planilla real del GL, una por
        # departamento. Once filas con el mismo marcador es lo esperado, no un
        # choque. Contarlas como duplicado haría que TODO escenario de actuales
        # abriera el reporte en rojo — y una alerta que siempre está encendida
        # es una alerta que nadie mira.
        if f["position_code"] and f["position_code"] != CODIGO_GL:
            por_codigo[f["position_code"]].append(f)
    duplicados = [
        {"position_code": cod,
         "posiciones": [{"dept_code": x["dept_code"], "position_name": x["position_name"],
                         "employee_name": x["employee_name"]} for x in v]}
        for cod, v in sorted(por_codigo.items()) if len(v) > 1
    ]

    return {
        "scenario_id": scenario_id,
        "year": scenario.year,
        "dept": dept,
        "conceptos": [{"key": k, "code": c, "label": l, "grupo": g}
                      for k, c, l, g in CONCEPTOS],
        "rows": filas,
        "totales": {
            "anual": total_anual,
            "meses": total_meses,
            "devengado": round(sum(f["devengado"] for f in filas), 2),
            "cargas": round(sum(f["cargas"] for f in filas), 2),
            "beneficios": round(sum(f["beneficios"] for f in filas), 2),
            "costo": round(sum(f["costo"] for f in filas), 2),
            "fte_prom": round(sum(f["fte_prom"] for f in filas), 4),
        },
        "auditoria": {
            "sin_codigo": sin_codigo,
            "duplicados": duplicados,
            "codigos_unicos": len(por_codigo),
            "posiciones": len(filas),
            "filas_gl": sum(1 for f in filas if f["position_code"] == CODIGO_GL),
            "limpio": not sin_codigo and not duplicados,
        },
    }


@router.get("/payroll/{scenario_id}/next-position-code/")
async def siguiente_codigo(
    scenario_id: str,
    dept: str = Query(..., description="Departamento, p.ej. 0111"),
    count: int = Query(1, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Los próximos `count` códigos libres del departamento: `0111-06`, `0111-07`…

    Existe para que la pantalla no tenga que adivinarlos. Antes, agregar tres
    personas les ponía el MISMO código a las tres, y duplicar una posición con
    «+1» copiaba el código de la original — dos formas silenciosas de romper el
    esquema que el owner acaba de construir a mano.

    El formato sale del código que ya usa ese departamento (`0111-NN`). Si el
    departamento todavía no tiene ninguno, arranca en `-01`.
    """
    codigos = [(p.position_code or "").strip() for p in (await db.execute(
        select(PayrollPosition).where(
            PayrollPosition.scenario_id == scenario_id,
            PayrollPosition.dept_code == dept))).scalars()]

    usados: set[int] = set()
    ancho = 2
    for c in codigos:
        if not c.startswith(f"{dept}-"):
            continue
        cola = c[len(dept) + 1:]
        if cola.isdigit():
            usados.add(int(cola))
            ancho = max(ancho, len(cola))

    # Se sigue desde el mayor, NO se rellenan huecos: un código que se borró
    # puede estar citado en un reporte viejo o en una regla de allocation, y
    # reciclarlo lo haría apuntar a otra persona.
    siguiente = (max(usados) + 1) if usados else 1
    return {
        "dept": dept,
        "codes": [f"{dept}-{n:0{ancho}d}" for n in range(siguiente, siguiente + count)],
        "usados": len(usados),
    }
