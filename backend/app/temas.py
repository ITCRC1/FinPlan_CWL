# -*- coding: utf-8 -*-
"""Las paletas visuales que existen.

⚠️ **Esta lista y la de `frontend/lib/tema.ts` son LA MISMA lista.** Si acá se
acepta un tema que el CSS no define, el usuario lo guarda, la pantalla no cambia
y nadie encuentra por qué. `tests/test_temas.py` falla si se separan.

Los colores viven en `frontend/app/globals.css`; acá solo está cuál es válido.
El backend no sabe de colores, igual que no sabe de traducciones.
"""
from __future__ import annotations

TEMAS: tuple[str, ...] = ("lino", "papel", "grafito", "hoy")

#: Con cuál abre quien nunca eligió (owner, 2026-08-19).
TEMA_POR_DEFECTO = "lino"
