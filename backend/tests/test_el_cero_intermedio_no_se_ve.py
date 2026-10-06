# -*- coding: utf-8 -*-
"""Poner en cero y volver a escribir es UN movimiento. Lo de en medio no existe.

**El defecto (owner, 2026-10-06, el quinto 409 de la misma subida).**

    cambiar ActualEntry.jun: 583.3333 -> 0 (diferencia 583.3333) · 7625 en 0230

El archivo **sí traía** ese 7625 con 583,33 en junio — se comprobó abriendo la
plantilla que el owner acababa de bajar. La carga en modo merge trabaja en dos
pasos: pone en cero los meses del archivo en todas las filas y después escribe
los valores de vuelta. Entre los dos pasos había dos `DELETE`, y un `execute`
dispara el **autoflush** de lo que está pendiente.

El candado de meses cerrados corre en ese flush. Veía el CERO —todavía sin el
valor de vuelta— y frenaba la carga. Sin el flush de en medio compara 583,3333
contra 583,33, que es medio centavo del redondeo de la plantilla y ya se tolera.

Era la carga tropezándose con su propio paso intermedio, y es el tipo de defecto
que no se ve leyendo ninguno de los dos pasos: solo existe en el orden.

**Lo que vigila esta prueba** no es el orden de dos líneas —eso se reacomoda sin
querer— sino que entre el cero y el valor de vuelta no viaje NADA a la base.
"""
import inspect
import re

from app.api import scenarios_api


def _cuerpo_del_merge_de_actual_entry() -> str:
    """El tramo entre el bucle que pone en cero y el que escribe de vuelta."""
    fuente = inspect.getsource(scenarios_api.import_gl_detail)
    i = fuente.index('e.set_month(mi_, Decimal("0"))')
    j = fuente.index('for (dept_c, code_c, outlet_c), a in ae_agg.items():', i)
    return fuente[i:j]


def test_no_hay_nada_que_vaya_a_la_base_entre_el_cero_y_el_valor():
    """Un `execute` acá dispara el autoflush y el candado ve el estado a medias.

    Vale para cualquier `execute`, no solo para los dos `DELETE` que estaban:
    una consulta nueva metida ahí reabre el mismo agujero.
    """
    enmedio = _cuerpo_del_merge_de_actual_entry()
    # Se miran las líneas de código, no los comentarios que explican el porqué.
    codigo = "\n".join(l for l in enmedio.splitlines()
                       if not l.strip().startswith("#"))
    assert "db.execute" not in codigo, (
        "hay una llamada a la base entre poner en cero y escribir de vuelta: "
        "el autoflush deja que el candado vea el cero")
    assert "await" not in codigo, (
        "cualquier await ahí puede acabar en un flush")


def test_los_dos_delete_siguen_estando():
    """Se MOVIERON, no se borraron: el resumen de línea y las estadísticas de
    los meses subidos se siguen limpiando, o el P&L leería dos fuentes."""
    fuente = inspect.getsource(scenarios_api.import_gl_detail)
    merge = fuente[fuente.index("if merge:\n            if touched:"):]
    merge = merge[:merge.index("        else:")]
    assert "sa_delete(ActualPLLine)" in merge
    assert "sa_delete(ScenarioStat)" in merge
    # Y van DESPUÉS de escribir los valores de vuelta.
    assert merge.index("for (dept_c, code_c, outlet_c), a in ae_agg.items():") \
        < merge.index("sa_delete(ActualPLLine)")


def test_la_tolerancia_cubre_el_redondeo_de_la_plantilla():
    """583,3333 en la base contra 583,33 en el archivo NO es una edición.

    Es el caso exacto del owner, con los números de producción: un gasto anual
    repartido en doce (7.000/12) baja a la plantilla con dos decimales y vuelve
    distinto. Si esto se cae, el 409 vuelve aunque el orden esté bien.
    """
    from decimal import Decimal

    from app.candado_meses import es_edicion

    assert not es_edicion(Decimal("583.3333"), Decimal("583.33"))
    # Pero la fila puesta en cero sí lo es — que es lo que el candado DEBE frenar.
    assert es_edicion(Decimal("583.3333"), Decimal("0"))
