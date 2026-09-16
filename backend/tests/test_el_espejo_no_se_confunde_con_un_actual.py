# -*- coding: utf-8 -*-
"""Nadie busca «el ACTUAL» sin excluir el espejo del Pre-Cierre.

El espejo es `type="ACTUAL"` a proposito —para que el P&L lo calcule con el
mismo motor que un cierre de verdad— y se distingue por `es_precierre=True`.
Pero trae UN SOLO MES y es lo ultimo que se creo, asi que cualquier consulta
que pida «el ACTUAL del hotel y el año» se lo lleva; si ademas ordena por
`created_at desc`, se lo lleva SIEMPRE.

Ya paso DOS veces, y las dos en silencio:

1. `scenarios_api._match_block_target` — el Pase a Final escribia sobre el
   espejo en vez del ACTUAL. Lado de ESCRITURA.
2. `recalculate.linked_actual_scenario` — de ahi salen los meses CERRADOS de
   todo forecast. Apuntando al espejo, once de los doce meses no tenian dato y
   el P&L los reportaba en CERO. Owner, 2026-09-16: «por que las versiones de
   forecast ninguna tiene revenue de actuales». Lado de LECTURA.

Ninguna de las dos dio error: dieron ceros, que se leen como «no hubo negocio».
Por eso esto es una prueba y no un comentario.
"""
import io
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[1] / "app"

#: Donde SI se puede nombrar el tipo crudo, con su razon.
PERMITIDO = {
    # El helper: es quien define la condicion.
    "models/scenario.py",
    # Crea el espejo — tiene que poder decir que es un ACTUAL.
    "api/precierre_api.py",
}

#: `type == "ACTUAL"` y sus variantes al consultar.
PATRON = re.compile(r'\.type\s*==\s*["\']ACTUAL["\']|type\s*=\s*["\']ACTUAL["\']')


def _fuentes():
    for f in sorted(RAIZ.rglob("*.py")):
        rel = f.relative_to(RAIZ).as_posix()
        if rel in PERMITIDO:
            continue
        yield rel, io.open(f, encoding="utf-8").read()


def test_ninguna_consulta_pide_el_actual_sin_excluir_el_espejo():
    culpables = []
    for rel, src in _fuentes():
        for n, linea in enumerate(src.splitlines(), 1):
            if not PATRON.search(linea):
                continue
            # Una comparacion sobre un objeto ya cargado (`sc.type == "ACTUAL"`)
            # no es una consulta: no puede traerse el espejo por error, porque
            # el escenario ya esta elegido. Lo que se vigila es el SELECT.
            if re.search(r'\bScenario\.type\s*==', linea):
                culpables.append(f"{rel}:{n}  {linea.strip()}")
    assert not culpables, (
        "consultas que pueden traerse el espejo del Pre-Cierre en vez del "
        "ACTUAL real:\n  " + "\n  ".join(culpables)
        + "\n\nUsar `scenario.actual_de_verdad()`. El espejo trae un solo mes: "
          "una consulta que se lo lleve devuelve CEROS, no un error.")


def test_el_helper_excluye_el_espejo():
    """Que la condicion diga lo que promete, no solo que exista."""
    from app.models.scenario import actual_de_verdad
    sql = str(actual_de_verdad().compile(compile_kwargs={"literal_binds": True}))
    assert "es_precierre" in sql, sql
    assert "ACTUAL" in sql, sql
