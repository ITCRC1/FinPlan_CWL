# -*- coding: utf-8 -*-
"""Una categoria de habitacion que abre en 2027 no cuenta en 2026.

Owner, 2026-09-16, sobre «Villas Deluxe» y «Residencia» en la carga de agosto:
«esto no aplica todavia para el 2026» · «si esta para 2027 pero no para 2026» ·
«las voy a usar ya en 2026 pero deben estar apagadas para 2026, ya que el
presupuesto lo empiezo en octubre».

Las dos cosas a la vez, y por eso `active` no alcanzaba:

  * fuera del Actual 2026  — no existian todavia;
  * dentro del Budget 2027 — que se arma en octubre DE 2026.

El filtro es por el año del ESCENARIO, nunca por la fecha de hoy.

## Lo que hacian mientras aparecian

Sumaban NOCHES DISPONIBLES (62 y 31 en agosto) sin sumar unidades: el cuadro
decia 30 unidades y contaba 93 noches que no existen. Eso infla el denominador
de la ocupacion y del RevPAR — los dos salian mas bajos de lo real, sin error y
sin aviso.
"""
import io
import pathlib
import re

from app.models.room_type_config import RoomTypeConfig, aplica_en

API = pathlib.Path(__file__).resolve().parents[1] / "app" / "api"


def test_la_categoria_lleva_desde_que_año_existe():
    col = RoomTypeConfig.__table__.c.vigente_desde_anio
    assert col.nullable, "nulo = de siempre; es el caso normal"


def test_el_filtro_deja_pasar_lo_de_siempre_y_frena_lo_que_no_abrio():
    cond = str(aplica_en(2026))
    assert "active" in cond
    assert "vigente_desde_anio IS NULL" in cond, (
        "una categoria sin año declarado tiene que seguir apareciendo")
    assert "vigente_desde_anio <=" in cond


def test_sin_año_cae_al_comportamiento_viejo():
    """Una consulta que no sabe el año no puede inventarlo."""
    assert "vigente_desde_anio" not in str(aplica_en(None))


def test_ninguna_consulta_filtra_por_active_a_secas():
    """`active == True` suelto deja pasar categorias que todavia no abrieron, y
    el sintoma es un KPI un poco bajo — que nadie lee como defecto."""
    malos = {}
    for f in sorted(API.glob("*.py")):
        src = io.open(f, encoding="utf-8").read()
        # Sin comentarios: lo que corre, no lo que explica.
        codigo = "\n".join(l for l in src.split("\n")
                           if not l.lstrip().startswith("#"))
        hits = re.findall(r"RoomTypeConfig\.active\s*==\s*True", codigo)
        if hits:
            malos[f.name] = len(hits)
    assert not malos, (
        f"consultas que filtran por `active` sin el año: {malos}. "
        "Usar `aplica_en(anio)` — ver app/models/room_type_config.py")
