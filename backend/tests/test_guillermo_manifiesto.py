# -*- coding: utf-8 -*-
"""El manifiesto es POR PROPIEDAD — owner, 2026-08-20.

*«Cada propiedad decide cómo manejar a Guillermo.»*

Lo que se vigila acá es que **el manifiesto de CWL no se estampe sobre una
propiedad nueva**, y que la propiedad nueva tenga por dónde declarar el suyo.
"""
import inspect

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def cliente():
    return TestClient(app, raise_server_exceptions=False)


# ── El clonado ───────────────────────────────────────────────────────────────

def test_el_manifiesto_de_CWL_no_se_estampa_sobre_otra_propiedad():
    """⚠️ **El defecto que esto evita.** La lista se sembraba en CUALQUIER
    instalación. Al clonar para Amarena, Guillermo habría arrancado reclamando
    **cinco reportes que nadie de Amarena prometió** — el manifiesto inventado
    que el propio `seed_guillermo.py` dice que no se hace.
    """
    from app.seed_guillermo import MANIFIESTO_CWL, MANIFIESTOS

    assert MANIFIESTOS["CWL"] is MANIFIESTO_CWL
    for otro in ("AMA", "OXI", "OJO"):
        assert MANIFIESTOS.get(otro, []) == [], (
            f"{otro} heredaría el manifiesto de CWL")


def test_el_seed_lee_del_diccionario_y_no_de_una_lista_suelta():
    from app import seed_guillermo

    fuente = inspect.getsource(seed_guillermo.seed_manifiesto)
    assert "MANIFIESTOS.get(HOTEL_ID" in fuente
    # Y sin manifiesto no siembra nada, en vez de sembrar el de otro.
    assert "if not manifiesto" in fuente


def test_una_propiedad_nueva_nace_en_GRIS_y_no_en_ROJO():
    """⚠️ La segunda mitad del mismo defecto, y la más fea: `estado_visible`
    usa `configurado = esperados > 0`. Con el manifiesto de CWL sembrado, una
    instalación **recién nacida** salía en ROJO —«trabado»— el día cero, y una
    alarma que suena desde el día cero se aprende a ignorar.
    """
    from app.guillermo.core import estado_visible

    recien_instalado = estado_visible(
        latido_vencido_=True, motivo_latido="Guillermo nunca latió",
        pendientes=0, corriendo=False, nunca_arranco=True, configurado=False)
    assert recien_instalado.color == "gris"
    assert recien_instalado.state == "off"

    # Y en cuanto SU owner decide qué espera, no haber corrido sí es una falla.
    ya_decidio = estado_visible(
        latido_vencido_=True, motivo_latido="Guillermo nunca latió",
        pendientes=0, corriendo=False, nunca_arranco=True, configurado=True)
    assert ya_decidio.color == "rojo"


def test_CWL_conserva_su_manifiesto_completo():
    """El arreglo no puede quitarle a Corcovado lo que ya decidió el 20-ago."""
    from app.seed_guillermo import MANIFIESTO_CWL

    ids = {m[0] for m in MANIFIESTO_CWL}
    assert ids == {"actuales_gl", "balance_sheet", "otb_xml",
                   "country_xml", "channel_xml"}


# ── La puerta para declararlo ────────────────────────────────────────────────

def test_declarar_el_manifiesto_exige_el_rol():
    """⚠️ El manifiesto decide **qué reclama Guillermo**: agregar un reporte
    convierte su ausencia en excepción, y sacarlo lo vuelve invisible. Leerlo
    puede cualquiera; escribirlo no."""
    from app.api import guillermo_api

    assert "get_current_user" in inspect.getsource(guillermo_api.leer_manifiesto)
    for escribe in (guillermo_api.crear_esperado, guillermo_api.editar_esperado,
                    guillermo_api.borrar_esperado):
        assert "get_guillermo_approver" in inspect.getsource(escribe), escribe


def test_no_entra_una_forma_de_verificar_que_no_existe():
    """⚠️ Un valor fuera de la lista **no falla al guardar: falla al
    verificar**, y ahí se ve como «este reporte nunca está al día» sin decir
    por qué."""
    from app.api.guillermo_api import (FRECUENCIAS, VERIFICACIONES,
                                       ReporteEsperado, _valida)
    from fastapi import HTTPException

    ok = ReporteEsperado(report_id="x", objetivo="tabla",
                         frecuencia="monthly", verifica="cobertura")
    _valida(ok)                                   # no levanta

    for malo in (ReporteEsperado(report_id="x", objetivo="t", frecuencia="cada rato"),
                 ReporteEsperado(report_id="x", objetivo="t", verifica="a ojo"),
                 ReporteEsperado(report_id="x", objetivo="  "),
                 ReporteEsperado(report_id="  ", objetivo="t")):
        with pytest.raises(HTTPException) as e:
            _valida(malo)
        assert e.value.status_code == 400

    # Y las listas viajan al front, para que no las tenga que adivinar.
    assert set(VERIFICACIONES) >= {"cobertura", "ultima_subida", "actualizado"}
    assert set(FRECUENCIAS) == {"daily", "weekly", "monthly"}


def test_dos_reportes_con_el_mismo_id_dan_409_con_el_motivo():
    """Dos filas con el mismo `report_id` harían que Guillermo reclamara el
    mismo archivo dos veces."""
    from app.api import guillermo_api

    fuente = inspect.getsource(guillermo_api.crear_esperado)
    assert "409" in fuente and "ya está en el manifiesto" in fuente


def test_las_cuatro_puertas_existen_y_piden_token(cliente):
    """⚠️ Probar el ENDPOINT, no la función: un `Depends` equivocado tumba la
    pantalla con las pruebas en verde. Sin token tiene que dar 401/403, nunca
    500 ni 404."""
    # ⚠️ `app.routes` NO sirve para esto en esta versión de FastAPI: los
    # routers incluidos quedan envueltos en `_IncludedRouter` y no se aplanan.
    # Se mira el esquema, que es lo que de verdad se publica.
    rutas = cliente.app.openapi()["paths"]
    assert "/api/guillermo/manifiesto/" in rutas
    assert "/api/guillermo/manifiesto/{esperado_id}/" in rutas
    assert set(rutas["/api/guillermo/manifiesto/"]) == {"get", "post"}
    assert set(rutas["/api/guillermo/manifiesto/{esperado_id}/"]) == {"put", "delete"}

    # Y sin token ninguna abre.
    assert cliente.get("/api/guillermo/manifiesto/").status_code in (401, 403)
    assert cliente.post("/api/guillermo/manifiesto/",
                        json={"report_id": "x", "objetivo": "t"}
                        ).status_code in (401, 403)
    assert cliente.delete("/api/guillermo/manifiesto/loquesea/"
                          ).status_code in (401, 403)
