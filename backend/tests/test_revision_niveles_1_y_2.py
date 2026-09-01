# -*- coding: utf-8 -*-
"""
LA REVISIÓN AVISA, NO RECHAZA — Y NO SE CALLA NADA.

Owner (2026-08-31): *«es un reporte de varianzas pero también de discrepancias,
ya que cualquier cosa puede subir y el sistema no puede ignorarlos. Quizás no
rechazar la subida pero sí indicar los hallazgos.»*

Cada chequeo tiene acá su caso armado a mano —con el monto— y su caso limpio.
Los módulos son puros, así que no hace falta base para nada de esto.

⚠️ Y hay una prueba que corre los dos niveles contra **julio 2026, un mes ya
cerrado y validado**. Un mes bueno tiene que salir casi limpio: si un chequeo
grita ahí, el que grita está mal. Fue lo que pasó con tres de ellos —los
subtotales del propio reporte, el neteo de las allocations y el impuesto de
renta negativo— y por eso esa prueba existe.
"""
import json
import pathlib
from decimal import Decimal as D

import pytest

from app.revision import nivel1_estructura as n1
from app.revision import nivel2_coherencia as n2

BASE = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = BASE / "tests" / "fixtures" / "integrity_final_JUL2026.xlsx"
SEMILLA = BASE / "app" / "seed_data" / "CWL" / "mapd_integrity.json"
TC = D("454.75")


def fila(cuenta="7000-0180", base=7000, depto="0180", destino="0180",
         grupo="ADMIN", categoria="Otros Gastos", mes=100, acum=None, n=20,
         desc="una cuenta"):
    return {"fila": n, "cuenta": cuenta, "cuenta_base": base, "depto": depto,
            "destino_finplan": destino, "grupo": grupo, "categoria": categoria,
            "descripcion": desc, "mes_usd": D(str(mes)),
            "acumulado_usd": D(str(mes if acum is None else acum))}


# ═════════════════════════════════════════════════════════════════════════════
# NIVEL 1 · ESTRUCTURA
# ═════════════════════════════════════════════════════════════════════════════

def test_una_cuenta_sin_mapeo_se_reporta_con_su_monto():
    h = n1.cuentas_sin_mapeo([fila(mes=5000)], lambda d, c: "")
    assert len(h) == 1
    assert h[0].clave == "cuenta_sin_mapeo"
    assert h[0].gravedad == "critico"
    assert h[0].monto == D("5000")
    assert h[0].referencias[0]["fila"] == 20


def test_si_todas_mapean_no_hay_hallazgo():
    assert n1.cuentas_sin_mapeo([fila()], lambda d, c: "OPEX_ADMIN") == []


def test_un_depto_sin_puente_dice_cuanta_plata_es():
    h = n1.departamentos_sin_puente([{"depto": "0999", "mes_usd": D("1234.5"),
                                      "cuentas": ["4000-0999"]}])
    assert h[0].clave == "depto_sin_puente" and h[0].monto == D("1234.5")
    assert "0999" in h[0].detalle


def test_una_cuenta_nueva_se_reporta():
    vistas = {(7000, "0180")}
    h = n1.cuentas_nuevas([fila(), fila(cuenta="7999-0180", base=7999, mes=90)],
                          vistas)
    assert len(h) == 1 and h[0].monto == D("90")


def test_sin_historia_no_hay_cuentas_nuevas():
    """El primer mes del año no puede tener novedades: no hay contra qué."""
    assert n1.cuentas_nuevas([fila()], set()) == []


def test_una_linea_obligatoria_en_cero_se_reporta():
    h = n1.lineas_obligatorias_vacias({"OH_UTILITIES": 0, "REV_ROOMS": 100},
                                      ["OH_UTILITIES", "REV_ROOMS"])
    assert len(h) == 1 and "OH_UTILITIES" in h[0].detalle
    assert "luz" in h[0].porque


# ═════════════════════════════════════════════════════════════════════════════
# NIVEL 2 · COHERENCIA INTERNA
# ═════════════════════════════════════════════════════════════════════════════

def test_una_fila_con_monto_y_sin_cuenta_es_critica():
    """El caso que ya costó $40.613 en el Actual 2024."""
    h = n2.filas_con_monto_y_sin_cuenta(
        [{"fila": 88, "monto_crc": D("45475"), "texto": "GASTO SIN CODIGO"}], TC)
    assert h[0].gravedad == "critico" and h[0].monto == D("100")
    assert "40.613" in h[0].porque


def test_el_subdetalle_que_no_suma_su_padre():
    h = n2.subdetalle_que_no_suma_su_padre(
        [fila(cuenta="7000-0180", mes=1000)], {"7000-0180": D("940")})
    assert h[0].clave == "subdetalle_no_suma" and h[0].monto == D("60")


def test_si_el_subdetalle_suma_no_hay_hallazgo():
    assert n2.subdetalle_que_no_suma_su_padre(
        [fila(cuenta="7000-0180", mes=1000)], {"7000-0180": D("1000")}) == []


def test_un_departamento_de_reparto_que_no_cierra_en_cero():
    """No es que las 4999 neteen entre sí —en julio las dos son negativas—: es
    que el departamento que reparte tiene que distribuir TODO su costo."""
    filas = [fila(destino="0161", categoria="Nómina", mes=3000),
             fila(cuenta="4999-0161", base=4999, destino="0161",
                  categoria="Allocation", mes=-2500)]
    h = n2.allocation_que_no_netea(filas, {"0161", "0220"})
    assert h[0].clave == "allocation_no_netea" and h[0].monto == D("500")


def test_un_reparto_que_cierra_no_es_hallazgo():
    filas = [fila(destino="0161", categoria="Nómina", mes=3000),
             fila(cuenta="4999-0161", base=4999, destino="0161",
                  categoria="Allocation", mes=-3000)]
    assert n2.allocation_que_no_netea(filas, {"0161"}) == []


def test_un_monto_negativo_se_reporta():
    h = n2.signo_contrario_a_su_clase([fila(mes=-250)])
    assert h[0].clave == "signo_contrario" and h[0].monto == D("-250")


def test_el_impuesto_de_renta_negativo_NO_es_hallazgo():
    """En un mes con pérdida es un crédito, y da negativo por definición.
    Reportarlo lo pondría todos los meses malos, con el monto más grande de la
    lista, tapando los que sí importan."""
    assert n2.signo_contrario_a_su_clase(
        [fila(cuenta="8060-0240", base=8060, categoria="No Operativo",
              mes=-40364.12)]) == []


def test_el_acumulado_que_no_cierra():
    """acumulado(mes) − acumulado(anterior) tiene que dar el mes."""
    f = fila(mes=100, acum=1000)
    h = n2.acumulado_no_cierra([f], {(7000, "0180"): D("800")})
    assert h[0].clave == "acumulado_no_cierra" and h[0].monto == D("100")


def test_sin_mes_anterior_el_acumulado_no_se_juzga():
    """«No se pudo mirar» no es «está mal»."""
    assert n2.acumulado_no_cierra([fila(mes=100, acum=1000)], {}) == []


# ═════════════════════════════════════════════════════════════════════════════
# LA PROPIEDAD QUE LOS UNE
# ═════════════════════════════════════════════════════════════════════════════

def test_ningun_hallazgo_rechaza_la_carga():
    """Bloquear es potestad de los cuatro controles de `verificacion.py`, y de
    nadie más. Un hallazgo que rechazara enseñaría a esquivarlo."""
    from app.revision.hallazgo import GRAVEDADES
    assert "bloquea" not in GRAVEDADES
    assert set(GRAVEDADES) == {"critico", "aviso", "info"}


def test_todo_hallazgo_explica_por_que_y_que_hacer():
    """Un hallazgo sin explicación no se puede discutir, y el que lo lee termina
    aprobándolo por cansancio."""
    todos = (n1.cuentas_sin_mapeo([fila(mes=1)], lambda d, c: "")
             + n1.departamentos_sin_puente([{"depto": "0999", "mes_usd": D("1")}])
             + n1.cuentas_nuevas([fila(base=1)], {(7000, "0180")})
             + n1.lineas_obligatorias_vacias({"OH_UTILITIES": 0}, ["OH_UTILITIES"])
             + n2.filas_con_monto_y_sin_cuenta(
                 [{"fila": 1, "monto_crc": D("1"), "texto": "x"}], TC)
             + n2.subdetalle_que_no_suma_su_padre([fila(mes=100)], {"7000-0180": D("0")})
             + n2.signo_contrario_a_su_clase([fila(mes=-1)])
             + n2.acumulado_no_cierra([fila(mes=1, acum=999)], {(7000, "0180"): D("0")}))
    assert todos
    for h in todos:
        assert h.porque and h.que_hacer, h.clave
        assert h.nivel in (1, 2)


# ═════════════════════════════════════════════════════════════════════════════
# CONTRA UN MES DE VERDAD
# ═════════════════════════════════════════════════════════════════════════════

def test_un_mes_ya_cerrado_sale_casi_limpio():
    """Julio 2026 está revisado y cerrado. Si un chequeo grita acá, el que está
    mal es el chequeo.

    Tres lo hicieron y se corrigieron: los subtotales del propio reporte
    («UTILIDAD OPERATIVA») contados como plata sin cuenta, el neteo de las
    allocations medido entre las 4999 en vez de por departamento, y el impuesto
    de renta negativo.
    """
    from app.engine import pl_engine
    from app.importers import integrity_final as m
    from app.seed_department_catalog import build_rows
    filas_cat = build_rows()
    pl_engine.set_dept_catalog([{"dept_code": f["dept_code"],
                                 "default_pl_group": f.get("default_pl_group", ""),
                                 "parent_dept_code": f.get("parent_dept_code")}
                                for f in filas_cat])
    puente = {d["codigo"]: d for d in
              json.loads(SEMILLA.read_text(encoding="utf-8"))["departamentos"]}
    r = m.leer(FIXTURE.read_bytes(), TC, puente,
               lambda d: pl_engine.group_for_dept(d) if d else None)

    assert r["sin_cuenta"] == [], (
        "los subtotales del reporte no son filas sin cuenta: "
        + str(r["sin_cuenta"]))

    fuentes = {f["dept_code"] for f in filas_cat if f.get("is_allocation_source")}
    h = n2.revisar(r["filas"], tc=TC, sin_cuenta=r["sin_cuenta"],
                   subdetalle=r["subdetalle"], fuentes_de_reparto=fuentes)
    claves = {x.clave for x in h}
    assert "fila_sin_cuenta" not in claves
    assert "allocation_no_netea" not in claves, (
        "los departamentos de reparto de julio cierran en cero")
    assert "subdetalle_no_suma" not in claves


def test_el_subdetalle_de_julio_suma_sus_padres():
    """315 cuentas padre con detalle, y ninguna discrepa. Es lo que hace creíble
    que el chequeo sirva cuando alguna discrepe."""
    from app.engine import pl_engine
    from app.importers import integrity_final as m
    from app.seed_department_catalog import build_rows
    pl_engine.set_dept_catalog([{"dept_code": f["dept_code"],
                                 "default_pl_group": f.get("default_pl_group", ""),
                                 "parent_dept_code": f.get("parent_dept_code")}
                                for f in build_rows()])
    puente = {d["codigo"]: d for d in
              json.loads(SEMILLA.read_text(encoding="utf-8"))["departamentos"]}
    r = m.leer(FIXTURE.read_bytes(), TC, puente, lambda d: None)
    assert len(r["subdetalle"]) > 300
    assert n2.subdetalle_que_no_suma_su_padre(r["filas"], r["subdetalle"]) == []
