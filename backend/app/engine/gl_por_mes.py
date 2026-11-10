# -*- coding: utf-8 -*-
"""Cuentas del mayor por mes, y la conciliación contra el P&L.

Owner, 2026-11-05, mostrando el mismo reporte de otra app: *«que lo pongas en
el tab Reports al final para poder conciliar los resultados… y que traiga todas
las cuentas… y que exista un proceso de validación interno para que pegue con
los reportes»*.

## La convención de signo, que es el corazón del reporte

En el mayor de Integrity el ingreso es un **crédito**: va negativo. **En
FinPlan se guarda positivo.** Para que valga la propiedad que hace útil al
reporte —**Σ de todas las filas = la utilidad cambiada de signo**— hay que dar
vuelta el ingreso al mostrarlo.

## ⚠️ Y el ingreso NO es «la cuenta empieza con 4»

Ése fue mi primer intento y daba una diferencia de **180.817,68** contra el
P&L de ACTUAL 2026. El número tenía una firma: era **exactamente el doble** de
90.408,84, y un factor dos aparece cuando una partida se resta de un lado y se
suma del otro. Eran estas dos:

    0161  4900  Distribución   −18.852,40  → OH_LAUNDRY    [OVERHEAD EXPENSES]
    0220  4901  Distribución   −71.556,43  → OH_CAFETERIA  [OVERHEAD EXPENSES]
                               ───────────
                               −90.408,84   × 2 = 180.817,68

Son clase 4, pero **no son ingreso**: son el crédito con que el reparto deja a
lavandería y cafetería en cero, y el P&L las manda a overhead. Es lo que dice
el CLAUDE.md —«la cuenta 4xxx Distribución se excluye del revenue»— y lo que
la conciliación encontró sola.

**Entonces manda la SECCIÓN del P&L donde cae la cuenta, no su primer dígito.**
Es crédito si, y sólo si, su línea del P&L vive en `REVENUES`. Con esa regla la
igualdad cierra al centavo.

Cuando una cuenta no tiene mapeo no hay sección, y ahí sí se cae al primer
dígito — es lo único que queda, y la fila sale marcada `DROP` para que el tab
de validación la muestre: es plata del mayor que el P&L no ve.

## Por qué el signo se decide ACÁ y en un solo lugar

Porque la suma tiene que dar lo mismo en la grilla, en el resumen, en el Excel
y en la validación. Cuatro lugares invirtiendo por su cuenta es la forma
conocida de que tres queden iguales y el cuarto no, y el cuarto sea justo el
que decide si «cuadra» ([[las-noches-disponibles-se-calculan-en-seis-lugares]]).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable, Iterable, Sequence

ZERO = Decimal("0")

#: Los doce meses, con el mismo nombre y orden que `ActualEntry`, `OpexEntry` y
#: `CostEntry`. Quien recorra cualquiera de ellas lo hace igual.
MESES = ("jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec")

#: La ÚNICA sección de ingreso del reporte. Lo que cae acá es crédito.
SECCION_INGRESO = "REVENUES"

#: Sección del P&L → categoría del reporte. Las dos secciones de costo se
#: juntan, y todo lo que vive debajo del GOP cae en una sola.
SECCION_A_CATEGORIA: dict[str, str] = {
    "REVENUES": "REVENUE",
    "COST OF SALES": "COST_OF_SALES",
    "OVERHEAD COST OF SALES": "COST_OF_SALES",
    "OPERATING EXPENSES": "_GASTO",          # se abre en planilla vs opex
    "OVERHEAD EXPENSES": "_GASTO",
    "OWNER / NON-OP EXPENSES": "BELOW_GOP",
    "CAPITAL": "BELOW_GOP",
    "FINANCIAL EXPENSES": "BELOW_GOP",
    "DEPRECIATION": "BELOW_GOP",
    "TAX / NET PROFIT": "BELOW_GOP",
}

#: Primer dígito → categoría, para cuando NO hay mapeo que consultar.
CLASE_A_CATEGORIA: dict[str, str] = {
    "4": "REVENUE", "5": "COST_OF_SALES", "6": "PAYROLL",
    "7": "OPERATING_EXPENSES", "8": "BELOW_GOP", "9": "STATISTICS",
}

#: Prefijo de las cuentas de REPARTO (allocation). Es el crédito con que
#: lavandería y cafetería quedan en cero: `4999` en el catálogo de CWL, y
#: `4900`/`4901` en el mayor del ACTUAL 2026. Sólo se usa cuando la cuenta no
#: tiene mapeo — teniéndolo, manda la sección.
PREFIJO_REPARTO = "49"

#: Orden de presentación del resumen. Los repartos van DESPUÉS del gasto y
#: antes de lo que vive bajo el GOP: ahí es donde el P&L los deja.
ORDEN_CATEGORIAS = ("REVENUE", "COST_OF_SALES", "PAYROLL",
                    "OPERATING_EXPENSES", "ALLOCATIONS", "BELOW_GOP",
                    "OTHER", "STATISTICS")

#: No entran en la suma: las 9xxx son cantidades (noches, kilos, covers), no
#: plata. Meterlas rompería la igualdad con la utilidad sin que nada avise.
NO_SUMAN = ("STATISTICS",)


def clase_de(account_code: str) -> str:
    """El primer dígito de la cuenta — la clase USALI."""
    return (account_code or "").strip()[:1]


def categoria_de(account_code: str, seccion_pl: str | None = None) -> str:
    """La categoría de la fila.

    Manda la sección del P&L cuando la hay; el primer dígito es el último
    recurso. Dentro de las dos secciones de gasto se separa la planilla por
    clase, porque el P&L no las distingue y el reporte sí tiene que hacerlo.
    """
    clase = clase_de(account_code)
    sec = (seccion_pl or "").strip().upper()

    # ⚠️ REPARTOS, antes que nada. Una cuenta clase 4 que el P&L NO manda a
    # ingreso no es ingreso: es el crédito con que lavandería y cafetería
    # quedan en cero (CLAUDE.md: «la cuenta 4xxx Distribución se excluye del
    # revenue»). Mezclarla con el gasto de verdad —que es donde cae hoy, por
    # su sección de overhead— esconde el reparto dentro del gasto operativo y
    # hace que el gasto de un departamento no se pueda leer solo.
    #
    # El signo NO cambia y la fila SIGUE sumando: la igualdad que sostiene el
    # reporte (Σ filas = −utilidad) sólo depende de `es_credito`, que no se
    # toca acá. Esto es cómo se AGRUPA, no cuánto vale.
    if clase == "4" and (
            (sec and sec != SECCION_INGRESO)
            or (not sec and (account_code or "").strip().startswith(PREFIJO_REPARTO))):
        return "ALLOCATIONS"

    cat = SECCION_A_CATEGORIA.get(sec)
    if cat == "_GASTO":
        return "PAYROLL" if clase == "6" else "OPERATING_EXPENSES"
    if cat:
        return cat
    return CLASE_A_CATEGORIA.get(clase, "OTHER")


def es_credito(account_code: str, seccion_pl: str | None = None) -> bool:
    """¿Esta fila se muestra con el signo dado vuelta?

    ⚠️ Sólo si su línea del P&L vive en `REVENUES`. Sin mapeo se cae al primer
    dígito, que es lo único que queda — y esa fila sale marcada `DROP`.
    """
    sec = (seccion_pl or "").strip().upper()
    if sec:
        return sec == SECCION_INGRESO
    return clase_de(account_code) == "4"


def nombre_de_cuenta(ejemplo: str | None) -> str:
    """El nombre limpio, de la columna de EJEMPLOS del mapeo.

    `account_name_example` guarda, separados por `|`, los nombres con que esa
    cuenta aparece en el mayor -- que suelen ser el mismo con un número
    pegado, porque Integrity numera las variantes:

        RENT1 | RENT                                    -> RENT
        DEPRECIATION1 | DEPRECIATION2 | DEPRECIATION    -> DEPRECIATION
        PROPERTY INSURANCE1 | ... | PROPERTY INSURANCE5 -> PROPERTY INSURANCE

    Volcar la lista entera en la celda la vuelve ilegible. Se prefiere la
    variante SIN número; si todas lo tienen, se le quitan los dígitos del final
    a la primera -- que es de donde salía el número, no parte del nombre.
    """
    partes = [t.strip() for t in str(ejemplo or "").split("|") if t.strip()]
    if not partes:
        return ""
    for t in partes:
        if not t[-1].isdigit():
            return t
    return partes[0].rstrip("0123456789").strip()


def ancla_contable(mapeos: Iterable[dict]) -> dict[str, tuple[str, str, str]]:
    """Línea del P&L → la cuenta y el departamento donde se contabiliza.

    Owner, 2026-11-10: *«asigna cuenta y asigna departamento, realiza la liga
    contable al checkbook»*.

    ## Por qué hace falta un ancla y no basta con «abrir la línea»

    El checkbook de ingresos guarda **un monto por línea del P&L** -- la tabla
    es `(scenario, line)`, sin departamento ni cuenta -- porque el ingreso se
    arma de tarifas y noches, no de asientos. Y abrir esa línea en sus cuentas
    es imposible sin inventar el reparto: medido sobre el mapeo real de CWL,
    **sólo 3 de las 19 líneas de ingreso tienen una única cuenta**; REV_ROOMS
    tiene tres (0110, 0115, 0116) y REV_MISC_OTHER nueve. Repartir un total
    entre nueve cuentas sin una base es fabricar detalle.

    Lo que sí se puede, y es lo que el owner pidió: **asignarle a cada línea su
    cuenta y su departamento**, el asiento donde esa plata se contabiliza. El
    monto no se toca ni se parte; se le pone domicilio contable.

    El ancla sale del mismo `account_mapping` que usa el P&L -- no de una lista
    nueva que se desincronice -- y se elige de forma determinista: la cuenta
    más baja de la línea y, dentro de ella, el departamento más bajo. Para
    REV_ROOMS eso da `0110 / 4000`, que es el asiento principal.

    ⚠️ **Esto NO cambia cómo se calcula el P&L.** El motor sigue sembrando el
    ingreso por línea, igual que antes. El ancla es para el reporte del mayor:
    hace que el ingreso aparezca con cuenta y departamento, y que la suma de la
    grilla vuelva a dar la utilidad. Mover el cálculo a pasar por cuentas sería
    otra cosa y movería plata; esto no mueve un centavo.
    """
    por_linea: dict[str, tuple[str, str, str]] = {}
    for m in mapeos:
        linea = str(m.get("report_line_code") or "")
        cuenta = str(m.get("account_code") or "").strip()
        dept = str(m.get("dept_code") or "").strip()
        if not linea or not cuenta:
            continue
        nombre = nombre_de_cuenta(m.get("account_name_example"))
        clave = (cuenta, dept)
        actual = por_linea.get(linea)
        if actual is None or clave < (actual[1], actual[0]):
            por_linea[linea] = (dept, cuenta, nombre)
    return por_linea


def es_reparto(account_code: str) -> bool:
    """¿Es una cuenta de reparto conocida? (`49xx`.)"""
    return (account_code or "").strip().startswith(PREFIJO_REPARTO)


def discrepa_clase(account_code: str, *, credito: bool, seccion_pl: str | None) -> bool:
    """Clase 4 que el P&L NO trata como ingreso, y que NO es un reparto conocido.

    ⚠️ Antes esto marcaba también a las «Distribución», y el tab de validación
    tenía que aclarar al lado que esas dos estaban bien. Una alarma que viene
    con su propia excusa no es una alarma: enseña a ignorarla. Ahora los
    repartos tienen su propia categoría y la bandera queda para lo que de
    verdad no se espera -- una TERCERA cuenta clase 4 cayendo en gasto.

    Estaba escrita igual en `armar_grilla` y en `gl_api._fila`; vive acá para
    que no se arreglen de a una.
    """
    if not (seccion_pl or "").strip():
        return False
    if es_reparto(account_code):
        return False
    return (clase_de(account_code) == "4") != credito


def _d(v) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if v is None or v == "":
        return ZERO
    return Decimal(str(v))


def con_signo_de_reporte(monto, *, credito: bool) -> Decimal:
    """El monto como lo muestra el reporte: el ingreso, negativo.

    ⚠️ **Una sola puerta.** La grilla, el resumen, el Excel y la validación
    pasan todos por acá.
    """
    m = _d(monto)
    return -m if credito else m


def armar_grilla(
    filas: Iterable[dict],
    *,
    resolver: Callable[[str, str], tuple[dict | None, str]] | None = None,
    seccion_de_linea: Callable[[str], str] | None = None,
    nombre_dept: Callable[[str], str] | None = None,
    corporativo: Callable[[str, str], str] | None = None,
) -> list[dict]:
    """Una fila del reporte por (departamento × cuenta), con sus doce meses.

    `filas` trae dicts con `dept_code`, `account_code`, `account_name` y los
    doce meses — la forma de `ActualEntry`, que es también la que sale de
    pivotar `checkbook_account_rows_for_month`.

    `resolver` es el de `pl_engine.construir_resolvedor`: devuelve la regla de
    mapeo y **cómo** la encontró. El cómo se guarda porque es la mitad del
    valor del reporte: `DROP` es plata del mayor que el P&L no ve, y `FALLBACK`
    es un mapeo que puede moverse solo.
    """
    salida: list[dict] = []
    for f in filas:
        cuenta = str(f.get("account_code") or "").strip()
        dept = str(f.get("dept_code") or "").strip()
        if not cuenta:
            continue

        linea_code = linea_nombre = seccion = ""
        como = "DROP"
        if resolver is not None:
            regla, como = resolver(dept, cuenta)
            if regla:
                linea_code = str(regla.get("report_line_code") or "")
                linea_nombre = str(regla.get("report_line_name") or "")
                if seccion_de_linea is not None:
                    seccion = seccion_de_linea(linea_code) or ""

        credito = es_credito(cuenta, seccion)
        meses = [con_signo_de_reporte(f.get(m), credito=credito) for m in MESES]
        clase = clase_de(cuenta)
        categoria = categoria_de(cuenta, seccion)

        salida.append({
            "dept_code": dept,
            "dept_name": (nombre_dept(dept) if nombre_dept else "") or dept,
            "account_code": cuenta,
            "account_name": str(f.get("account_name") or "").strip(),
            "outlet": str(f.get("outlet") or "").strip(),
            "clase": clase,
            # La columna que el owner pidió: a qué renglón del P&L va a parar.
            # Es la llave de la conciliación, no un adorno.
            "pl_line_code": linea_code,
            "pl_line_name": linea_nombre,
            "pl_section": seccion,
            "mapeo": como,
            # El código corporativo de la otra app. Vacío hasta que exista la
            # tabla de equivalencias; la columna ya viaja para que el día que
            # se cargue no haya que tocar la pantalla ni el Excel.
            "codigo_corporativo": (corporativo(dept, cuenta) if corporativo else ""),
            "categoria": categoria,
            # Clase 4 que NO es ingreso (o al revés). No es un error: las dos
            # «Distribución» del reparto son exactamente esto. Se marca para
            # que el tab de validación las muestre en vez de esconderlas.
            "clase_discrepa": discrepa_clase(cuenta, credito=credito,
                                             seccion_pl=seccion),
            "meses": meses,
            "total": sum(meses, ZERO),
        })
    salida.sort(key=lambda r: (r["categoria"] == "STATISTICS", r["account_code"],
                               r["dept_code"], r["outlet"]))
    return salida


def resumen_por_categoria(grilla: Sequence[dict]) -> list[dict]:
    """Una fila por categoría, con sus doce meses y el total.

    Cierra con `NET`, que es la suma de todo lo que sí suma. Con el ingreso en
    negativo, `NET` es **la utilidad cambiada de signo**.
    """
    por_cat: dict[str, list[Decimal]] = {}
    for r in grilla:
        acc = por_cat.setdefault(r["categoria"], [ZERO] * 12)
        for i, v in enumerate(r["meses"]):
            acc[i] += v

    filas = []
    for cat in ORDEN_CATEGORIAS:
        if cat not in por_cat:
            continue
        meses = por_cat[cat]
        filas.append({"categoria": cat, "meses": meses, "total": sum(meses, ZERO),
                      "suma": cat not in NO_SUMAN})

    neto = [ZERO] * 12
    for f in filas:
        if f["suma"]:
            for i, v in enumerate(f["meses"]):
                neto[i] += v
    filas.append({"categoria": "NET", "meses": neto, "total": sum(neto, ZERO),
                  "suma": True})
    return filas


def total_del_reporte(grilla: Sequence[dict]) -> Decimal:
    """Σ de todas las filas que suman. Debe ser **−utilidad**."""
    return sum((r["total"] for r in grilla if r["categoria"] not in NO_SUMAN), ZERO)


def conciliar(
    grilla: Sequence[dict],
    *,
    utilidad_pl: Decimal,
    por_linea_pl: dict[str, Decimal] | None = None,
    suma_gl_por_linea: dict[str, Decimal] | None = None,
    comparables: set[str] | None = None,
    secciones: dict[str, str] | None = None,
    tolerancia: Decimal = Decimal("0.01"),
) -> dict:
    """El proceso de validación interno: ¿esto pega con los reportes?

    La prueba fuerte es una sola: **Σ de todas las filas = −utilidad del P&L**.
    Si cierra, cada peso del mayor llegó a un renglón del reporte.

    Si no cierra, las otras dicen dónde mirar:

    1. **Cuentas sin mapeo (`DROP`)** — están en el mayor y no llegan al P&L.
       Es la causa número uno. En el Pre-Cierre de 2026 era exactamente eso:
       una sola cuenta, `0250 8050 OTHER OWNERS' EXPENSES`, y sus 529,21 eran
       toda la diferencia.
    2. **Cuentas por `FALLBACK`** — llegan, pero por descarte. No rompe hoy; el
       día que aparezca una segunda regla la plata se mueve de renglón sola.
    3. **Clase contra sección** — una cuenta 4xxx que el P&L trata como gasto.
       Las dos «Distribución» del reparto son esto y están bien; una tercera
       merece una mirada.

    ## La comparación renglón por renglón

    ⚠️ **Sólo contra las líneas MAPEADAS**, y la lista la pone el llamador en
    `comparables`. No alcanza con sacar las CALCULATED del catálogo: el motor
    emite además líneas que **no están en la configuración** (`GOP`,
    `EBITDA_BEFORE`, `EBITDA_AFTER`). Si se comparan, salen con el mayor en
    cero y una diferencia igual a todo el renglón — ruido que tapa las
    diferencias de verdad.

    ⚠️ Y **el ingreso hay que ponerlo en la misma vara**: la grilla lo tiene
    negativo y el P&L positivo. Se mira la SECCIÓN del renglón, no el signo del
    número: adivinar por el signo da el doble del monto cada vez que un gasto
    resulta negativo, que es justo lo que pasó con `INCOME_TAXES`.

    ⚠️ `suma_gl_por_linea` viene de afuera porque el mapeo **cambia a mitad de
    año**: la 7120 dejó `OH_ADMIN` en jul-2026. Sumar por el renglón que la
    fila muestra hoy le carga a `OH_ADMIN` los doce meses y la diferencia que
    aparece es el monto entero de la cuenta — una alarma falsa sobre un P&L
    que está bien.
    """
    total = total_del_reporte(grilla)
    esperado = -_d(utilidad_pl)
    diferencia = total - esperado

    sin_mapeo = [r for r in grilla if r["mapeo"] == "DROP"
                 and r["categoria"] not in NO_SUMAN]
    por_descarte = [r for r in grilla if r["mapeo"] == "FALLBACK"]
    discrepan = [r for r in grilla if r.get("clase_discrepa")]

    def _resumen(rs):
        return [{"dept_code": r["dept_code"], "account_code": r["account_code"],
                 "account_name": r["account_name"], "total": r["total"],
                 "pl_line_code": r["pl_line_code"], "pl_section": r["pl_section"]}
                for r in sorted(rs, key=lambda x: -abs(x["total"]))]

    lineas = []
    if por_linea_pl is not None:
        secs = secciones or {}
        suma_gl = dict(suma_gl_por_linea or {})
        if suma_gl_por_linea is None:
            for r in grilla:
                if r["categoria"] in NO_SUMAN or not r["pl_line_code"]:
                    continue
                suma_gl[r["pl_line_code"]] = (
                    suma_gl.get(r["pl_line_code"], ZERO) + r["total"])
        codigos = set(suma_gl) | set(por_linea_pl)
        if comparables is not None:
            codigos &= comparables
        for code in sorted(codigos):
            gl = suma_gl.get(code, ZERO)
            pl = _d(por_linea_pl.get(code, ZERO))
            # Misma vara: el ingreso de la grilla va negativo, el del P&L no.
            gl_comparable = -gl if (secs.get(code, "").strip().upper()
                                    == SECCION_INGRESO) else gl
            lineas.append({"pl_line_code": code, "gl": gl_comparable, "pl": pl,
                           "diferencia": gl_comparable - pl})

    return {
        "total_reporte": total,
        "utilidad_pl": _d(utilidad_pl),
        "esperado": esperado,
        "diferencia": diferencia,
        "cuadra": abs(diferencia) <= tolerancia,
        "tolerancia": tolerancia,
        "sin_mapeo": _resumen(sin_mapeo),
        "sin_mapeo_total": sum((r["total"] for r in sin_mapeo), ZERO),
        "por_descarte": _resumen(por_descarte),
        "por_descarte_total": sum((r["total"] for r in por_descarte), ZERO),
        "clase_discrepa": _resumen(discrepan),
        "clase_discrepa_total": sum((r["total"] for r in discrepan), ZERO),
        "por_linea": lineas,
    }
