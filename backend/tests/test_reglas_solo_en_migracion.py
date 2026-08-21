# -*- coding: utf-8 -*-
"""
UNA REGLA QUE VIVE SOLO EN UNA MIGRACIÓN NO VIAJA A LOS OTROS HOTELES.

Es una trampa de portabilidad, y es sutil porque **el hotel donde se arregló
queda bien**: la migración corre una vez, escribe la fila, y `seed_mapping` no
borra lo que sobra — así que sobrevive para siempre en esa base.

Pero `mapping_pl.json` es lo que viaja. Una propiedad nueva nace con lo que diga
el archivo, no con lo que digan las migraciones de Corcovado.

**El caso que lo destapó:** la migración `092` le dio al `0184` RRHH sus 52
reglas de mapeo. Corcovado quedó bien. Pero el archivo fuente no las tenía, así
que Amarena, Oxígen y Ojochal habrían nacido con **toda la planilla de Recursos
Humanos cayendo en `OPEX_ROOMS`** por descarte — sumada al gasto de
Habitaciones, sin dar error y con el GOP cuadrando igual.

Esta prueba fija los departamentos que ya se corrigieron. No pretende encontrar
los que falten: para eso está la auditoría de cobertura, que se corre a mano.
"""
import json
import pathlib

from app.engine import pl_engine
from app.seed_department_catalog import build_rows

MAPEO = (pathlib.Path(pl_engine.__file__).parents[1]
         / "seed_data" / "mapping_pl.json")

# depto → (línea que le toca, cuentas de muestra)
CORREGIDOS = {
    "0184": ("OH_ADMIN", ("6000", "6020", "7400", "7680")),
    "0151": ("OPEX_TIENDA", ("5203", "7400")),   # linea propia desde 2026-08-13
    # El crédito del reparto de Rooms a Villas y Residencias (mig 089). Sin la
    # regla, la 4999 de estos tres departamentos caía por FALLBACK en la regla
    # de la 4999 de Lavandería: los $92,108 que Rooms entregaba salían
    # restando de LAVANDERÍA. El GOP cuadraba igual, por eso el Control decía
    # «$0 se pierde» — el P&L por departamento quedaba mal por los dos lados.
    #
    # La regla estaba solo en la migración. Y las migraciones que hacen
    # `INSERT … SELECT FROM account_mapping` corren ANTES del seed, contra una
    # tabla vacía: en un hotel nuevo insertan cero filas. Corcovado quedaba
    # bien y los otros tres nacían con el error de $92k puesto.
    "0110": ("OPEX_ROOMS", ("4999",)),
    "0115": ("OPEX_ROOMS", ("4999",)),
    "0116": ("OPEX_ROOMS", ("4999",)),
}

# Pares que llegan a su línea HEREDANDO de la madre, y está bien que así sea.
#
# El owner (2026-08-14) cerró Administración como una familia: «0180 es el
# departamento madre, 0181 y 0184 son hijos; 0181 y 0184 solo tienen planilla,
# no tienen cuentas de gastos porque sus gastos se postean en la 0180». Así que
# el 0184 dejó de tener regla propia de opex — la 7400 y la 7680 ahora las
# hereda del 0180 por la cadena de padres (migración 112).
#
# Lo que esta prueba cuida NO es el modo `exact`: es que la cuenta no caiga por
# **descarte** en otro departamento, que es el bug de la migración 092. `parent`
# aterriza en la misma línea, `FALLBACK` es el que manda la plata a
# Habitaciones. Por eso se acepta `parent` acá y solo acá, enumerado par por
# par: aceptarlo en general dejaría pasar justo lo que se está cuidando.
HEREDADAS = {("0184", "7400"), ("0184", "7680")}


def _resolver():
    reglas = json.loads(MAPEO.read_text(encoding="utf-8"))["account_mapping"]
    pl_engine.set_dept_catalog(build_rows())
    return pl_engine.construir_resolvedor(reglas), reglas


def test_las_reglas_estan_en_el_archivo_fuente_no_solo_en_la_base():
    _, reglas = _resolver()
    for dept in CORREGIDOS:
        propias = [m for m in reglas if (m.get("dept_code") or "") == dept]
        assert propias, (
            f"el departamento {dept} no tiene reglas en mapping_pl.json. Si "
            "están solo en una migración, este hotel funciona y los otros tres "
            "nacen ruteando por descarte.")


def test_rutean_exacto_y_a_la_linea_que_les_toca():
    resolve, _ = _resolver()
    for dept, (linea, cuentas) in CORREGIDOS.items():
        for cuenta in cuentas:
            regla, como = resolve(dept, cuenta)
            esperado = "parent" if (dept, cuenta) in HEREDADAS else "exact"
            assert como == esperado, (dept, cuenta, como, esperado)
            # Se compara el SUFIJO —el departamento— y no el código completo.
            # Desde que el costo de ventas salió a su propia línea
            # (owner, 2026-08-14) una cuenta clase 5 del 0151 rutea a
            # `COS_TIENDA` en vez de `OPEX_TIENDA`: sigue siendo la Tienda, que
            # es lo que esta prueba cuida. El bug original era que caía en OTRO
            # departamento por fallback.
            assert (regla["report_line_code"].split("_", 1)[1]
                    == linea.split("_", 1)[1]), (
                dept, cuenta, regla["report_line_code"], linea)


def test_el_0184_no_cae_en_rooms():
    """El síntoma exacto que tendría una instalación nueva sin este arreglo."""
    resolve, _ = _resolver()
    for cuenta in ("6000", "6021", "6026"):
        regla, _ = resolve("0184", cuenta)
        assert regla["report_line_code"] != "OPEX_ROOMS", (
            f"la planilla de RRHH ({cuenta}) está cayendo en Habitaciones")
