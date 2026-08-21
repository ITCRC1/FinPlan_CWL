"""Checkbook de gastos por departamento: generar el Excel y leerlo de vuelta.

`build.py` y `read.py` llegaron como paquete aparte (owner, 18-ago-2026) y se
instalan **sin tocarles la lógica**: son la implementación de
`docs/CHECKBOOK_FORMATO.md`, están validados contra el archivo original del
owner (1.184 fórmulas, 0 errores) y cualquier retoque nuestro se despegaría de
esa especificación. Lo que se adapta a FinPlan es el router, no el motor.
"""
from app.checkbook.build import build, validar          # noqa: F401
from app.checkbook.read import leer                     # noqa: F401
