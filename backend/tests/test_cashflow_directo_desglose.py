# -*- coding: utf-8 -*-
"""El desglose del tab de Proveedores tiene que sumar SU PROPIO total.

El bloque «A. COSTO DEVENGADO DEL MES» existe para explicar de dónde sale
`TOTAL COSTO DEVENGADO`. Ese total no se calcula sumando las filas: sale de
TOTAL_OPEXP + TOTAL_OVERHEAD + TOTAL_NON_OP del P&L, igual que el flujo
indirecto —y así tiene que ser, porque es lo que hace que los dos métodos
concilien.

El precio de esa independencia es que las dos mitades pueden separarse **sin
que falle nada**: la caja sigue bien, la conciliación sigue dando $0.02, y la
lista queda corta. Pasó: faltaban los bloques de Cost of Sales (`COS_*`,
`COH_*`) y el desglose estaba $418,982 por debajo de su total —el 10.6% del
costo del año del Budget 2027.

Es el mismo defecto que se corrigió en `pl_api` el 2026-08-14 para la pantalla
del P&L. Se repitió acá porque cada pantalla tenía su copia de la regla.
"""
import inspect

from app.api import cashflow_directo_api as cfd
from app.api.pl_api import _pl_component


class _L:
    def __init__(self, code, sec, dept=None):
        self.line_code, self.section, self.dept_code = code, sec, dept


# Las familias que el P&L emite del lado del costo, con la sección con la que
# viajan. Si mañana aparece otra, agregarla acá es parte de agregarla al P&L.
COSTO = [
    ("OPEX_ROOMS", "OPERATING EXPENSES"),
    ("OPEXP_ROOMS", "OPEXP"),
    ("COS_FB_FOOD", "COST OF SALES"),
    ("COS_FB_BEV", "COST OF SALES"),
    ("COS_LAUNDRY", "COST OF SALES"),
    ("OH_ADMIN", "OVERHEAD EXPENSES"),
    ("OVH_ADMIN", "OVERHEAD"),
    ("COH_CAFETERIA", "OVERHEAD COST OF SALES"),
]


def test_toda_linea_de_costo_entra_al_desglose():
    """Ninguna familia de costo puede quedar fuera de la lista."""
    for code, sec in COSTO:
        ln = _L(code, sec)
        assert _pl_component(ln, "OPEX") or _pl_component(ln, "OVERHEAD"), (
            f"{code} ({sec}) no lo reconoce ningún lado del clasificador: su "
            f"monto entraría al TOTAL del tab y no a las filas que lo explican")


def test_el_cost_of_sales_esta_en_el_lado_correcto():
    """`COS_` es operativo y `COH_` es overhead — no al revés, o el subtotal
    de cada bloque se movería aunque el gran total siguiera cuadrando."""
    assert _pl_component(_L("COS_FB_FOOD", "COST OF SALES"), "OPEX")
    assert not _pl_component(_L("COS_FB_FOOD", "COST OF SALES"), "OVERHEAD")
    assert _pl_component(_L("COH_CAFETERIA", "OVERHEAD COST OF SALES"), "OVERHEAD")
    assert not _pl_component(_L("COH_CAFETERIA", "OVERHEAD COST OF SALES"), "OPEX")


def test_no_entran_los_totales_ni_las_utilidades():
    """Si un TOTAL_ o un PROFIT_ se colara como fila, el desglose duplicaría
    el costo entero y ninguna otra prueba lo vería."""
    for code, sec in (("TOTAL_OPEXP", "OPEXP"),
                      ("TOTAL_OVERHEAD", "OVERHEAD EXPENSES"),
                      ("PROFIT_ROOMS", "OPERATING PROFIT"),
                      ("OPPROFIT_ROOMS", "OP_PROFIT")):
        ln = _L(code, sec)
        assert not (_pl_component(ln, "OPEX") or _pl_component(ln, "OVERHEAD")), \
            f"{code} no puede aparecer como fila del desglose"


def test_los_gastos_de_propiedad_siguen_yendo_a_su_rama():
    """El bloque below-GOP se muestra en UNA línea («Gastos de propiedad») y su
    detalle vive en otro tab. Si el clasificador se los tragara, saldrían dos
    veces: una en la lista y otra dentro de esa línea."""
    for code, sec in (("RENT", "OWNER / NON-OP EXPENSES"),
                      ("MGMT_FEE_3", "OWNER / NON-OP EXPENSES"),
                      ("OTHER_EXPENSES", "OWNER / NON-OP EXPENSES"),
                      ("PROPERTY_INSURANCE", "OWNER / NON-OP EXPENSES"),
                      ("CAPITAL_EXPENSE", "CAPITAL EXPENSES")):
        ln = _L(code, sec)
        assert not (_pl_component(ln, "OPEX") or _pl_component(ln, "OVERHEAD")), \
            f"{code} tiene su propia rama en _lines_from_pl; contarlo acá lo duplica"


def test_no_vuelve_a_haber_una_lista_de_prefijos_propia():
    """La regla vive en `_pl_component` y en ningún otro lado.

    Las dos copias ya se desincronizaron una vez —`pl_api` sumó `COS_` en
    agosto y esta pantalla no— así que la que quedó tiene que seguir siendo
    una sola.
    """
    src = inspect.getsource(cfd._lines_from_pl)
    cuerpo = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    assert "_pl_component" in cuerpo, \
        "_lines_from_pl dejó de usar el clasificador canónico"
    # `"OH_"` sigue apareciendo a proposito en `etiqueta()`: ahi NO clasifica, le
    # pone el sufijo << (overhead) >> al nombre repetido. Lo que no puede volver
    # es una lista propia que decida QUIEN ENTRA, y `"OPEX_"` solo servia a eso.
    assert '"OPEX_"' not in cuerpo, \
        ("volvió a haber una lista de prefijos propia en _lines_from_pl: "
         "usar _pl_component, que ya sabe de COS_ y COH_")
    etiquetado = cuerpo.count('"OH_"')
    assert etiquetado <= 1,         (f'"OH_" aparece {etiquetado} veces; solo se admite la de `etiqueta()`, '
         "que rotula el nombre repetido: clasificar es trabajo de _pl_component")
