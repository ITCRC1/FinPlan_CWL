# -*- coding: utf-8 -*-
"""Ninguna cuenta del catálogo puede llegar a su renglón POR DESCARTE.

Owner, 2026-09-09: *«corrige»*, sobre las dos cosas que la auditoría había
encontrado y yo había dejado señaladas.

## El error que esto hace imposible

`construir_resolvedor` busca la regla del par exacto `(departamento, cuenta)`.
Cuando no la encuentra, no falla: **cae** — a la regla del mismo código en otro
departamento, o a una genérica. La plata aterriza en un renglón que no es el
suyo.

Y no se nota. Es una reclasificación entre dos líneas, así que **ningún total se
mueve**: el GOP cuadra, la verificación de arriba contra abajo cuadra, y el P&L
se ve perfecto. Sólo se ve cruzando el detalle contra el motor, que es lo que
hace la Auditoría — y así apareció:

- **582,93 al año** de reparto de lavandería a Tour Activities (`0150`/`7310`)
  contabilizados en Habitaciones, en el BUDGET 2026 de Amarena.
- **1.361,29 al año** por lo mismo en Oxygen, encontrado el 2026-09-03.
- **15 cuentas de Gerencia** (`0181`) cayendo en A&B y en Habitaciones: `5700` y
  `5701` a Cafetería, nueve 7xxx a `OPEX_FB` y cuatro a `OPEX_ROOMS`. En cero
  hoy, en las tres propiedades — pero el día que alguien postee ahí, el gasto de
  Gerencia aparece como gasto de A&B.

## Por qué la guarda va sobre el CATÁLOGO y no sobre lo cargado

Medir sólo lo que tiene monto haría que la prueba pasara mientras la cuenta
esté vacía y fallara el día que alguien la use — o sea, justo cuando ya no se
puede arreglar sin mover el P&L de un mes cerrado. El catálogo es lo que se
puede llenar; ahí es donde hay que estar cubierto.
"""
import json
import pathlib

import pytest

from app.engine import pl_engine

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SEMILLAS = RAIZ / "app" / "seed_data"

#: Pares que a propósito NO tienen regla propia, con el motivo.
#:
#: Va acá y no en un comentario para que agregar una excepción sea un cambio
#: visible en el diff: dejar una cuenta cayendo por descarte es una decisión
#: contable, no un olvido, y tiene que costar una línea escrita.
SIN_REGLA_A_PROPOSITO: dict[tuple[str, str], str] = {}


def _reglas() -> list[dict]:
    d = json.loads((SEMILLAS / "mapping_pl.json").read_text(encoding="utf-8"))
    return [{"account_code": str(x.get("account_code") or ""),
             "dept_code": str(x.get("dept_code") or ""),
             "report_line_code": x.get("report_line_code"),
             "active_status": x.get("active_status"),
             "rollup_operator": x.get("rollup_operator")}
            for x in d["account_mapping"]]


def _del_catalogo() -> list[tuple[str, str]]:
    orden = json.loads((SEMILLAS / "orden_plantilla.json")
                       .read_text(encoding="utf-8"))["orden"]
    return sorted({(f["dept_code"], str(f["cuenta"])) for f in orden})


def test_ninguna_cuenta_del_catalogo_cae_por_descarte():
    resolver = pl_engine.construir_resolvedor(_reglas())
    malas = []
    for dep, cta in _del_catalogo():
        if (dep, cta) in SIN_REGLA_A_PROPOSITO:
            continue
        regla, como = resolver(dep, cta)
        if como in ("FALLBACK", "DROP"):
            malas.append((dep, cta, (regla or {}).get("report_line_code"), como))
    assert not malas, (
        "estas combinaciones llegan a su renglón por descarte, así que la plata "
        "queda en el departamento equivocado sin que ningún total se mueva:\n"
        + "\n".join("  %s / %s -> %s (%s)" % m for m in malas))


def test_el_reparto_de_lavanderia_a_tours_tiene_regla_propia():
    """El caso concreto que costó 582,93 al año acá y 1.361,29 en Oxygen.

    Se nombra aparte del barrido porque el barrido depende de que la cuenta esté
    en `orden_plantilla.json`, y ésta llegó por los checkbooks: la encontró la
    Auditoría cruzando el detalle contra el motor, no el catálogo.
    """
    resolver = pl_engine.construir_resolvedor(_reglas())
    regla, como = resolver("0150", "7310")
    assert como == "exact", f"volvió a resolver por {como}"
    assert regla["report_line_code"] == "OPEX_TOURS", (
        "el reparto de lavandería a Tour Activities dejó de ir a Tours")


def test_las_excepciones_declaradas_siguen_haciendo_falta():
    """⚠️ En los dos sentidos.

    Una lista que sólo perdona nunca se limpia: si alguien le pone regla a una
    cuenta declarada acá, la declaración sobra y tiene que salir, o dentro de un
    año nadie va a saber cuáles siguen siendo de verdad.
    """
    if not SIN_REGLA_A_PROPOSITO:
        pytest.skip("no hay excepciones declaradas")
    resolver = pl_engine.construir_resolvedor(_reglas())
    sobran = [par for par in SIN_REGLA_A_PROPOSITO
              if resolver(par[0], par[1])[1] == "exact"]
    assert not sobran, f"estas ya tienen regla y la excepción sobra: {sobran}"
