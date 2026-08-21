# -*- coding: utf-8 -*-
"""
EL MAPEO TIENE QUE SER COHERENTE CONSIGO MISMO.

`mapping_pl.json` es la fuente de verdad del ruteo: 1.095 reglas que traducen
(departamento, cuenta) a una línea del P&L. El seed lo re-afirma campo por campo
en cada deploy, así que un error acá se vuelve permanente.

Estas cuatro propiedades no miran plata — miran la ESTRUCTURA. Ninguna de ellas
puede romperse sin que algo esté mal, y las cuatro son baratas de verificar:

1. **Ninguna regla apunta a una línea que no existe.** Una regla huérfana manda
   su monto a un `report_line_code` que el reporte no conoce: la plata se
   evapora sin dar error.

2. **La llave de negocio `(dept_code, account_code)` es única.** La llave del
   seed es `(report_id, source_department, account_code, source_origin)` —
   cuatro campos, tres de ellos TEXTO— así que dos reglas pueden convivir en la
   tabla apuntando al mismo par (departamento, cuenta) y a líneas DISTINTAS.
   Cuando eso pasa, `construir_resolvedor` se queda con la primera que aparece
   (`setdefault`), o sea con **el orden físico de las filas**. La línea la
   decide el orden, no una decisión — y el orden cambia solo.

   Es el camino por el que la plata se mueve sin que nadie toque nada: cambiarle
   una palabra a un `source_department` en el archivo hace que el seed INSERTE
   una fila nueva sin borrar la vieja (el seed no borra), y ahí quedan las dos.

3. **Los campos denormalizados dicen lo mismo que el reporte.** Cada regla
   arrastra una copia de `report_line_name`, `report_section` y `display_order`.
   Son copias, y las copias se desincronizan: el 2026-08-14 había **59 líneas**
   con el `display_order` viejo, incluida `REV_CLARO_HUERTA`, que llevaba el 75
   de `OH_CLARO_HUERTA` —otra línea, otra sección— en vez de su 27. No mueve el
   P&L (el motor ordena por `report_line_config`), pero sí desordena el listado
   del tab de mapeo, que es donde se revisa todo esto.

4. **Ningún nombre de departamento apunta a dos códigos.** Al revés SÍ se
   permite y es normal —el `0250` aparece como «Property Expenses» y como
   «MANAGEMENT FEES (3%)», que es cómo dos reglas de la misma cuenta `8005`
   consiguen convivir bajo la llave del seed—. Lo que no puede pasar es que un
   mismo texto signifique dos departamentos, porque el texto es lo que se lee
   en pantalla.
"""
import collections
import json
import pathlib
import re

import pytest

from app.seed_mapping import ARCHIVO


@pytest.fixture(scope="module")
def datos() -> dict:
    return json.loads(pathlib.Path(ARCHIVO).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def activas(datos) -> list[dict]:
    return [m for m in datos["account_mapping"] if m["active_status"] == "YES"]


def test_ninguna_regla_apunta_a_una_linea_inexistente(datos):
    lineas = {r["line_code"] for r in datos["report_line_config"]}
    huerfanas = collections.Counter(
        m["report_line_code"] for m in datos["account_mapping"]
        if m["report_line_code"] not in lineas)
    assert not huerfanas, (
        "estas reglas mandan su monto a una línea que el reporte no conoce, "
        f"así que se pierde sin dar error: {dict(huerfanas)}")


def _se_pisan(a, b) -> bool:
    """¿Dos reglas rigen a la vez? Vigencias `YYYY-MM` inclusive, None = sin tope."""
    a_ini, a_fin = a.get("vigente_desde") or "0000-00", a.get("vigente_hasta") or "9999-99"
    b_ini, b_fin = b.get("vigente_desde") or "0000-00", b.get("vigente_hasta") or "9999-99"
    return a_ini <= b_fin and b_ini <= a_fin


def test_la_llave_de_negocio_departamento_cuenta_es_unica(activas):
    """Dos reglas VIGENTES A LA VEZ para el mismo par = la línea la elige el
    orden de las filas.

    La unicidad es por par **y por momento**. Desde D9 el par (0180, 7120) tiene
    dos reglas: `OH_ADMIN` hasta jun-2026 y `OH_CC_COMMISSIONS` desde jul-2026.
    No se pisan un solo mes, así que no hay ambigüedad — pero si alguien les
    corre la vigencia y se solapan, esto tiene que volver a fallar.
    """
    por_par = collections.defaultdict(list)
    for m in activas:
        por_par[((m.get("dept_code") or "").strip(),
                 m["account_code"].strip())].append(m)

    ambiguos = {}
    for (dc, ac), v in por_par.items():
        chocan = {x["report_line_code"] for i, a in enumerate(v)
                  for b in v[i + 1:] if _se_pisan(a, b)
                  for x in (a, b)}
        if chocan:
            ambiguos[f"({dc or 'sin dept'}, {ac})"] = sorted(chocan)

    assert not ambiguos, (
        "hay más de una regla activa Y VIGENTE A LA VEZ para el mismo "
        "(departamento, cuenta). El resolvedor se queda con la primera que "
        "aparezca, así que la línea la decide el orden físico de las filas:\n"
        f"  {ambiguos}")


def test_los_campos_denormalizados_dicen_lo_mismo_que_el_reporte(datos):
    lineas = {r["line_code"]: r for r in datos["report_line_config"]}
    desfasados = []
    for m in datos["account_mapping"]:
        ref = lineas.get(m["report_line_code"])
        if ref is None:
            continue          # lo cubre la prueba de huérfanas
        for campo, campo_ref in (("report_line_name", "line_name"),
                                 ("report_section", "section"),
                                 ("display_order", "display_order")):
            if m[campo] != ref[campo_ref]:
                desfasados.append(
                    f"{m['report_line_code']}.{campo}: la regla dice "
                    f"{m[campo]!r} y el reporte {ref[campo_ref]!r}")
    assert not desfasados, (
        f"{len(desfasados)} copias desincronizadas del reporte:\n  "
        + "\n  ".join(sorted(set(desfasados))[:20]))


def test_ningun_nombre_de_departamento_apunta_a_dos_codigos(datos):
    por_nombre = collections.defaultdict(set)
    for m in datos["account_mapping"]:
        por_nombre[(m.get("source_department") or "").strip()].add(
            (m.get("dept_code") or "").strip())
    compartidos = {k: sorted(v) for k, v in por_nombre.items() if len(v) > 1}
    assert not compartidos, (
        "un mismo nombre de departamento significa dos códigos distintos, y el "
        f"nombre es lo que se lee en pantalla:\n  {compartidos}")


def test_toda_linea_calculada_lee_lineas_que_ya_se_evaluaron(datos):
    """El motor recorre las líneas en `display_order` y va guardando cada
    resultado para que las siguientes lo lean (`pl_engine`, «Evaluate report
    lines in display_order»). Una línea calculada que referencie a otra con
    orden IGUAL o MAYOR lee un cero, o lee el valor de la corrida anterior.

    El empate es el caso silencioso: hay 13 `display_order` repetidos en el
    reporte —tres de ellos entre líneas calculadas—, y `sorted` es estable, así
    que ante un empate manda el orden en que la base devolvió las filas. Hoy
    ninguna de las empatadas se lee a la otra; nada lo impedía.
    """
    orden = {r["line_code"]: r["display_order"] for r in datos["report_line_config"]}
    tarde = []
    for r in datos["report_line_config"]:
        if not r["line_type"].startswith("CALCULATED"):
            continue
        for tok in re.findall(r"[A-Z][A-Z0-9_]+", r["calculation_logic"] or ""):
            if tok in orden and orden[tok] >= r["display_order"]:
                tarde.append(f"{r['line_code']} (orden {r['display_order']}) lee "
                             f"{tok} (orden {orden[tok]})")
    assert not tarde, (
        "estas líneas calculadas leen una línea que todavía no se evaluó, así "
        f"que toman cero:\n  " + "\n  ".join(tarde))
