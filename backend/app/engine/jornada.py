# -*- coding: utf-8 -*-
"""La jornada: cuántas horas tiene un mes y cómo tienen que cerrar.

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
from decimal import Decimal

# Los dos números que el owner dio. Todo lo demás se deriva.
HORAS_POR_DIA = Decimal("8")
DIAS_BASE_MES = Decimal("30")

#: Las horas de un mes a tiempo completo. 30 × 8 = 240.
HORAS_MES = DIAS_BASE_MES * HORAS_POR_DIA

#: Las tres cuentas que tienen que sumar `HORAS_MES`. El mes se paga completo:
#: las vacaciones y la incapacidad sustituyen horas, no se agregan.
CUENTAS_DE_LA_JORNADA = ("9980", "9985", "9986")

#: Lo que va POR ENCIMA del mes: tiempo trabajado además, pagado recargado.
#: NO entra en la identidad — si entrara, quien trabaja extras «no cerraría».
CUENTAS_SOBRE_LA_JORNADA = ("9981", "9982", "9983")

#: Colchón para no gritar por un redondeo. Media jornada.
TOLERANCIA = HORAS_POR_DIA / 2


def horas_del_mes(fte: Decimal | float = 1) -> Decimal:
    """Las horas que le corresponden a esa posición en el mes.

    Un FTE de 0.5 —media jornada— cierra en 120, no en 240.
    """
    return HORAS_MES * Decimal(str(fte))


def fte_desde_horas(horas_regulares: Decimal | float) -> Decimal:
    """El FTE que implican unas horas regulares.

    La fórmula de `CLAUDE.md` §18.4 —FTE = horas regulares / horas del mes—, que
    hasta hoy no tenía de dónde sacar el divisor.
    """
    return Decimal(str(horas_regulares)) / HORAS_MES


def cierra_la_jornada(horas: dict[str, Decimal | float],
                      fte: Decimal | float = 1) -> tuple[bool, Decimal]:
    """¿Las tres cuentas de la jornada suman el mes de esta posición?

    Devuelve `(cierra, diferencia)`. La diferencia es lo que sobra (positivo) o
    lo que falta (negativo) contra `240 × FTE`.

    Se AVISA, no se bloquea: puede haber un caso real que el sistema no conozca,
    y el dueño del dato es el owner. Pero se avisa siempre — una posición que no
    cierra es un dato del que no se puede sacar ni el FTE ni el costo por hora.
    """
    total = sum((Decimal(str(horas.get(c, 0) or 0))
                 for c in CUENTAS_DE_LA_JORNADA), Decimal("0"))
    dif = total - horas_del_mes(fte)
    return abs(dif) <= TOLERANCIA, dif
