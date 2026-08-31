# -*- coding: utf-8 -*-
"""
LOS DOS VOCABULARIOS DE CANAL TIENEN QUE ENCONTRARSE.

Los canales del PMS (KPI groups, `market_codes.canal`) y las filas del reporte
de mix (`seed_data/<HOTEL_ID>/canales_mix.json`) son DOS listas distintas para
lo mismo. Hasta el 2026-08-30 el importador del XML guardaba la primera en un
campo que el reporte lee con la segunda: las noches importadas caian en filas
nuevas —«Travel Agent»— y las de siempre —«Travel Agency»— se quedaban en cero.

**El total del mes seguia cuadrando.** Se vio al cargar junio 2026: de los
cuatro canales, solo `OTA` parecia actualizarse, porque es el unico nombre que
existe igual en los dos lados.

Y el mismo dia el owner agrego `Grupos Directos` y decidio CORP y GRP, que
llevaban dos semanas sin canal y por lo tanto sin cargar sus noches.
"""
import json
import pathlib

import pytest

from app.models.market_code import (CANALES, CANAL_A_COMISION, CANAL_A_MIX,
                                    canal_del_mix)

SEED = pathlib.Path(__file__).resolve().parents[1] / "app" / "seed_data"


def _mix_cwl() -> list[str]:
    return json.loads((SEED / "CWL" / "canales_mix.json").read_text(encoding="utf-8"))["canales"]


def _codigos() -> list[dict]:
    return json.loads((SEED / "market_codes.json").read_text(encoding="utf-8"))["codigos"]


# ── El puente entre los dos vocabularios ─────────────────────────────────────

@pytest.mark.parametrize("canal", CANALES)
def test_todo_canal_del_pms_sabe_a_que_fila_del_mix_va(canal):
    """Si un canal no esta en el puente, sus noches se van a una fila inventada."""
    assert canal in CANAL_A_MIX, (
        f"«{canal}» no tiene fila de mix: sus noches crearian una fila nueva y "
        f"la fila real del reporte se quedaria en cero, con el total cuadrando.")


@pytest.mark.parametrize("canal", CANALES)
def test_la_fila_destino_existe_de_verdad_en_el_reporte(canal):
    """No basta con mapear: el destino tiene que ser una fila que el mix tenga."""
    destino = CANAL_A_MIX[canal]
    assert destino in _mix_cwl(), (
        f"«{canal}» apunta a «{destino}», que no esta en canales_mix.json. "
        f"Filas del reporte: {_mix_cwl()}")


def test_lo_desconocido_pasa_derecho_sin_perderse():
    """Otra propiedad con otras filas de mix no se rompe: pasa con su nombre."""
    assert canal_del_mix("Un Canal De Otra Propiedad") == "Un Canal De Otra Propiedad"
    assert canal_del_mix("") == ""


def test_direct_client_y_website_caen_en_la_misma_fila():
    """La agrupacion del owner: el mix tiene CUATRO filas y el PMS cinco canales."""
    assert canal_del_mix("Direct Client") == canal_del_mix("Website") == "Direct Client + Website"


def test_ota_es_el_unico_que_se_llama_igual_en_los_dos_lados():
    """Por eso era el unico que parecia actualizarse cuando el bug estaba vivo."""
    iguales = [c for c in CANALES if canal_del_mix(c) == c]
    assert set(iguales) == {"OTA", "Grupos Directos"}


# ── El canal nuevo ───────────────────────────────────────────────────────────

def test_grupos_directos_es_un_canal():
    assert "Grupos Directos" in CANALES


def test_grupos_directos_no_paga_comision_de_intermediario():
    """Es «directo»: rueda a DIRECT, como ya decia el mixer del owner."""
    assert CANAL_A_COMISION["Grupos Directos"] == "DIRECT"


def test_grupos_directos_es_una_fila_APARTE_del_directo():
    """El owner: «no, aparte, ese es grupo, otro concepto»."""
    assert canal_del_mix("Grupos Directos") == "Grupos Directos"
    assert canal_del_mix("Grupos Directos") != "Direct Client + Website"


def test_la_fila_nueva_se_agrego_AL_FINAL():
    """La nota del seed: la grilla escribe POR POSICION. Meterla en medio
    correria las noches ya guardadas al canal de al lado, sin avisar."""
    canales = _mix_cwl()
    assert canales[-1] == "Grupos Directos"
    assert canales[:4] == ["Travel Agency", "Direct Client + Website",
                           "OTA", "Other / In-House"], (
        "las cuatro filas originales se movieron de lugar: las noches guardadas "
        "se correrian al canal de al lado")


@pytest.mark.parametrize("canal", CANALES)
def test_todo_canal_rueda_a_un_canal_de_comision(canal):
    """Un canal fuera de `CANAL_A_COMISION` no entra al Net Factor: su plata
    desaparece del calculo de comision sin que nada avise."""
    assert CANAL_A_COMISION.get(canal) in ("TA", "OTA", "DIRECT")


# ── CORP y GRP ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code,canal", [("CORP", "Travel Agent"),
                                        ("GRP", "Grupos Directos")])
def test_los_dos_codigos_que_faltaban_ya_tienen_canal(code, canal):
    """Sin canal, el importador los deja en `sin_canal` y NO carga sus noches."""
    por_code = {c["code"]: c["canal"] for c in _codigos()}
    assert por_code[code] == canal


def test_ningun_market_code_quedo_sin_canal():
    """Hoy no queda ninguno. Si alguien agrega uno nuevo sin decidirlo, esto
    falla y lo obliga a decidirlo — no a que sus noches se pierdan calladas."""
    sin = [c["code"] for c in _codigos() if not (c.get("canal") or "").strip()]
    assert not sin, f"market codes sin canal: {sin}. Sus noches no se cargarian."


@pytest.mark.parametrize("c", _codigos())
def test_todo_canal_del_seed_es_un_canal_valido(c):
    canal = (c.get("canal") or "").strip()
    assert not canal or canal in CANALES, f"{c['code']}: «{canal}» no es un canal"


# ── La migracion no puede desincronizarse del codigo ─────────────────────────

def test_la_migracion_137_dice_lo_mismo_que_el_codigo():
    """La 137 lleva su propia copia del puente —una migracion no importa del
    codigo vivo, que cambia—. Esta prueba las mantiene diciendo lo mismo."""
    import importlib.util
    ruta = (pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
            / "137_grupos_directos_y_fila_del_mix.py")
    spec = importlib.util.spec_from_file_location("m137", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    # La migracion solo lista los que CAMBIAN de nombre; los que se llaman igual
    # no tienen nada que mover.
    cambian = {k: v for k, v in CANAL_A_MIX.items() if k != v}
    assert m.A_MIX == cambian, (
        f"la migracion 137 y CANAL_A_MIX se separaron: {m.A_MIX} vs {cambian}")
    assert m.CANAL_DE == {"CORP": "Travel Agent", "GRP": "Grupos Directos"}
