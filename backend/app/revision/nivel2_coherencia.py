# -*- coding: utf-8 -*-
"""Nivel 2 · coherencia interna — ¿el archivo se contradice a sí mismo?

Todo lo de acá se comprueba **con el propio archivo**, sin preguntarle nada al
resto del sistema. Son las contradicciones que hoy nadie mira porque el total
sigue cuadrando: el subdetalle que no suma su padre, el reparto que no cierra en
cero, el ingreso que viene negativo.

Puro: recibe las filas ya traducidas, no toca la base.
"""
from __future__ import annotations

from decimal import Decimal

from app.revision.hallazgo import hallazgo

ZERO = Decimal("0")
NIVEL = 2

#: Debajo de esto es redondeo, no descuadre. Un dólar — la misma tolerancia que
#: usa `recalculate.TOLERANCIA_FINO` para decidir entre detalle y resumen.
TOLERANCIA = Decimal("1")


def filas_con_monto_y_sin_cuenta(sin_cuenta: list[dict], tc) -> list:
    """Plata sin número de cuenta.

    **El caso que ya costó $40.613.** En el Actual 2024, dos renglones del gasto
    de Habitaciones venían sin código y el importador los descartaba en
    silencio; el P&L siguió cuadrando consigo mismo y el descuadre apareció
    meses después, al compararlo contra el auxiliar.
    """
    conmonto = [x for x in sin_cuenta if x["monto_crc"]]
    if not conmonto:
        return []
    tc = Decimal(str(tc))
    total = sum((x["monto_crc"] for x in conmonto), ZERO) / tc
    return [hallazgo(
        "fila_sin_cuenta",
        "Filas con monto y sin número de cuenta",
        "critico",
        f"{len(conmonto)} filas traen plata sin código de cuenta: "
        + ", ".join(f"fila {x['fila']} ({x['texto'][:26]})" for x in conmonto[:6]),
        porque="Sin el código no se sabe a qué línea del P&L va, así que la fila "
               "no se carga. Así se perdieron $40.613 del gasto de Habitaciones "
               "en el Actual 2024, y el descuadre apareció meses después.",
        que_hacer="Ponerle la cuenta en Integrity y volver a subir el mes.",
        monto=total, nivel=NIVEL,
        referencias=[{"fila": x["fila"], "texto": x["texto"]} for x in conmonto])]


def subdetalle_que_no_suma_su_padre(filas: list[dict], subdetalle: dict) -> list:
    """El movimiento no suma el total del departamento.

    El libro asume que la cuenta de dos segmentos (`4000-0110`) es el total de
    sus movimientos (`4000-0110-001`, `-002`…). Si no lo es, o el padre está mal
    o falta un movimiento — y como sólo se carga el padre, la diferencia entra al
    P&L sin que nada la señale.
    """
    padres = {f["cuenta"]: f for f in filas}
    difs = []
    for padre, suma_hijos in subdetalle.items():
        p = padres.get(padre)
        if p is None:
            continue
        d = Decimal(str(p["mes_usd"])) - Decimal(str(suma_hijos))
        if abs(d) > TOLERANCIA:
            difs.append({"cuenta": padre, "padre": float(p["mes_usd"]),
                         "hijos": float(suma_hijos), "diferencia": float(d),
                         "fila": p["fila"]})
    if not difs:
        return []
    total = sum((Decimal(str(x["diferencia"])) for x in difs), ZERO)
    difs.sort(key=lambda x: -abs(x["diferencia"]))
    return [hallazgo(
        "subdetalle_no_suma",
        "El detalle no suma el total de su cuenta",
        "aviso",
        f"{len(difs)} cuentas donde el padre y sus movimientos no coinciden: "
        + ", ".join(f"{x['cuenta']} {x['diferencia']:+,.2f}" for x in difs[:6]),
        porque="Sólo se carga la cuenta de dos segmentos. Si su detalle no la "
               "suma, la diferencia entra al P&L y nada la señala.",
        que_hacer="Revisar en Integrity si falta un movimiento o si el total "
                  "quedó mal.",
        monto=total, nivel=NIVEL, referencias=difs)]


def allocation_que_no_netea(filas: list[dict], fuentes: set) -> list:
    """Un departamento de reparto tiene que quedar en CERO.

    ⚠️ La primera versión de este chequeo pedía que las cuentas `4999` netearan
    entre sí, y estaba mal: en julio 2026 hay dos —lavandería y cafetería— y las
    **dos son negativas**. Su contrapartida no es otra `4999`, es el gasto que
    aparece en los departamentos que consumen el servicio.

    Lo que sí es invariante: un departamento de reparto **distribuye todo su
    costo**, así que su neto es cero. Verificado en julio: `0161` da −0,00
    exacto (planilla + suministros = 3.081,28, y el `4999` se lo lleva entero).

    `fuentes` son los departamentos marcados `is_allocation_source` en el
    catálogo — hoy `0220` (comida de empleados) y `0161` (lavandería).
    """
    if not fuentes:
        return []
    neto_por_depto: dict[str, Decimal] = {}
    for f in filas:
        if f["destino_finplan"] in fuentes:
            neto_por_depto[f["destino_finplan"]] = (
                neto_por_depto.get(f["destino_finplan"], ZERO)
                + Decimal(str(f["mes_usd"])))
    abiertos = {d: v for d, v in neto_por_depto.items() if abs(v) > TOLERANCIA}
    if not abiertos:
        return []
    total = sum(abiertos.values(), ZERO)
    return [hallazgo(
        "allocation_no_netea",
        "Un departamento de reparto no quedó en cero",
        "critico",
        ", ".join(f"{d} quedó en {float(v):+,.2f}" for d, v in sorted(abiertos.items())),
        porque="Un departamento de reparto distribuye TODO su costo a los que "
               "consumen el servicio, así que tiene que cerrar en cero. Si le "
               "sobra, ese gasto se quedó sin repartir y ningún total lo muestra "
               "— el efecto se diluye entre los demás departamentos.",
        que_hacer="Revisar la cuenta 4999 de ese departamento en Integrity: la "
                  "distribución no cubre todo el gasto del mes.",
        monto=total, nivel=NIVEL,
        referencias=[{"depto": d, "neto": float(v)} for d, v in sorted(abiertos.items())])]


#: Cuentas donde un monto negativo es lo NORMAL y no una anomalía.
#:
#: `8060` es el impuesto de renta: en un mes con pérdida es un crédito, y da
#: negativo por definición. En julio 2026 son −40.364,12. Reportarlo haría que el
#: hallazgo apareciera todos los meses malos, con el monto más grande de la
#: lista, tapando los que sí importan — y una lista así se aprende a ignorar.
CUENTAS_QUE_PUEDEN_SER_NEGATIVAS = {8060}


def signo_contrario_a_su_clase(filas: list[dict]) -> list:
    """Un ingreso negativo o un gasto negativo.

    Puede ser legítimo —una nota de crédito, un ajuste— o un signo mal puesto.
    Las dos cosas se ven igual en el total, así que se reportan y decide quien
    sabe.
    """
    raros = []
    for f in filas:
        v = Decimal(str(f["mes_usd"]))
        if not v:
            continue
        cat = f["categoria"]
        if cat == "Allocation":
            continue          # su signo es justamente el del reparto
        if f["cuenta_base"] in CUENTAS_QUE_PUEDEN_SER_NEGATIVAS:
            continue
        # Después de normalizar el signo, POSITIVO es lo esperado en las dos
        # clases: un ingreso suma ingreso y un gasto suma gasto. Negativo es la
        # anomalía en ambas —una nota de crédito, una reversión, o un signo mal
        # puesto—, así que la condición es una sola y no dos.
        if v < ZERO:
            raros.append({"fila": f["fila"], "cuenta": f["cuenta"],
                          "nombre": f["descripcion"][:40],
                          "categoria": cat, "monto": float(v)})
    if not raros:
        return []
    raros.sort(key=lambda x: x["monto"])
    total = sum((Decimal(str(x["monto"])) for x in raros), ZERO)
    return [hallazgo(
        "signo_contrario",
        "Montos con el signo contrario al de su clase",
        "aviso",
        f"{len(raros)} filas: "
        + ", ".join(f"{x['cuenta']} {x['monto']:,.2f} ({x['categoria']})"
                    for x in raros[:6]),
        porque="Una nota de crédito legítima y un signo mal puesto se ven igual "
               "en el total.",
        que_hacer="Confirmar cada una. Si es un ajuste, está bien; si es un "
                  "error de posteo, corregirlo y volver a subir.",
        monto=total, nivel=NIVEL, referencias=raros)]


def acumulado_no_cierra(filas: list[dict], acumulado_anterior: dict) -> list:
    """`acumulado(este mes) − acumulado(mes anterior)` tiene que dar el mes.

    Las dos columnas vienen de Integrity y son independientes. Si no cierran, el
    archivo se contradice a sí mismo — y hoy nadie lo mira. `acumulado_anterior`
    es `{(cuenta_base, depto): monto}` del pre-cierre del mes previo.
    """
    if not acumulado_anterior:
        return []
    difs = []
    for f in filas:
        k = (f["cuenta_base"], f["depto"])
        previo = Decimal(str(acumulado_anterior.get(k, 0)))
        esperado = Decimal(str(f["acumulado_usd"])) - previo
        d = esperado - Decimal(str(f["mes_usd"]))
        if abs(d) > TOLERANCIA:
            difs.append({"fila": f["fila"], "cuenta": f["cuenta"],
                         "mes": float(f["mes_usd"]),
                         "por_acumulado": float(esperado),
                         "diferencia": float(d)})
    if not difs:
        return []
    difs.sort(key=lambda x: -abs(x["diferencia"]))
    total = sum((Decimal(str(x["diferencia"])) for x in difs), ZERO)
    return [hallazgo(
        "acumulado_no_cierra",
        "El acumulado no coincide con el mes",
        "aviso",
        f"{len(difs)} cuentas donde el acumulado menos el del mes anterior no da "
        f"el movimiento del mes: "
        + ", ".join(f"{x['cuenta']} {x['diferencia']:+,.2f}" for x in difs[:6]),
        porque="Las dos columnas vienen de Integrity y son independientes. Si no "
               "cierran, o se reabrió un mes anterior o el movimiento del mes "
               "está mal.",
        que_hacer="Revisar si hubo un asiento con fecha de un mes ya cerrado.",
        monto=total, nivel=NIVEL, referencias=difs)]


def revisar(filas: list[dict], *, tc, sin_cuenta=None, subdetalle=None,
            acumulado_anterior=None, fuentes_de_reparto=None) -> list:
    """Los cinco chequeos del nivel."""
    out = []
    out += filas_con_monto_y_sin_cuenta(sin_cuenta or [], tc)
    out += subdetalle_que_no_suma_su_padre(filas, subdetalle or {})
    out += allocation_que_no_netea(filas, fuentes_de_reparto or set())
    out += signo_contrario_a_su_clase(filas)
    out += acumulado_no_cierra(filas, acumulado_anterior or {})
    return out
