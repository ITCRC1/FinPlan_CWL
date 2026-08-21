# -*- coding: utf-8 -*-
"""La VERIFICACIÓN que viaja arriba del archivo de actuales.

Owner, 2026-08-16 — y es el requisito que destraba clonar propiedades:

    «Necesito que el upload de los resultados tenga la verificación arriba
    versus el detalle abajo. Sobre todo para las nuevas propiedades, que tengo
    que subir los actuales. Para Corcovado no hay problema, pero para las
    otras, que debo empezar desde cero, sí ocupo esa validación — o al menos
    algunas cuentas de control básico: ingresos, GOP, EBITDA y net profit. Así
    el sistema consolida el detalle y valida que estos resultados hagan match.»

## Por qué va EN LA PUERTA

En Corcovado hay tres años cargados: si algo entra mal, se nota comparando. En
una propiedad nueva **no hay contra qué comparar**. El archivo entra, el P&L
sale, cuadra consigo mismo, y nadie se entera hasta meses después. Es el modo de
falla que este sistema ya tuvo tres veces en agosto — el total cuadra y la plata
está en otro lado. Por eso la comparación va al subir, no en un reporte después.

## Por BUCKET, nunca línea por línea

Medido el 2026-08-16: **34 de las 106 líneas del reporte no existen en el
vocabulario del Resumen** (todos los `COS_*`, `COH_*`, `REV_FB_BEV`,
`OH_CAFETERIA`, `OH_LAUNDRY`, `FINANCIAL_LOSSES`…). Un validador por línea daría
26–28 rojas por escenario **sin un solo error real**, y el owner dejaría de
mirarlo en una semana. Por bucket, el `ACTUAL 2025`, el `ACTUAL 2026` y el
`FORECAST Working 2026` dan cero.

Así que los controles son los **totales**, no las líneas: los ocho buckets del
corte natural (ingresos · gasto operativo · overhead · no operativo · capital ·
financieros · depreciación · impuesto) más los tres escalones de la cascada que
el owner lee (GOP, EBITDA, utilidad neta).

## Qué bloquea y qué avisa

**Bloquean los cuatro que pidió el owner**: ingresos totales, GOP, EBITDA y
utilidad neta. Los demás **avisan**: son el desglose que explica DÓNDE está la
diferencia, y una diferencia de presentación adentro de un bucket que cuadra no
tiene por qué frenar una carga.

## El impuesto va en su propia sección

Es la única línea donde una diferencia puede significar «se subió una provisión
que los libros todavía no tienen» en vez de «el dato está mal». Mezclarlo hace
que el `FORECAST April 2026` se vea roto cuando su GOP y su EBT cuadran exactos
(los dos forecast 2026 reportan $17.881,10 y $2.473,73 de diferencia neta, y toda
es del impuesto).

Por eso hay una regla explícita: **si toda la diferencia de la utilidad neta se
explica por la del impuesto, la utilidad neta baja de bloqueo a aviso** y lo
dice. No se esconde la diferencia — se dice de qué es.

⚠️ Este módulo es PURO: no toca la base ni escribe nada. La verificación es un
**control**, no un origen: ni un centavo de lo que trae puede terminar sumando en
el P&L. Si lo hiciera, sería exactamente el problema que se está cerrando.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

#: Un dólar. Es el mismo umbral con el que `recalculate._el_detalle_cuadra`
#: decide si dos caminos cuentan la misma plata: por debajo es redondeo.
TOLERANCIA = Decimal("1")

ZERO = Decimal("0")


@dataclass(frozen=True)
class Control:
    codigo: str        #: lo que se escribe en la columna «Código» de la hoja
    etiqueta: str      #: cómo se lee en la hoja
    line_code: str     #: la línea del reporte contra la que se compara
    seccion: str       #: "control" · "desglose" · "impuesto"
    bloquea: bool
    alias: tuple[str, ...] = field(default=())


#: El orden es el de la CASCADA del P&L: ingresos, lo que se le resta, el
#: escalón que resulta, y así hasta la utilidad neta. Se lee de arriba abajo
#: como el estado de resultados, que es como el owner lo revisa.
#:
#: ⚠️ Son ONCE filas y entran EXACTAS en las doce que quedan libres arriba del
#: encabezado del Detalle (fila 13 = título, 14 = meses, 15 = versiones). Agregar
#: una fila más obliga a mover el encabezado, y esas dos filas están cableadas en
#: el parser (`MONTH_ROW`, `VERSION_ROW`) y en todos los archivos que el owner ya
#: tiene. Antes de sumar un control, leer eso.
CONTROLES: tuple[Control, ...] = (
    Control("VER_INGRESOS", "Ingresos totales", "TOTAL_REVENUES", "control", True,
            ("ingresos", "ingresos_totales", "total_ingresos", "total_revenues",
             "revenue", "revenues", "total_revenue")),
    Control("VER_GASTO_OPERATIVO", "Gasto operativo (departamentos)",
            "TOTAL_OPERATING_EXPENSES", "desglose", False,
            ("gasto_operativo", "gastos_operativos", "total_operating_expenses",
             "operating_expenses", "opex")),
    Control("VER_OVERHEAD", "Overhead", "TOTAL_OVERHEAD_EXPENSES", "desglose", False,
            ("overhead", "gastos_generales", "total_overhead_expenses",
             "overhead_expenses")),
    Control("VER_GOP", "GOP", "TOTAL_GOP", "control", True,
            ("gop", "total_gop", "gross_operating_profit")),
    Control("VER_NO_OPERATIVO", "No operativo (renta, fees, seguros)",
            "TOTAL_NON_OP_EXPENSES", "desglose", False,
            ("no_operativo", "gastos_no_operativos", "total_non_op_expenses",
             "non_op_expenses", "non_operating")),
    Control("VER_EBITDA", "EBITDA", "EBITDA_BEFORE_CAPITAL", "control", True,
            ("ebitda", "ebitda_before_capital", "ebitda_antes_de_capital")),
    Control("VER_CAPITAL", "Capital (reserva + capex)", "CAPITAL_EXPENSE",
            "desglose", False,
            ("capital", "capital_expense", "capex", "gasto_de_capital")),
    Control("VER_FINANCIEROS", "Financieros", "FINANCIAL_EXPENSES", "desglose", False,
            ("financieros", "gastos_financieros", "financial_expenses")),
    Control("VER_DEPRECIACION", "Depreciación", "TOTAL_DEPRECIATIONS", "desglose", False,
            ("depreciacion", "depreciaciones", "total_depreciations", "depreciation")),
    Control("VER_IMPUESTO", "Impuesto de renta", "INCOME_TAXES", "impuesto", False,
            ("impuesto", "impuestos", "impuesto_de_renta", "renta", "income_taxes",
             "income_tax")),
    Control("VER_UTILIDAD_NETA", "Utilidad neta", "NET_PROFIT", "control", True,
            ("utilidad_neta", "neto", "net", "net_profit", "utilidad")),
)

POR_CODIGO: dict[str, Control] = {c.codigo: c for c in CONTROLES}

#: Los cuatro que pidió el owner. Se nombran acá para que quien lea el archivo
#: no tenga que deducirlos del campo `bloquea`.
LOS_CUATRO_DEL_OWNER = tuple(c.codigo for c in CONTROLES if c.bloquea)


def _norm(texto) -> str:
    """Minúsculas, sin tildes y con un solo separador. Para poder reconocer el
    control aunque el owner lo escriba «Utilidad Neta», «UTILIDAD_NETA» o
    «Utilidad neta:»."""
    s = str(texto or "").strip().lower()
    s = "".join(ch for ch in unicodedata.normalize("NFD", s)
                if unicodedata.category(ch) != "Mn")
    fuera = []
    for ch in s:
        fuera.append(ch if ch.isalnum() else "_")
    return "_".join(p for p in "".join(fuera).split("_") if p)


_ALIAS: dict[str, str] = {}
for _c in CONTROLES:
    _ALIAS[_norm(_c.codigo)] = _c.codigo
    _ALIAS[_norm(_c.etiqueta)] = _c.codigo
    for _a in _c.alias:
        _ALIAS[_norm(_a)] = _c.codigo


def codigo_de_verificacion(texto) -> str | None:
    """El control que nombra esta celda, o None.

    Se reconoce por **contenido exacto normalizado**, nunca por posición ni por
    subcadena. Que sea exacto importa: una cuenta de detalle que se llame
    «Otros ingresos» no puede convertirse por accidente en el control de
    ingresos, porque entonces su plata desaparecería del mayor.
    """
    if texto is None:
        return None
    return _ALIAS.get(_norm(texto))


def meses_comparables(tipo: str, actuals_through: int | None) -> tuple[list[int], list[int]]:
    """(meses que SÍ se comparan, meses que NO y por qué no).

    ⚠️ **Un forecast toma sus meses cerrados del Actual enlazado, no de sí
    mismo** (`_compute_pl_month_core`). Comparar los doce meses mide meses que
    el reporte no usa: es exactamente lo que hizo creer que el `Working 2026`
    estaba desalineado cuando no lo estaba.
    """
    corte = int(actuals_through or 0)
    if str(tipo or "").upper() == "FORECAST" and corte > 0:
        return list(range(corte + 1, 13)), list(range(1, corte + 1))
    return list(range(1, 13)), []


def _dec(v) -> Decimal:
    if v is None:
        return ZERO
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def comparar(verificacion: dict, consolidado: dict, meses: list[int],
             meses_omitidos: list[int] | None = None,
             tolerancia: Decimal | float = TOLERANCIA) -> dict:
    """Compara el bloque de arriba contra el detalle ya consolidado.

    verificacion : {codigo_control: {mes: monto}} — lo que dice el archivo.
    consolidado  : {mes: {line_code: monto}} — lo que da el detalle por el motor.
    meses        : los meses que el reporte SÍ toma de este archivo.

    **Una celda vacía no se compara.** Es lo que permite subir una propiedad
    nueva mes a mes, o dejar los meses cerrados de un forecast en blanco: lo que
    no se declara no se controla, y lo que se declara se controla al dólar.
    """
    tol = _dec(tolerancia)
    meses = sorted(meses)
    omitidos = sorted(meses_omitidos or [])

    lineas = []
    dif_por_codigo: dict[str, Decimal] = {}
    for c in CONTROLES:
        del_archivo = {int(m): _dec(v) for m, v in (verificacion.get(c.codigo) or {}).items()}
        comparables = [m for m in meses if m in del_archivo]
        if not comparables:
            continue
        por_mes = []
        for m in comparables:
            arch = del_archivo[m]
            det = _dec((consolidado.get(m) or {}).get(c.line_code))
            dif = det - arch
            por_mes.append({"mes": m, "archivo": float(arch), "detalle": float(det),
                            "dif": float(dif), "cuadra": abs(dif) <= tol})
        anual_arch = sum((d["archivo"] for d in por_mes), 0.0)
        anual_det = sum((d["detalle"] for d in por_mes), 0.0)
        dif_anual = _dec(anual_det) - _dec(anual_arch)
        dif_por_codigo[c.codigo] = dif_anual
        malos = [d for d in por_mes if not d["cuadra"]]
        lineas.append({
            "codigo": c.codigo, "etiqueta": c.etiqueta, "seccion": c.seccion,
            "line_code": c.line_code, "bloquea": c.bloquea,
            "meses_comparados": comparables,
            "archivo": round(anual_arch, 2), "detalle": round(anual_det, 2),
            "dif": round(float(dif_anual), 2),
            "cuadra": abs(dif_anual) <= tol and not malos,
            "meses_que_no_cuadran": malos,
            "nota": "",
        })

    # ── El impuesto no puede hacer ver rota a la utilidad neta ────────────────
    #
    # NET = EBT − IMPUESTO. Si el EBT cuadra y el impuesto no, toda la
    # diferencia neta ES la del impuesto — y eso NO significa que el detalle
    # esté mal: significa que se subió una provisión que los libros todavía no
    # tienen (o al revés). Los dos Forecast 2026 son exactamente ese caso.
    #
    # Se dice, no se esconde: la fila sigue marcada como que no cuadra, pero
    # deja de bloquear y explica de qué es la diferencia.
    d_net = dif_por_codigo.get("VER_UTILIDAD_NETA")
    d_imp = dif_por_codigo.get("VER_IMPUESTO")
    if d_net is not None and d_imp is not None and abs(d_net) > tol and abs(d_imp) > tol \
            and abs(d_net + d_imp) <= tol:
        for L in lineas:
            if L["codigo"] == "VER_UTILIDAD_NETA":
                L["bloquea"] = False
                L["nota"] = ("Toda la diferencia de la utilidad neta es la del impuesto "
                             f"({float(d_imp):,.2f}). El resultado antes de impuesto cuadra: "
                             "no es un dato mal cargado, es una provisión distinta.")

    bloqueantes = [L for L in lineas if L["bloquea"] and not L["cuadra"]]
    avisos = [L for L in lineas if not L["bloquea"] and not L["cuadra"]]
    return {
        "hay_verificacion": bool(lineas),
        "cuadra": not bloqueantes and not avisos,
        "bloquea": bool(bloqueantes),
        "tolerancia": float(tol),
        "meses_comparados": meses,
        "meses_no_comparados": omitidos,
        "motivo_meses_no_comparados": (
            "Son meses cerrados: el forecast los toma del Actual enlazado, no de este "
            "archivo. Compararlos mediría meses que el reporte no usa."
            if omitidos else ""),
        "lineas": lineas,
        "bloqueantes": [L["codigo"] for L in bloqueantes],
        "avisos": [L["codigo"] for L in avisos],
    }


def resumen_texto(rep: dict, etiqueta_bloque: str = "") -> str:
    """El informe en una cadena, para el mensaje de error del upload.

    El error ES el reporte: el owner tiene que poder decidir sin abrir otra
    pantalla, así que dice bucket, mes, lo que declaró, lo que dio el detalle y
    la diferencia.
    """
    partes = []
    if etiqueta_bloque:
        partes.append(f"Bloque «{etiqueta_bloque}»")
    for L in rep.get("lineas", []):
        if L["cuadra"]:
            continue
        marca = "BLOQUEA" if L["bloquea"] else "aviso"
        partes.append(
            f"[{marca}] {L['etiqueta']}: el archivo declara {L['archivo']:,.2f} y el "
            f"detalle consolida {L['detalle']:,.2f} — diferencia {L['dif']:,.2f}."
            + (f" {L['nota']}" if L["nota"] else "")
        )
        for d in L["meses_que_no_cuadran"]:
            partes.append(
                f"    · mes {d['mes']:02d}: archivo {d['archivo']:,.2f} · "
                f"detalle {d['detalle']:,.2f} · dif {d['dif']:,.2f}")
    if rep.get("meses_no_comparados"):
        partes.append("No se compararon los meses "
                      + ", ".join(f"{m:02d}" for m in rep["meses_no_comparados"])
                      + ": " + rep.get("motivo_meses_no_comparados", ""))
    return "\n".join(partes)
