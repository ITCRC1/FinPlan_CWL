# -*- coding: utf-8 -*-
"""Antes de clonar: nada puede asumir que la propiedad es Corcovado.

Owner, 2026-08-20: *«voy a prepararme para clonar, revisá todo»*.

`app/hotel_actual.py` existe justamente porque había «20 literales `CWL`
repartidos por la API»: en Corcovado son inofensivos, en un despliegue de
Amarena cada uno es **una fila estampada con el hotel equivocado**. Esta prueba
es la que impide que vuelvan.
"""
import pathlib
import re

FUENTE = pathlib.Path(__file__).resolve().parents[1] / "app"

#: Dónde «CWL» es legítimo: el módulo de identidad lo usa como default del
#: entorno, el seed compara contra él, y los datos sembrados de Corcovado viven
#: en su propia carpeta.
PERMITIDOS = {
    "hotel_actual.py",   # el default del entorno y su explicación
    "seed.py",           # `if HOTEL_ID != "CWL"` — no estampa, COMPARA
    "seed_guillermo.py", # MANIFIESTOS: el manifiesto de CWL, por hotel
}


def _archivos():
    for p in FUENTE.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        yield p


def test_ningun_literal_CWL_suelto_fuera_de_los_permitidos():
    """⚠️ Un literal suelto no falla al clonar: **guarda bien, en el hotel
    equivocado**."""
    culpables = []
    for p in _archivos():
        if p.name in PERMITIDOS:
            continue
        texto = p.read_text(encoding="utf-8")
        # Sólo el literal como VALOR, no el que aparece en un comentario.
        for linea in texto.splitlines():
            sin_comentario = linea.split("#")[0]
            if re.search(r'=\s*"CWL"|\(\s*"CWL"\s*[,)]', sin_comentario):
                culpables.append(f"{p.relative_to(FUENTE)}: {linea.strip()[:70]}")
    assert not culpables, (
        "Estos asumen Corcovado. Usá `HOTEL_ID` de `app/hotel_actual.py`:\n  "
        + "\n  ".join(culpables))


def test_owners_q_usa_la_entidad_DE_LA_INSTALACION():
    """⚠️ Tenía ocho endpoints con «CWL» clavado. Al clonar, Amarena habría
    guardado su capacidad y sus fotos del reporte bajo la entidad de
    Corcovado."""
    from app.api import owners_q_api

    fuente = pathlib.Path(owners_q_api.__file__).read_text(encoding="utf-8")
    assert 'entidad: str = "CWL"' not in fuente
    assert "entidad: str = HOTEL_ID" in fuente
    assert "from app.hotel_actual import HOTEL_ID" in fuente


def test_el_chequeo_MIRA_las_tablas_que_van_por_entidad():
    """⚠️ El control de contaminación pregunta `WHERE hotel_id <> :h`, y las
    tablas de Owners Q **no tienen `hotel_id`**: se llavean por `entidad`. Nunca
    las miró."""
    from app.api.chequeo_api import CON_ENTIDAD

    assert set(CON_ENTIDAD) >= {"capacidad", "report_snapshots"}
    from app.api import chequeo_api
    fuente = pathlib.Path(chequeo_api.__file__).read_text(encoding="utf-8")
    assert "WHERE entidad <> :h" in fuente


def test_el_manifiesto_de_Guillermo_es_POR_PROPIEDAD():
    """Amarena no hereda los cinco reportes que prometió Corcovado."""
    from app.seed_guillermo import MANIFIESTOS

    assert MANIFIESTOS.get("AMA", []) == []
    assert MANIFIESTOS["CWL"]


def test_el_tarifario_rack_de_otra_propiedad_NO_revienta():
    """Una propiedad sin `seed_data/<HOTEL>/rack_rates.json` abre la pantalla
    vacía, que es la verdad — no un error."""
    from app import seed_costos_grupos as scg

    fuente = pathlib.Path(scg.__file__).read_text(encoding="utf-8")
    assert "if not ARCHIVO_RACK.exists():" in fuente
    assert "return []" in fuente


def test_la_identidad_se_puede_RENOMBRAR_desde_la_app():
    """«Ocupo nombrar ese otro hotel»: hay endpoint, y es de admin."""
    from app.api import provisioning_api

    import inspect
    fuente = inspect.getsource(provisioning_api.cambiar_identidad)
    assert "get_current_admin" in fuente
    assert "hotel.name = nombre" in fuente
