# -*- coding: utf-8 -*-
"""Cómo se llama una cuenta contable, para mostrarla.

Owner, 2026-09-03, sobre «Property x Cuenta»: *«sin nombre el GL y el texto se
sobrepone en los datos»*. Dos problemas distintos en el mismo cuadro.

## 1. El nombre que trae varios nombres pegados

`account_mapping.account_name_example` es —como dice su nombre— una columna de
EJEMPLOS, y fue acumulando cada variante que apareció en el mayor:

    8040 -> "DEPRECIATION1 | DEPRECIATION2 | DEPRECIATION4 | DEPRECIATION"
    8015 -> "PROPERTY INSURANCE1 | ... | PROPERTY INSURANCE5"
    8000 -> "RENT1 | RENT"

Sirve para rastrear de dónde salió una regla. **No sirve como rótulo**: son 60
caracteres donde caben 20, y por eso el texto se montaba encima de los montos.

Los sufijos numéricos (`RENT1`, `OWNERS FEE1`) son de la codificación del
mayor, no del nombre de la cuenta.

⚠️ **No se elige “el primero”.** El primero suele ser el que TIENE sufijo
—`DEPRECIATION1`—; el bueno es el que no lo tiene. Cuando ninguno está limpio
(`PROPERTY INSURANCE1..5`), se le quita el número al más corto.

## 2. La cuenta sin nombre

`nonop_entries` guarda `account_name` **vacío en todas sus filas** (medido en
producción: las 18, en los tres escenarios). Por eso el 8000 y el 8020 salían
como número pelado.

El respaldo es el catálogo, que sí los tiene: 8000 es RENT y 8020 es CAPITAL
RESERVE.
"""
from __future__ import annotations

import re

#: Un nombre que termina en dígitos: `RENT1`, `DEPRECIATION4`.
_SUFIJO = re.compile(r"\d+$")


def limpiar_nombre(crudo: str | None) -> str:
    """Un nombre presentable a partir de la columna de ejemplos.

    >>> limpiar_nombre("DEPRECIATION1 | DEPRECIATION2 | DEPRECIATION")
    'DEPRECIATION'
    >>> limpiar_nombre("PROPERTY INSURANCE1 | PROPERTY INSURANCE5")
    'PROPERTY INSURANCE'
    >>> limpiar_nombre("OWNERS FEE1")
    'OWNERS FEE'
    >>> limpiar_nombre("")
    ''
    """
    if not crudo:
        return ""
    variantes = [v.strip() for v in str(crudo).split("|") if v.strip()]
    if not variantes:
        return ""
    # El que ya viene sin sufijo es el bueno; entre varios, el más corto.
    limpias = [v for v in variantes if not _SUFIJO.search(v)]
    if limpias:
        return min(limpias, key=len)
    # Ninguno está limpio: se le quita el número al más corto.
    return _SUFIJO.sub("", min(variantes, key=len)).strip()


def nombre_de_cuenta(
    codigo: str,
    propio: str | None = None,
    catalogo: dict | None = None,
    dept: str | None = None,
) -> str:
    """El nombre de una cuenta. **Nunca vacío.**

    El orden importa: primero lo que trajo el asiento —es el nombre con el que
    vino del mayor—, después el catálogo del departamento, después el del
    código a secas, y recién al final el número.

    `catalogo` es `{(dept, cuenta): nombre}` tal como lo arma
    `_catalogo_gl`; se acepta también `{cuenta: nombre}`.
    """
    limpio = limpiar_nombre(propio)
    if limpio:
        return limpio
    if catalogo:
        if dept is not None:
            limpio = limpiar_nombre(catalogo.get((dept, codigo)))
            if limpio:
                return limpio
        # Sin departamento, o el departamento no lo tiene: se busca el código
        # en cualquier departamento. Un 8040 se llama «Depreciation» en todos.
        for llave, valor in catalogo.items():
            cta = llave[1] if isinstance(llave, tuple) else llave
            if cta == codigo:
                limpio = limpiar_nombre(valor)
                if limpio:
                    return limpio
    from app.api.consulta_api import CONCEPTOS
    for _campo, cod, rotulo in CONCEPTOS:
        if cod == codigo:
            return rotulo
    return f"Cuenta {codigo}"
