# -*- coding: utf-8 -*-
"""El registro de importaciones — Guillermo Fase 0 (`docs/GUILLERMO.md` §5.3).

**El hueco que cierra.** FinPlan tiene 23 puertas de subida y 18
parsers, y hasta hoy **ninguna forma de identidad de archivo**: ni checksum, ni
nombre guardado, ni tabla que dijera «esto ya se subió». Subir el mismo archivo
dos veces no se detectaba, y como la respuesta HTTP es efímera tampoco quedaba
traza de qué entró.

⚠️ **Lo que ya protegía, y por qué no alcanzaba.** El anti-duplicado existente
es por DOMINIO —`UNIQUE (scenario_id, dept_code, account_code, outlet)` más el
`merge` acotado al período—. Eso evita filas duplicadas, pero **no distingue
«subí el mismo archivo otra vez» de «subí el archivo corregido»**, que es
justamente la diferencia que importa.
"""
import io
import os
import re

import pytest

from app.importers.registro import checksum_de

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── El checksum ─────────────────────────────────────────────────────────────

def test_el_checksum_es_del_CONTENIDO_no_del_nombre():
    """⚠️ La razón de ser: «actuales_julio (2).xlsx» es la forma más común de
    reimportar sin querer. Renombrar no convierte un archivo en otro."""
    assert checksum_de(b"mismo contenido") == checksum_de(b"mismo contenido")
    assert checksum_de(b"contenido A") != checksum_de(b"contenido B")


def test_un_byte_distinto_cambia_el_checksum():
    """Un archivo corregido TIENE que poder entrar. Si el checksum no
    distinguiera la corrección, el anti-reimport bloquearía el arreglo."""
    assert checksum_de(b"total: 100") != checksum_de(b"total: 101")


def test_el_checksum_entra_en_la_columna():
    """sha256 en hex son 64 caracteres, y la columna es `String(64)`."""
    assert len(checksum_de(b"x")) == 64


# ── Lo más peligroso del módulo ─────────────────────────────────────────────

def test_EL_SEEK_CERO_ESTA_PUESTO():
    """⚠️ **Si esto falta, se rompe todo en silencio.**

    Leer el `UploadFile` en la dependencia mueve el puntero. Sin devolverlo al
    principio, el `await file.read()` del endpoint devuelve **vacío** y el
    import entra **sin datos y sin fallar** — el P&L queda en cero y cuadra
    consigo mismo. Eso es mucho peor que no tener registro.
    """
    import inspect

    from app.importers import registro_dep

    fuente = inspect.getsource(registro_dep.registro_de_subida)
    assert "await up.seek(0)" in fuente
    assert fuente.index("await up.read()") < fuente.index("await up.seek(0)")


def test_un_dry_run_NO_se_registra():
    """⚠️ Una previsualización no importó nada. Anotarla como archivo entrado
    haría que el archivo real después chocara **contra su propia sombra** — y
    el owner vería «ya se importó» sin haber importado nunca."""
    import inspect

    from app.importers import registro_dep

    fuente = inspect.getsource(registro_dep.registro_de_subida)
    assert 'dry_run' in fuente
    assert fuente.index("dry_run") < fuente.index("request.form()")


def test_un_registro_roto_NO_puede_tumbar_una_carga_que_funcionaba():
    """⚠️ Esto es aditivo. Si el registro falla, el import SIGUE: lo que se
    pierde es la traza, no el dato. Un módulo nuevo que puede voltear el camino
    principal de actuales no es aditivo, es un riesgo."""
    import inspect

    from app.importers import registro_dep

    fuente = inspect.getsource(registro_dep.registro_de_subida)
    # El 409 del reimport SÍ se propaga; todo lo demás se traga.
    assert "except ErrorApi:" in fuente
    assert fuente.count("except Exception:") >= 2


def test_el_409_dice_CUANDO_y_QUIEN_no_solo_duplicado():
    """Un «duplicado» pelado no deja decidir. Quien lo recibe tiene que poder
    distinguir el mismo archivo por error del archivo corregido."""
    import inspect

    from app.importers import registro_dep

    fuente = inspect.getsource(registro_dep.registro_de_subida)
    assert "previa.creado_en" in fuente
    assert "previa.subido_por" in fuente
    assert "permitir_reimport=true" in fuente


# ── El agujero del NULL, que el constraint no cubre ─────────────────────────

def test_el_chequeo_real_es_el_SELECT_y_no_el_UNIQUE():
    """⚠️ **El defecto que esto documenta.** En Postgres dos NULL no chocan,
    así que `UNIQUE (hotel_id, scenario_id, checksum)` NO deduplica cuando el
    escenario viene vacío — y viene vacío en varias de las puertas.

    `== None` en SQLAlchemy se traduce a `IS NULL`, que sí compara. Si alguien
    lo cambia por `is None` en Python, el filtro deja de aplicarse y el
    anti-reimport se apaga en silencio.
    """
    import inspect

    from app.importers import registro

    fuente = inspect.getsource(registro.subida_previa)
    assert "ImportFile.scenario_id == scenario_id" in fuente
    assert "NULL" in fuente, "el docstring tiene que explicar por qué el UNIQUE no alcanza"


# ── La identidad de la propiedad ────────────────────────────────────────────

def test_las_tablas_usan_hotel_id_de_TEXTO_no_property_id_uuid():
    """⚠️ Decisión del owner (2026-08-19). El spec original pedía
    `property_id uuid FK → properties`: **no existe tal tabla**, es `hotels`
    con llave de texto, y FinPlan es una instalación por hotel, no
    multi-tenant."""
    from app.models.import_registro import ImportBatch, ImportFile

    for modelo in (ImportBatch, ImportFile):
        cols = {c.name: c for c in modelo.__table__.columns}
        assert "hotel_id" in cols, modelo.__tablename__
        assert "property_id" not in cols, modelo.__tablename__
        assert cols["hotel_id"].type.length == 10


def test_borrar_un_escenario_no_borra_la_traza_de_lo_que_se_importo():
    """`ondelete=SET NULL`, no CASCADE: es justo cuando más falta hace saber
    qué se había cargado."""
    from app.models.import_registro import ImportBatch

    fks = list(ImportBatch.__table__.c.scenario_id.foreign_keys)
    assert fks and fks[0].ondelete == "SET NULL"


def test_la_migracion_es_aditiva_y_reversible():
    """No toca ninguna tabla existente: sólo crea dos y sabe borrarlas."""
    p = os.path.join(RAIZ, "alembic", "versions",
                     "133_registro_de_importaciones.py")
    txt = io.open(p, encoding="utf-8").read()
    assert txt.count("create_table") == 2
    assert txt.count("drop_table") == 2
    for prohibido in ("drop_column", "alter_column", "drop_constraint"):
        assert prohibido not in txt, f"la migración usa {prohibido}: no es aditiva"


# ── La cobertura de las puertas ─────────────────────────────────────────────

def _rutas_de_subida() -> tuple[list[str], list[str]]:
    """(cubiertas, sin cubrir) — rutas que reciben un archivo.

    Se lee del DECORADOR, que es donde vive el enganche.
    """
    api = os.path.join(RAIZ, "app", "api")
    cubiertas: list[str] = []
    sin_cubrir: list[str] = []
    for a in sorted(os.listdir(api)):
        if not a.endswith(".py"):
            continue
        txt = io.open(os.path.join(api, a), encoding="utf-8").read()
        if "UploadFile" not in txt:
            continue
        lineas = txt.split("\n")
        for i, l in enumerate(lineas):
            m = re.match(r"async def (\w+)\(", l)
            if not m:
                continue
            # ⚠️ La firma se cierra contando PARÉNTESIS, no con una ventana de
            # N líneas. Con la ventana, un `export_*` que vive arriba de un
            # `import_*` se lleva el `UploadFile` del vecino y aparece como
            # puerta de subida sin serlo — daba seis falsos positivos.
            firma, abiertos = "", 0
            for k in range(i, min(i + 60, len(lineas))):
                firma += lineas[k] + "\n"
                abiertos += lineas[k].count("(") - lineas[k].count(")")
                if abiertos <= 0 and k > i:
                    break
            if "UploadFile" not in firma:
                continue
            j = i - 1
            while j >= 0 and not lineas[j].lstrip().startswith("@router."):
                j -= 1
            deco = "\n".join(lineas[max(j, 0):i])
            destino = cubiertas if "registro_de_subida" in deco else sin_cubrir
            destino.append(f"{a}:{m.group(1)}")
    return cubiertas, sin_cubrir


# ⚠️ `validate_upload` sólo VALIDA y no escribe. Registrarla haría que la
# subida real después chocara contra su propia validación.
NO_REGISTRAN = {"audit_api.py:validate_upload"}


def test_TODA_puerta_de_subida_QUE_ESCRIBE_registra_el_archivo():
    """⚠️ **La red completa.** El mecanismo es UNO —una dependencia en el
    decorador— así que la regla puede ser dura: una ruta nueva que reciba un
    archivo y no registre, falla acá.

    Antes esto era un contador que informaba sin fallar, porque la cobertura
    era de una puerta sobre veinticuatro. Un contador se justifica mientras la
    cobertura es parcial; cuando deja de serlo, se convierte en regla.
    """
    _cubiertas, sin_cubrir = _rutas_de_subida()
    faltan = [r for r in sin_cubrir if r not in NO_REGISTRAN]
    assert not faltan, (
        f"estas rutas reciben un archivo y NO lo registran: {faltan}. "
        f"Agregá `dependencies=[Depends(registro_de_subida)]` al decorador, o "
        f"anotalas en NO_REGISTRAN con el motivo")


def test_la_cobertura_no_puede_bajar():
    """Un refactor que desenganche rutas sin querer se ve acá."""
    cubiertas, _ = _rutas_de_subida()
    assert len(cubiertas) >= 23, (
        f"sólo {len(cubiertas)} rutas registran el archivo; eran 23")


@pytest.mark.parametrize("clave", ["import.ya_subido"])
def test_el_error_esta_en_los_dos_idiomas(clave):
    from app.errores import MENSAJES

    assert clave in MENSAJES
    assert set(MENSAJES[clave]) >= {"es", "en"}
