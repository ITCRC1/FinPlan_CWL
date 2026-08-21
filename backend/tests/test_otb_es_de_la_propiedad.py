# -*- coding: utf-8 -*-
"""El On the Books se guarda por PROPIEDAD, no por escenario.

**La regla (owner, 2026-08-18).** «El escenario es solo una referencia
comparativa, pero no tiene nada que ver con las subidas.»

Sacar el candado del presupuesto (ver `test_otb_no_lo_frena_el_candado`) fue la
mitad visible. La otra mitad era de fondo: las tres tablas del OTB estaban
llaveadas por `scenario_id`, y eso partía el dato. Medido en producción antes
de migrar:

    cortes 24, 25, 26, 27, 28  ->  ACTUAL 2026
    corte  34                  ->  BUDGET 2027 · Final

Subir el XML teniendo elegido un presupuesto dejaba las reservas AHÍ, invisibles
desde cualquier otro escenario. Y el FK tenía `ON DELETE CASCADE`: borrar un
presupuesto se llevaba puesto un hecho de Opera que no le pertenecía.

Se midió antes de fusionar: 86 filas, dos escenarios, **cero choques** de
(corte, año, mes). La migración 126 igual verifica los duplicados y falla
ruidosamente si aparecen en otra base — fusionar en silencio perdería filas.
"""
import ast
import inspect
import re

import pytest

from app.api import revenue_api
from app.models.on_the_books import OnTheBooksEntry
from app.models.otb_daily_occ import OtbDailyOcc
from app.models.otb_week_param import OtbWeekParam

MODELOS = [OnTheBooksEntry, OtbDailyOcc, OtbWeekParam]

#: Las rutas que leen o escriben On the Books.
RUTAS_OTB = [
    "get_on_the_books", "get_otb_weeks", "get_otb_years", "get_otb_params",
    "put_otb_param", "get_otb_pacing", "clear_otb", "get_otb_entry",
    "put_otb_entry", "get_daily_occ", "get_daily_occ_entry",
    "put_daily_occ_entry", "import_otb_xml",
]


@pytest.mark.parametrize("modelo", MODELOS, ids=lambda m: m.__tablename__)
def test_la_tabla_tiene_hotel(modelo):
    assert "hotel_id" in modelo.__table__.columns, (
        f"{modelo.__tablename__} tiene que llevar el hotel: el On the Books es "
        f"de la propiedad")
    assert not modelo.__table__.columns["hotel_id"].nullable


@pytest.mark.parametrize("modelo", MODELOS, ids=lambda m: m.__tablename__)
def test_la_llave_unica_es_por_hotel_y_no_por_escenario(modelo):
    """Si la llave siguiera siendo el escenario, el dato se volvería a partir."""
    unicas = [c for c in modelo.__table__.constraints
              if c.__class__.__name__ == "UniqueConstraint"]
    assert unicas, f"{modelo.__tablename__} perdió su llave única"
    for u in unicas:
        cols = [c.name for c in u.columns]
        assert "hotel_id" in cols, f"{u.name} no lleva el hotel: {cols}"
        assert "scenario_id" not in cols, (
            f"{u.name} sigue llaveada por escenario: {cols}. Con eso el mismo "
            f"corte cargado desde dos escenarios vuelve a ser dos filas.")


@pytest.mark.parametrize("modelo", MODELOS, ids=lambda m: m.__tablename__)
def test_borrar_un_escenario_no_se_lleva_las_reservas(modelo):
    """`scenario_id` es RASTRO de dónde se subió, no dueño del dato.

    Con `ON DELETE CASCADE` —lo que había— borrar un presupuesto borraba un
    hecho de Opera que no le pertenecía.
    """
    col = modelo.__table__.columns["scenario_id"]
    assert col.nullable, "scenario_id tiene que poder quedar en NULL"
    fks = list(col.foreign_keys)
    assert fks, "se perdió el FK a scenarios"
    assert (fks[0].ondelete or "").upper() == "SET NULL", (
        f"ondelete={fks[0].ondelete!r} — tiene que ser SET NULL, no CASCADE")


@pytest.mark.parametrize("nombre", RUTAS_OTB)
def test_la_ruta_consulta_por_hotel(nombre):
    """Ninguna ruta de OTB puede volver a filtrar por escenario."""
    src = inspect.getsource(getattr(revenue_api, nombre))
    for modelo in ("OnTheBooksEntry", "OtbDailyOcc", "OtbWeekParam"):
        assert f"{modelo}.scenario_id ==" not in src, (
            f"`{nombre}` filtra {modelo} por escenario. El On the Books es de "
            f"la propiedad: se consulta por hotel_id.")


@pytest.mark.parametrize("nombre", RUTAS_OTB)
def test_la_ruta_define_el_hotel_que_usa(nombre):
    """El defecto que esta prueba atrapa es un NameError en producción.

    Cambiar 22 consultas de `scenario_id` a `hotel_id` es mecánico; olvidarse
    de definir `hotel` en UNA de las trece funciones no lo ve ni el linter ni
    el arranque de la app — revienta cuando alguien abre esa pantalla.
    """
    src = inspect.getsource(getattr(revenue_api, nombre))
    usa = re.search(r"\bhotel\b(?!_)", src)
    if not usa:
        pytest.skip(f"{nombre} no usa `hotel`")
    assert re.search(r"^\s*hotel = ", src, re.M), (
        f"`{nombre}` usa `hotel` sin definirlo: NameError en cuanto se llame")


def test_la_migracion_126_verifica_los_choques_antes_de_fusionar():
    """Fusionar dos escenarios en uno puede PERDER filas. Hay que mirarlo antes.

    En CWL son cero, medido. Pero la migración corre en otras bases, y ahí un
    duplicado tiene que hacer ruido, no desaparecer una fila.
    """
    ruta = "alembic/versions/126_otb_de_la_propiedad.py"
    src = open(ruta, encoding="utf-8").read()
    ast.parse(src)   # que sea Python válido, no solo texto
    assert "HAVING COUNT(*) > 1" in src, "la 126 no busca duplicados"
    assert "raise RuntimeError" in src, "la 126 no falla si los encuentra"


def test_la_migracion_126_REHACE_el_fk_y_no_solo_el_modelo():
    """`alter_column(nullable=True)` no cambia el ondelete. Hay que rehacer el FK.

    Sin esto el modelo diría `SET NULL` y la base seguiría con `CASCADE`: los
    tests de arriba pasarían en verde y borrar un escenario en producción se
    seguiría llevando las reservas puestas. Es el defecto que ya mordió antes
    —verificar el modelo y no la base— y por eso se verifica el SQL.
    """
    src = open("alembic/versions/126_otb_de_la_propiedad.py", encoding="utf-8").read()
    assert "DROP CONSTRAINT IF EXISTS {tabla}_scenario_id_fkey" in src
    assert "ON DELETE SET NULL" in src


def test_los_drop_de_la_126_van_con_IF_EXISTS():
    """En Postgres un DDL que falla aborta la transacción entera.

    Un `try/except` alrededor de `op.drop_constraint` se traga el error de
    Python y deja la transacción muerta para todo lo que venga después — la
    migración parecería seguir y reventaría más adelante, lejos de la causa.
    """
    src = open("alembic/versions/126_otb_de_la_propiedad.py", encoding="utf-8").read()
    assert "try:" not in src, "los DROP van con IF EXISTS, no con try/except"
    assert src.count("DROP CONSTRAINT IF EXISTS") >= 4
