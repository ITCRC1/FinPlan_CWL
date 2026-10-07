# -*- coding: utf-8 -*-
"""Lector del «Full Detail P&L» de Integrity — el Balance de Comprobacion.

Es el MAXIMO detalle que da el sistema contable: una fila por LINEA DE ASIENTO,
con la cuenta de siete segmentos, el texto que escribio quien lo registro y el
monto. Owner, 2026-10-05: *«este es el maximo detalle que tira el sistema de
contabilidad. Yo debo revisar linea por linea»*.

Forma del archivo
-----------------
- Varias hojas (`Detalle`, `Detalle (2)`, …): es UN reporte partido, no tres
  reportes. Se leen todas y se concatenan.
- Encabezado en la fila 6; arriba van compania, periodo y moneda.
- Entre los asientos hay filas de corte —«Cuenta 1000-…» y «Total 1000-…»— que
  NO son movimientos. Se reconocen porque la columna Cuenta no es un codigo
  completo de siete segmentos.

⚠️ **Los montos vienen en COLONES**, aunque el documento original sea en
dolares: el encabezado dice `Moneda: COL`. La columna `Moneda` es la del
documento y `T.C.` el tipo de cambio de ESA linea — con el se vuelve a dolares.
Confundirlos daria un reporte 450 veces mas grande.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from openpyxl import load_workbook

#: Un codigo completo: `4000-0110-001-001-001-09-01`.
CUENTA = re.compile(r"^\d{4}(?:-\w+){6}$")

COLUMNAS = ["cuenta", "asiento", "linea", "fecha", "descripcion", "desc_asiento",
            "origen", "referencia", "doc", "num_doc", "centro_costo", "tc",
            "moneda", "debito", "credito"]


@dataclass
class Linea:
    """Una linea de asiento, ya partida en lo que el motor necesita."""
    cuenta: str
    seg1: str            # clase + cuenta USALI: '4000', '5101', '6000', '7380'
    seg2: str            # departamento: '0110', '0220'
    seg3: str            # puesto (planilla) o detalle
    asiento: str
    linea: str
    fecha: str
    descripcion: str     # lo que escribio quien registro
    desc_asiento: str
    origen: str          # CXP, PLA, CON, FIJ, BAN…
    referencia: str      # el ARTICULO comprado, o el puesto en planilla
    num_doc: str
    tc: float
    #: La moneda de la TRANSACCION (`DOL` o `COL`), no la de la columna de
    #: montos. Vienen mezcladas: el archivo de setiembre 2026 trae 1.281
    #: renglones `DOL` y 3.497 `COL` — es en qué se pagó, no en qué está escrito.
    moneda: str
    debito: float
    credito: float
    #: En qué moneda están los MONTOS de este archivo, del encabezado
    #: (`Moneda: DOL` / `Moneda: COL`). Integrity exporta el mismo balance en
    #: las dos, y la diferencia no se ve mirando una fila: son los mismos
    #: asientos con la columna convertida.
    #:
    #: ⚠️ `COL` por defecto para no cambiarle el significado a nadie que
    #: construya una `Linea` a mano — era lo que se asumía antes de mirar el
    #: encabezado.
    moneda_archivo: str = "COL"

    @property
    def clase(self) -> str:
        return self.seg1[0]

    @property
    def _monto(self) -> float:
        return self.debito - self.credito

    @property
    def monto_crc(self) -> float:
        """El movimiento en COLONES, venga el archivo como venga.

        ⚠️ **Antes esto devolvía la columna cruda y la llamaba colones.** Con un
        export en dólares —que es lo que Integrity da si se le pide— el número
        salía rotulado `CRC` siendo dólares, y `monto_usd` dividía otra vez por
        el tipo de cambio: un gasto de 1.207,84 aparecía como US$2,63.

        No fallaba nada: la auditoría corría, los hallazgos eran correctos (las
        reglas comparan unos contra otros, no contra una escala) y sólo los
        MONTOS mentían. Owner, 2026-10-06: *«¿cómo hay que subir el archivo
        máximo detalle, en colones o en USD?»* — la respuesta tenía que ser
        «como lo tengas», y para eso hay que mirar el encabezado.
        """
        if (self.moneda_archivo or "").upper().startswith("DOL"):
            return self._monto * self.tc
        return self._monto

    @property
    def monto_usd(self) -> float:
        if (self.moneda_archivo or "").upper().startswith("DOL"):
            return self._monto
        return self._monto / self.tc if self.tc else 0.0


@dataclass
class Archivo:
    lineas: list[Linea] = field(default_factory=list)
    titulo: str = ""
    periodo: str = ""
    moneda: str = ""
    hojas: list[str] = field(default_factory=list)
    descartadas: int = 0
    #: Lineas que ya venian en otra hoja del mismo libro y NO se volvieron a
    #: contar. Viaja en la respuesta porque es un dato del archivo, no un
    #: detalle del lector: el owner tiene que saber que su export repite.
    repetidas: int = 0

    @property
    def anio_mes(self) -> tuple[int, int] | None:
        """`(2026, 9)` a partir de «Setiembre - 2026». `None` si no se entiende.

        Vive acá y no en quien llama porque el período es un dato del ARCHIVO:
        el día que Integrity lo escriba distinto, se arregla en un solo lugar.

        ⚠️ Devuelve `None` en vez de adivinar. Guardar el mayor de setiembre
        como si fuera otro mes es peor que no guardarlo: el mes bueno se
        quedaría sin su libro y el malo mostraría asientos que no son suyos.
        """
        return _anio_mes(self.periodo)


#: Los doce meses como los escribe Integrity, y las dos formas de setiembre:
#: el archivo del owner dice «Setiembre» y el castellano general «Septiembre».
#: Las dos tienen que valer o el libro de un mes entero se pierde por una letra.
_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "setiembre": 9, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}


def _anio_mes(periodo: str) -> tuple[int, int] | None:
    texto = (periodo or "").lower()
    mes = next((n for nombre, n in _MESES.items() if nombre in texto), None)
    anio = re.search(r"(20\d{2})", texto)
    if mes is None or not anio:
        return None
    return int(anio.group(1)), mes


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def leer(contenido: bytes) -> Archivo:
    """Todas las hojas del reporte, concatenadas, sin las filas de corte y **sin
    repetir una linea que ya vino en otra hoja**.

    ⚠️ **Un export de Integrity puede traer la misma linea en varias hojas.**
    Medido sobre `Full Detail P&L September 2026.xlsx` (owner, 2026-10-06): tres
    hojas —`Detalle`, `Detalle (2)`, `Detalle (3)`— con 4.565, 2.330 y 1.957
    lineas. Las dos ultimas **no aportan ni una linea nueva**: estan contenidas
    enteras en la primera. Concatenando salian 8.852 lineas donde hay 4.565, o
    sea **4.287 de mas**, y el debito del mes daba 1.092 millones de colones en
    vez de 815 — **277 millones contados dos y tres veces**.

    No fallaba nada. El archivo se leia, la auditoria corria y daba hallazgos
    reales; solo que sobre un libro inflado. Es el modo de falla de siempre en
    este repo: la plata esta mal y los totales cuadran consigo mismos.

    La llave es `(cuenta, asiento, linea, debito, credito)`, que es lo que
    identifica un renglon del mayor: un asiento no tiene dos veces la misma
    linea para la misma cuenta. Lo que se descarta se CUENTA y se informa, en
    vez de desaparecer en silencio.
    """
    wb = load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
    out = Archivo(hojas=list(wb.sheetnames))
    vistas: set[tuple] = set()
    for i, nombre in enumerate(wb.sheetnames):
        ws = wb[nombre]
        for fila in ws.iter_rows(values_only=True):
            celdas = list(fila) + [None] * (len(COLUMNAS) - len(fila))
            cta = _s(celdas[0])
            # La cabecera son las primeras filas de la PRIMERA hoja. Cada una
            # se mira por su cuenta: condicionar el bloque a que el titulo
            # siga vacio dejaba periodo y moneda sin leer, porque el titulo
            # es la primera que aparece y de ahi en adelante nunca mas se
            # entraba.
            if i == 0 and cta and not CUENTA.match(cta):
                # Las cuatro lineas de cabecera, en orden.
                if cta.lower().startswith("balance"):
                    out.titulo = cta
                elif cta.lower().startswith("moneda"):
                    out.moneda = cta.split(":", 1)[-1].strip()
                elif not out.periodo and "-" in cta and len(cta) < 40 \
                        and not cta.lower().startswith(("compa", "cuenta", "total")):
                    out.periodo = cta
            if not CUENTA.match(cta):
                if cta:
                    out.descartadas += 1
                continue
            p = cta.split("-")
            # La llave de un renglon del mayor. Si ya vino en otra hoja, no se
            # vuelve a contar — ver el porque en el docstring.
            llave = (cta, _s(celdas[1]), _s(celdas[2]),
                     _f(celdas[13]), _f(celdas[14]))
            if llave in vistas:
                out.repetidas += 1
                continue
            vistas.add(llave)
            out.lineas.append(Linea(
                cuenta=cta, seg1=p[0], seg2=p[1], seg3=p[2],
                asiento=_s(celdas[1]), linea=_s(celdas[2]), fecha=_s(celdas[3]),
                descripcion=_s(celdas[4]), desc_asiento=_s(celdas[5]),
                origen=_s(celdas[6]), referencia=_s(celdas[7]),
                num_doc=_s(celdas[9]), tc=_f(celdas[11]), moneda=_s(celdas[12]),
                debito=_f(celdas[13]), credito=_f(celdas[14]),
                moneda_archivo=out.moneda or "COL"))
    return out
