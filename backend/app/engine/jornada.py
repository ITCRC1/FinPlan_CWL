# -*- coding: utf-8 -*-
"""La jornada: cuántas horas tiene un mes y cómo tienen que cerrar.

**Regla vigente (owner, 2026-11-10): días naturales del mes × 8 horas.**

    «configurar cada mes con un total de horas según el número de días que
     tenga el mes, por 8 horas diarias» · «podemos poner esto como base para el
     cálculo del FTE»

    2027: ene 248 · feb 224 · mar 248 · abr 240 · … · total 2,920 (365 × 8)
    En bisiesto, febrero da 232.

Reemplaza a la base fija de 240 (30 días × 8) del 2026-08-14, que se cuenta
abajo como historia. Lo que NO cambió de esa regla: el mes se trabaja completo
(el día libre semanal ya está adentro), las vacaciones y la incapacidad
sustituyen horas en vez de sumarse, y las extras van por encima.

Por qué el calendario y no 240: la 9980 de Integrity se registra POR DÍA (el
nivel 6 de la cuenta es el día). Alguien a tiempo completo en enero registra
31 × 8 = 248. Con base 240 cada mes de 31 días se leía como 8 horas de más y un
FTE de 1.03; con base 224 febrero se leía como un FTE de 0.93.

─── Historia: la regla del 2026-08-14 (base fija de 240) ───

**La regla, en palabras del owner (2026-08-14):**

    «Se trabajan 8 horas por día, y un día libre a la semana, en una base de
     30 días naturales.»

    «Al final, las horas regulares, más horas tomadas en vacaciones, horas
     incapacidad, debe dar 240 horas.»

    «Las extras y los días libres laborados es otra cosa.»

    240 = 30 días × 8 horas

⚠️ **El segundo mensaje corrige la lectura obvia del primero.** De «un día libre
a la semana» uno deduciría 25.71 días trabajados y 205.71 horas. Pero el owner
cierra en **240**, que son los 30 días completos: o sea que la base de horas es
el mes natural entero y el día libre ya está adentro. Es lo habitual en planilla
de Costa Rica — el mes se paga completo, llueva o truene.

**La identidad que tiene que cumplirse, por posición y por mes:**

    9980 regulares
  + 9985 vacaciones tomadas
  + 9986 incapacidad
  ─────────────────────────
  = 240 × FTE

Las vacaciones y la incapacidad **no se suman encima**: sustituyen horas que no
se trabajaron. El mes se paga completo igual.

**Y lo que va POR ENCIMA de los 240**, que es otra cosa (owner, 2026-08-14):

    9981 extras
    9982 día libre laborado
    9983 feriado laborado

Son tiempo que se trabajó **además** del mes y que se paga recargado. Meterlas en
la identidad haría que quien trabaja extras «no cierre», cuando es justo al
revés: trabajó más.

**Para qué sirve.** Sin ella, una celda de horas es un número suelto: nadie puede
decir si 260 horas es sobretiempo real o un error de digitación. Con ella, cada
posición **cierra o no cierra**, y lo que no cierra se ve.

Es la primera vez que las estadísticas tienen una comprobación propia. Todo lo
demás en este proyecto se verifica contra el P&L; las horas no tienen contra qué
cuadrarse, así que su control es interno.
"""
import calendar
from decimal import Decimal

# Las horas de un día de trabajo. Es el único número fijo de la jornada: las
# horas del mes salen del calendario (`horas_del_mes`).
HORAS_POR_DIA = Decimal("8")

#: La cuenta donde se guarda la base (owner, 2026-11-10: «asignar una cuenta
#: estadística para poner esta base»). Sin valor cargado, vale el calendario.
#: En Integrity se registra 8 por día y el mes suma solo: 248, 224, 240…
CUENTA_BASE = "9979"

#: Las tres cuentas que tienen que sumar `horas_del_mes`. El mes se paga completo:
#: las vacaciones y la incapacidad sustituyen horas, no se agregan.
CUENTAS_DE_LA_JORNADA = ("9980", "9985", "9986")

#: Lo que va POR ENCIMA del mes: tiempo trabajado además, pagado recargado.
#: NO entra en la identidad — si entrara, quien trabaja extras «no cerraría».
CUENTAS_SOBRE_LA_JORNADA = ("9981", "9982", "9983")

#: Colchón para no gritar por un redondeo. Media jornada.
TOLERANCIA = HORAS_POR_DIA / 2


def dias_del_mes(anio: int, mes: int) -> int:
    """Los días naturales del mes: 31, 30, 28 o 29 (bisiesto)."""
    return calendar.monthrange(anio, mes)[1]


def horas_del_mes(anio: int, mes: int, fte: Decimal | float = 1) -> Decimal:
    """Las horas que le corresponden a esa posición en el mes: días del mes × 8 × FTE.

    Enero (31 días) da 248; con FTE 0.5, 124. Febrero 2027 da 224.
    """
    return Decimal(dias_del_mes(anio, mes)) * HORAS_POR_DIA * Decimal(str(fte))


def bases_del_anio(anio: int, cargadas: dict[int, Decimal | float] | None = None) -> list[Decimal]:
    """Las horas de 1 FTE de los doce meses: lo cargado en la 9979 y, donde no
    hay nada (o hay cero), los días del mes × 8.

    Un cero no se respeta a propósito: una base de 0 horas haría infinito el FTE
    de cualquiera que trabajó ese mes. Un mes cerrado se expresa con FTE 0, no
    con una jornada de 0 horas.
    """
    cargadas = cargadas or {}
    out = []
    for m in range(1, 13):
        v = cargadas.get(m)
        out.append(Decimal(str(v)) if v else horas_del_mes(anio, m))
    return out


def fte_desde_horas(horas_regulares: Decimal | float, anio: int, mes: int,
                    base: Decimal | float | None = None) -> Decimal:
    """El FTE que implican unas horas regulares: horas ÷ (días del mes × 8).

    La fórmula de `CLAUDE.md` §18.4 —FTE = horas regulares / horas del mes— con
    el divisor del calendario (owner, 2026-11-10). 248 horas en enero = 1 FTE;
    224 en febrero también.
    """
    divisor = Decimal(str(base)) if base else horas_del_mes(anio, mes)
    return Decimal(str(horas_regulares)) / divisor


def cierra_la_jornada(horas: dict[str, Decimal | float], anio: int, mes: int,
                      fte: Decimal | float = 1,
                      base: Decimal | float | None = None) -> tuple[bool, Decimal]:
    """¿Las tres cuentas de la jornada suman el mes de esta posición?

    Devuelve `(cierra, diferencia)`. La diferencia es lo que sobra (positivo) o
    lo que falta (negativo) contra `días del mes × 8 × FTE` —o contra la base
    cargada en la 9979, si se pasa `base`—.

    Se AVISA, no se bloquea: puede haber un caso real que el sistema no conozca,
    y el dueño del dato es el owner. Pero se avisa siempre — una posición que no
    cierra es un dato del que no se puede sacar ni el FTE ni el costo por hora.
    """
    total = sum((Decimal(str(horas.get(c, 0) or 0))
                 for c in CUENTAS_DE_LA_JORNADA), Decimal("0"))
    mes_completo = Decimal(str(base)) if base else horas_del_mes(anio, mes)
    dif = total - mes_completo * Decimal(str(fte))
    return abs(dif) <= TOLERANCIA, dif
