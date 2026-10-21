# -*- coding: utf-8 -*-
"""El 0162 es operativo: su costo de venta cuenta como gasto.

Owner, 2026-10-21, con el aviso amarillo en la pantalla de cierre: *«como
resuelvo esto»*.

    El GOP acumulado de este reporte ($733.802,62) no coincide con el del
    motor ($731.280,14): $2.522,48 de diferencia.

## Dos reglas que no se hablaban

El GOP se calcula por dos caminos que TIENEN que dar lo mismo:

* **por naturaleza** — ingreso menos las clases 5/6/7 (`gasto_por_clase_api`);
* **por departamento** — la suma de las líneas del P&L (`pl_engine`).

`gasto_por_clase_api` excluía el **0162 «Laundry Revenue»** del gasto, con su
propia justificación escrita: *«es la cara de venta del mismo servicio»*. El
motor lo contaba como operativo. Ninguno de los dos estaba equivocado en su
propio archivo, y por eso nadie lo vio: cada uno cuadraba consigo mismo.

## Quién tenía razón

CLAUDE.md §1, textual: *«el Laundry Services que vende afuera es OPERATIVO →
su ingreso(4) y costo de venta(5) SE QUEDAN»*. Y la regla oficial
—`ALLOCATION_EXCLUDE` en `gl_detail_importer`, blindada por
`test_gl_allocation.py`— **nunca tuvo el 0162**: sólo 0220 y 0161.

El argumento de la copia valía para el INGRESO —por eso existe
`FUSION_INGRESO`, que junta las dos caras de la venta en una sola línea— y no
para el costo.

## Medido antes de tocar nada

Los dos departamentos no se solapan ni en una clase:

    0161   clase 4 (el crédito de reparto) · 6 · 7    -> allocation
    0162   clase 4 (ingreso) · 5 (costo de venta)     -> operativo

Y la brecha ERA el 0162, entero:

    BUDGET 2026   0162 clase 5 = 3.262,98  ·  brecha anual = 3.262,98
    ACTUAL 2026   0162 clase 5 =   505,06  ·  brecha YTD   =   505,06

Después del arreglo, los dos caminos dan CERO en los doce meses de los dos
escenarios.

⚠️ Lo que esto NO cambia: el 0220 y el 0161 siguen fuera del gasto. Sacarlos
volvería a contar dos veces lo que ya viaja repartido en los departamentos que
lo consumen.
"""
import inspect

from app.api import gasto_por_clase_api as gpc
from app.importers import gl_detail_importer as gl


def test_el_0162_NO_se_excluye_del_gasto():
    """El costo de venta de lo que se factura afuera es gasto operativo."""
    assert "0162" not in gpc.EXCLUIR_DE_GASTO
    assert gpc.EXCLUIR_DE_GASTO == {"0220", "0161"}


def test_la_copia_NO_puede_crecer_mas_que_la_regla_oficial():
    """⚠️ La defensa de fondo, y la que habría evitado esto.

    `EXCLUIR_DE_GASTO` es una COPIA de `ALLOCATION_EXCLUDE` dicha de otra
    manera. Una copia que crece por su cuenta —aunque sea con una justificación
    razonable escrita al lado— separa los dos caminos del GOP en silencio: cada
    archivo sigue cuadrando consigo mismo y nadie lo nota.
    """
    oficial = set(gl.ALLOCATION_EXCLUDE)
    assert gpc.EXCLUIR_DE_GASTO <= oficial, (
        f"{gpc.EXCLUIR_DE_GASTO - oficial} se excluye del gasto pero NO está "
        f"en ALLOCATION_EXCLUDE, que es la regla oficial. Si de verdad "
        f"corresponde excluirlo, va en los dos lados o en ninguno.")


def test_el_0220_y_el_0161_SIGUEN_fuera():
    """El contrapeso: esto no es «sacar la regla», es sacarla de donde no iba.

    Sin esto, el arreglo se puede «lograr» vaciando el conjunto, y entonces el
    gasto de Cafetería y Lavandería se cuenta dos veces: una en su propio
    departamento y otra repartido en los que lo consumen.
    """
    assert "0220" in gpc.EXCLUIR_DE_GASTO
    assert "0161" in gpc.EXCLUIR_DE_GASTO


def test_el_ingreso_de_lavanderia_sigue_saliendo_en_UNA_linea():
    """`FUSION_INGRESO` es lo que resolvía el problema REAL de la copia: que la
    venta de lavandería saliera en dos filas según cómo quedó cargada. Eso vale
    para el ingreso y sigue en pie."""
    assert gpc.FUSION_INGRESO == {"0161": "0162"}
    fuente = inspect.getsource(gpc)
    assert "Solo en ingreso" in fuente or "**Solo en ingreso.**" in fuente


def test_el_motor_tiene_el_0162_como_departamento_OPERATIVO():
    """La otra mitad del acuerdo. Si el motor lo moviera a overhead o lo
    sacara, los dos caminos volverían a separarse por el otro lado."""
    from app.engine import pl_engine

    grupos = {k: v for k, v in vars(pl_engine).items()
              if isinstance(v, dict) and "LAUNDRY" in v}
    assert grupos, "no se encontró el mapa de departamentos operativos"
    mapa = next(iter(grupos.values()))
    assert mapa["LAUNDRY"] == ["0162"]
