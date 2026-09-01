# -*- coding: utf-8 -*-
"""Lee el estado de resultados CRUDO de Integrity — la hoja `Final`.

## Qué es este archivo

Lo que Integrity entrega cada mes: una hoja `Final` con el mayor del período.
**Del sistema baja sólo hasta la columna U.** Todo lo que está a la derecha en el
libro del owner —el signo, el tipo de cambio, el departamento, la división y la
categoría USALI— lo agrega él a mano, mes a mes, con fórmulas.

Este módulo es esas fórmulas. Cada función lleva en su docstring **la fórmula de
Excel que reemplaza**, copiada del libro (`Conc JUL 2026.xlsx`, julio 2026), para
que la equivalencia se pueda verificar leyendo, no confiando.

## Por qué es puro

No toca la base, no escribe nada, no sabe qué es un escenario. Recibe bytes y
devuelve filas. Eso es lo que permite probarlo con casos armados a mano y correr
la prueba de oro —julio 2026, que ya está cerrado y validado— sin levantar nada.

## Las dos trampas

⚠️ **El subdetalle NO se mapea.** Una cuenta de Integrity viene en tres niveles:
`4000` (clase), `4000-0110` (clase + departamento) y `4000-0110-001` (el
movimiento). El libro mapea **sólo las de dos segmentos**: son el total del
departamento, y las de tres ya están sumadas adentro. Contar las tres cuenta la
plata tres veces. Es la razón de ser de `cuenta_base()`.

⚠️ **El signo de los ingresos viene invertido.** En el mayor un ingreso es un
crédito y baja negativo, salvo `4999`, que son las contrapartidas de allocation y
ya vienen con el signo que corresponde.
"""
from __future__ import annotations

from decimal import Decimal

#: El nombre de la hoja que entrega Integrity.
HOJA = "Final"

#: Los encabezados que tiene que traer, y con los que se ubican las columnas.
#: Se buscan POR TEXTO y no por letra: si Integrity mueve una columna, esto falla
#: diciendo qué no encontró en vez de leer la de al lado en silencio.
ENCABEZADOS = {"cuenta": "Cuenta", "descripcion": "Descripción",
               "mes": "Mes Actual", "acumulado": "Acumulado"}

#: Primer dígito de la cuenta → categoría USALI.
CATEGORIA_POR_CLASE = {"4": "Ingresos", "5": "Costo de Ventas", "6": "Nómina",
                       "7": "Otros Gastos", "8": "No Operativo"}

#: La clase que son contrapartidas de reparto, no ingreso.
CLASE_ALLOCATION = "4999"

ZERO = Decimal("0")


def signo_de(cuenta: str) -> int:
    """Excel: ``IF(LEFT(D,4)="4999",1,IF(LEFT(D,1)="4",-1,1))``

    Un ingreso baja del mayor como crédito, o sea negativo, y hay que darlo
    vuelta para leerlo. `4999` es la excepción: son las contrapartidas de
    allocation, que ya vienen con el signo bueno — invertirlas haría que un
    reparto sumara en vez de restar y el total seguiría cuadrando.
    """
    c = (cuenta or "").strip()
    if c[:4] == CLASE_ALLOCATION:
        return 1
    return -1 if c[:1] == "4" else 1


def monto_mes(cuenta: str, mes_crudo, acumulado_crudo) -> Decimal:
    """Excel: ``signo * IF($U<0,-$R,$R)``  (columna X, «Mes ₡ con signo»)

    ⚠️ El signo del MES lo decide el ACUMULADO, no el mes. Integrity entrega la
    columna del mes en valor absoluto y la del acumulado con signo; sin mirar el
    acumulado, un ingreso y un gasto del mismo monto son indistinguibles.
    """
    r, u = _dec(mes_crudo), _dec(acumulado_crudo)
    return signo_de(cuenta) * (-r if u < ZERO else r)


def monto_acumulado(cuenta: str, acumulado_crudo) -> Decimal:
    """Excel: ``signo * $U``  (columna Y, «Acumulado ₡ con signo»)"""
    return signo_de(cuenta) * _dec(acumulado_crudo)


def a_dolares(monto_crc: Decimal, tc: Decimal) -> Decimal:
    """Excel: ``$X/$AD$11``  (columnas Z y AA)

    El TC **no tiene default**. Cambia todos los meses y es un dato del cierre,
    no una constante del sistema: inventarlo pondría todo el P&L a un tipo de
    cambio que nadie decidió, y cuadraría igual.
    """
    if tc is None or Decimal(str(tc)) <= ZERO:
        raise ValueError("El tipo de cambio es obligatorio y tiene que ser mayor que cero.")
    return monto_crc / Decimal(str(tc))


def cuenta_base(cuenta: str) -> int | None:
    """Excel: ``IF(AND($D<>"",LEN($D)-LEN(SUBSTITUTE($D,"-",""))=1),VALUE(LEFT($D,4)),"")``

    Devuelve la clase de cuenta **sólo para las filas de dos segmentos**
    (`4000-0110`). Para la clase sola (`4000`) y para el movimiento
    (`4000-0110-001`) devuelve `None`, que es lo que las deja fuera de los
    totales. Ver la trampa del subdetalle arriba.
    """
    c = (cuenta or "").strip()
    if not c or c.count("-") != 1:
        return None
    try:
        return int(c[:4])
    except ValueError:
        return None


def depto_de(cuenta: str) -> str:
    """Excel: ``MID($D,6,4)``  (columna AF)"""
    return "" if cuenta_base(cuenta) is None else (cuenta or "").strip()[5:9]


def categoria_usali(cuenta: str) -> str:
    """Excel: ``IF($AE=4999,"Allocation",IF(LEFT($D,1)="4","Ingresos", … ))``  (AH)"""
    if cuenta_base(cuenta) is None:
        return ""
    c = (cuenta or "").strip()
    if c[:4] == CLASE_ALLOCATION:
        return "Allocation"
    return CATEGORIA_POR_CLASE.get(c[:1], "")


def _dec(v) -> Decimal:
    """Un número sumable. Integrity entrega la columna como texto con separadores
    de miles y, a veces, el negativo entre paréntesis — el «convertir a números
    sumables y legibles» que hoy se pide a mano."""
    if v is None or v == "":
        return ZERO
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    s = str(v).strip().replace(" ", "").replace(" ", "")
    negativo = s.startswith("(") and s.endswith(")")
    if negativo:
        s = s[1:-1]
    s = s.replace("$", "").replace("₡", "").replace(",", "")
    if not s or s in ("-", "."):
        return ZERO
    try:
        d = Decimal(s)
    except Exception:
        return ZERO
    return -d if negativo else d


# ─── Lectura de la hoja ───────────────────────────────────────────────────────

class FormatoInesperado(ValueError):
    """La hoja no tiene la forma que este módulo sabe leer. El mensaje dice QUÉ
    faltó: es la diferencia entre arreglarlo en un minuto y abrir el Excel a
    adivinar."""


def _texto(v) -> str:
    return "" if v is None else str(v).strip()


def _parece_cuenta(v) -> bool:
    """`4000`, `4000-0110`, `4000-0110-001`. El formato de Integrity."""
    s = _texto(v)
    if not s:
        return False
    partes = s.split("-")
    return partes[0].isdigit() and len(partes[0]) == 4 and all(p.isdigit() for p in partes[1:])


def ubicar_encabezados(filas: list[tuple]) -> dict:
    """Dónde están las columnas, buscadas POR TEXTO.

    La fila de encabezados es la que trae «Mes Actual» y «Acumulado» juntos —en
    el archivo de julio 2026 es la 11, pero no se asume: si Integrity agrega un
    renglón de título, buscar por posición leería la columna equivocada y el
    total seguiría cuadrando.

    ⚠️ La columna de la CUENTA no se toma del encabezado. En el archivo real el
    rótulo «Cuenta» está en `C` y los códigos en `D` (celdas combinadas). Se
    detecta por CONTENIDO: la columna con más valores que parecen cuenta.
    """
    for i, fila in enumerate(filas):
        textos = {_texto(v).lower(): j for j, v in enumerate(fila)}
        col_mes = textos.get(ENCABEZADOS["mes"].lower())
        col_acum = textos.get(ENCABEZADOS["acumulado"].lower())
        if col_mes is None or col_acum is None:
            continue
        datos = filas[i + 1:]
        conteo: dict[int, int] = {}
        for f in datos:
            for j, v in enumerate(f):
                if _parece_cuenta(v):
                    conteo[j] = conteo.get(j, 0) + 1
        if not conteo:
            raise FormatoInesperado(
                f"Se encontró la fila de encabezados ({i + 1}) pero ninguna columna "
                f"trae códigos de cuenta con el formato de Integrity (`4000-0110`).")
        col_cuenta = max(conteo, key=lambda j: conteo[j])
        return {"fila_encabezado": i, "cuenta": col_cuenta, "mes": col_mes,
                "acumulado": col_acum,
                "descripcion": textos.get(ENCABEZADOS["descripcion"].lower())}
    raise FormatoInesperado(
        f"La hoja «{HOJA}» no trae una fila con «{ENCABEZADOS['mes']}» y "
        f"«{ENCABEZADOS['acumulado']}». ¿Es el estado de resultados de Integrity?")


def mapear_filas(filas: list[tuple], cols: dict, tc, puente: dict,
                 grupo_de=None) -> dict:
    """Las filas ya traducidas, más los departamentos que nadie mapeó.

    `puente` = {codigo_integrity: {nombre_integrity, destino_finplan}} — la
    semilla `seed_data/<HOTEL>/mapd_integrity.json`.

    `grupo_de(destino)` devuelve el grupo del P&L al que pertenece ese
    departamento **según FinPlan**, o `None` si el catálogo lo deja vacío a
    propósito (los departamentos que se abren POR CUENTA, como `280`
    Misceláneos). Cuando es `None` no se inventa un grupo: la línea la resuelve
    el mapeo de cuentas, y poner el fallback —`OTHER_OVERHEAD`— rotularía como
    overhead lo que en realidad es ingreso.

    ⚠️ **La clasificación no sale de este archivo, sale del catálogo de
    FinPlan.** El puente sólo traduce el CÓDIGO, porque los dos sistemas no
    comparten espacio de códigos: Integrity `0130` es el Restaurant Terra
    Kitchen y FinPlan `0130` es «Spa (gerencia)». Ver la nota de la semilla.

    Un departamento que no está en el puente **no se adivina**: va a `sin_mapeo`
    con su monto, para que se pueda decidir si es ruido o si falta media
    operación. Es la misma regla que el importador de Channel Mix aplica con los
    market codes sin canal.
    """
    tc = Decimal(str(tc)) if tc is not None else None
    salida, sin_mapeo = [], {}
    for n, f in enumerate(filas[cols["fila_encabezado"] + 1:], cols["fila_encabezado"] + 2):
        cuenta = _texto(f[cols["cuenta"]] if cols["cuenta"] < len(f) else "")
        if not _parece_cuenta(cuenta):
            continue
        base = cuenta_base(cuenta)
        if base is None:
            continue                      # clase sola o subdetalle: ya está sumado
        crudo_mes = f[cols["mes"]] if cols["mes"] < len(f) else None
        crudo_acum = f[cols["acumulado"]] if cols["acumulado"] < len(f) else None
        mes_crc = monto_mes(cuenta, crudo_mes, crudo_acum)
        acum_crc = monto_acumulado(cuenta, crudo_acum)
        depto = depto_de(cuenta)
        m = puente.get(depto)
        destino = (m or {}).get("destino_finplan", "")
        fila = {
            "fila": n,
            "cuenta": cuenta,
            "cuenta_base": base,
            "depto": depto,
            "descripcion": _texto(f[cols["descripcion"]]
                                  if cols["descripcion"] is not None
                                  and cols["descripcion"] < len(f) else ""),
            "categoria": categoria_usali(cuenta),
            "destino_finplan": destino,
            "grupo": (grupo_de(destino) if grupo_de and destino else None),
            "nombre_integrity": (m or {}).get("nombre_integrity", ""),
            "mes_crc": mes_crc,
            "acumulado_crc": acum_crc,
            "mes_usd": a_dolares(mes_crc, tc),
            "acumulado_usd": a_dolares(acum_crc, tc),
        }
        salida.append(fila)
        if m is None:
            acc = sin_mapeo.setdefault(depto, {"depto": depto, "mes_usd": ZERO,
                                               "cuentas": []})
            acc["mes_usd"] += fila["mes_usd"]
            acc["cuentas"].append(cuenta)
    return {"filas": salida,
            "sin_mapeo": sorted(sin_mapeo.values(), key=lambda x: -abs(x["mes_usd"]))}


def leer(data: bytes, tc, puente: dict, grupo_de=None) -> dict:
    """El archivo crudo de Integrity → filas traducidas. Es la puerta del módulo."""
    import io as _io
    import openpyxl
    if tc is None:
        raise ValueError("El tipo de cambio es obligatorio: no se deduce del archivo.")
    wb = openpyxl.load_workbook(_io.BytesIO(data), read_only=True, data_only=True)
    if HOJA not in wb.sheetnames:
        raise FormatoInesperado(
            f"El archivo no trae la hoja «{HOJA}». Trae: {', '.join(wb.sheetnames)}.")
    filas = list(wb[HOJA].iter_rows(values_only=True))
    cols = ubicar_encabezados(filas)
    return {**mapear_filas(filas, cols, tc, puente, grupo_de), "columnas": cols}
