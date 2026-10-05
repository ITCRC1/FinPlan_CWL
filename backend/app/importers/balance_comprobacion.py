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
    moneda: str
    debito: float
    credito: float

    @property
    def clase(self) -> str:
        return self.seg1[0]

    @property
    def monto_crc(self) -> float:
        return self.debito - self.credito

    @property
    def monto_usd(self) -> float:
        return self.monto_crc / self.tc if self.tc else 0.0


@dataclass
class Archivo:
    lineas: list[Linea] = field(default_factory=list)
    titulo: str = ""
    periodo: str = ""
    moneda: str = ""
    hojas: list[str] = field(default_factory=list)
    descartadas: int = 0


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def leer(contenido: bytes) -> Archivo:
    """Todas las hojas del reporte, concatenadas, sin las filas de corte."""
    wb = load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
    out = Archivo(hojas=list(wb.sheetnames))
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
            out.lineas.append(Linea(
                cuenta=cta, seg1=p[0], seg2=p[1], seg3=p[2],
                asiento=_s(celdas[1]), linea=_s(celdas[2]), fecha=_s(celdas[3]),
                descripcion=_s(celdas[4]), desc_asiento=_s(celdas[5]),
                origen=_s(celdas[6]), referencia=_s(celdas[7]),
                num_doc=_s(celdas[9]), tc=_f(celdas[11]), moneda=_s(celdas[12]),
                debito=_f(celdas[13]), credito=_f(celdas[14])))
    return out
