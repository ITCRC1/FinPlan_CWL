# -*- coding: utf-8 -*-
"""EN PRE-CLOSING EL INGRESO SE VE LINEA POR LINEA.

Owner, 2026-09-10: *«los ingresos aca se deben ver individuales ya que es
revision»*.

El P&L Statement resume el ingreso en tres renglones —Rooms, F&B y **Other**—.
Para leer un resultado alcanza; para REVISAR un mes, no: «Other» junta Spa,
Tours, Gift Shop, Transporte, Lavanderia, Innoceana y el Sustainability Fee en
un solo numero, y ahi dos errores de signo contrario se cancelan. El mes se ve
bien y no lo esta. Ese es exactamente el defecto que la pantalla de revision
tiene que hacer imposible.

## Que se fija

1. En modo Pre-Cierre las filas del estado se ARMAN con las lineas de la
   seccion `REVENUES` que devuelve el motor — no con una lista escrita en el
   frontend, que se olvidaria de crecer justo cuando agreguen una linea nueva.
2. Los tres renglones agregados (`X_ROOMS`/`X_FB`/`X_OTHER`) salen del cuadro
   cuando el ingreso esta abierto: si se quedaran, la misma plata estaria dos
   veces y el cuadro no cerraria contra Total Revenue.
3. Fuera del Pre-Cierre no cambia NADA: el estado de resultados de siempre.
4. El Excel baja lo que se esta viendo (owner, 2026-08-27: *«el excel no baja
   lo que esta viendo»*), asi que el cuadro descargable lee las MISMAS filas.
"""
import io
import os
import re

RAIZ = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
PANTALLA = os.path.join(RAIZ, "app", "month-end", "pl", "Pantalla.tsx")


def _pantalla() -> str:
    return io.open(PANTALLA, encoding="utf-8").read()


def _memo() -> str:
    """El cuerpo del memo `filasEstado`."""
    src = _pantalla()
    i = src.index("const filasEstado = useMemo")
    j = src.index("}, [esPre, vA, vB]);", i)
    return src[i:j]


def test_el_ingreso_abierto_sale_del_motor():
    """Las lineas se leen de la respuesta, no de una lista escrita a mano."""
    cuerpo = _memo()
    assert 'l.section !== "REVENUES"' in cuerpo
    assert "c?.lines" in cuerpo
    # Y se saltan las cabeceras y el total, que no son lineas de ingreso.
    assert 'l.line_code.startsWith("SEC_")' in cuerpo
    assert 'l.line_code === "TOTAL_REVENUES"' in cuerpo
    # Ninguna linea REV_* escrita a mano: seria la segunda verdad.
    assert not re.search(r'"REV_[A-Z_]+"', cuerpo), \
        "las lineas de ingreso no se escriben en el frontend: salen del motor"


def test_los_tres_agregados_se_van_cuando_el_ingreso_se_abre():
    """Si «Other Revenue» se quedara, la plata estaria contada dos veces."""
    cuerpo = _memo()
    assert 'ESTADO.filter(f => !["X_ROOMS", "X_FB", "X_OTHER"].includes(f.code))' in cuerpo


def test_fuera_del_precierre_el_estado_no_cambia():
    """El P&L de verdad se dibuja igual que siempre."""
    cuerpo = _memo()
    assert "if (!esPre) return ESTADO;" in cuerpo
    # Y si todavia no llegaron datos, tampoco se inventa un cuadro vacio.
    assert "if (!lineas.size) return ESTADO;" in cuerpo


def test_el_excel_y_la_pantalla_leen_las_mismas_filas():
    """El cuadro descargable no puede ser una copia del cuadro de la pantalla."""
    src = _pantalla()
    assert "const filas: FilaCuadro[] = filasEstado.flatMap" in src
    assert "{filasEstado.flatMap(f => [(" in src
    # Y que no quede ningun consumidor RECORRIENDO la lista cruda por su
    # cuenta: en Pre-Cierre dibujaria los tres agregados que ya no van. Lo
    # unico que puede tocar `ESTADO` directo es el memo que la arma.
    recorren = re.findall(r"ESTADO\.(?:flatMap|map|find|forEach|reduce)\(", src)
    assert recorren == [], f"quedo un consumidor con la lista cruda: {recorren}"


def test_la_linea_de_ingreso_abre_sus_cuentas():
    """Revisar es poder bajar de la linea a la cuenta que la formo."""
    cuerpo = _memo()
    assert 'abre: { clase: "revenue", clave: code }' in cuerpo
    src = _pantalla()
    # El click respeta `abre` y, cuando no hay, cae en el camino de siempre.
    assert "const ab = f.abre ?? (CLASE_DE[f.code]" in src
