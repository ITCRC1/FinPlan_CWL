# -*- coding: utf-8 -*-
"""EL AVISO DE LINEAS OBLIGATORIAS: que avise, que no bloquee, y que no mienta.

El par de `test_upload_viaje_redondo`: aquella cuida que los ACTUALES entren
bien; esta, que un PRESUPUESTO con agujeros se note antes de clonarlo.

Los tres modos de falla que se cuidan aca son los que costaron plata en agosto:

1. **Medir los doce meses de un forecast.** Un forecast toma sus meses cerrados
   del Actual enlazado. Si el aviso mira enero-junio de un `Working` con corte
   en 6, esta midiendo meses que este escenario no aporta — y ya paso una vez
   que eso hizo creer que el Working 2026 estaba desalineado cuando no lo estaba.
2. **Confundir «escenario vacio» con «escenario con agujeros».** Los ocho
   Working 2028-2035 estan enteros en cero. Escupir 33 avisos por cada uno
   sepulta los 9 reales del Working 2027.
3. **Que el aviso bloquee.** Un presupuesto se arma por partes durante semanas.
"""
import json

import pytest

from app.engine import lineas_obligatorias as obligatorias

TODOS = list(range(1, 13))


def _pl(codes_con_dato, meses=TODOS, monto=1000.0):
    """{mes: {line_code: monto}} con dato solo en los codigos que se pidan."""
    return {m: {c: monto for c in codes_con_dato} for m in meses}


# ── La lista ──────────────────────────────────────────────────────────────────

def test_la_lista_existe_y_tiene_lo_que_el_owner_midio():
    """Los seis agujeros del 2027 que el owner midio el 2026-08-16 estan."""
    codes = {L["line_code"] for L in obligatorias.lista()["lineas"]}
    for c in ("OH_UTILITIES", "COS_TOURS", "COS_TRANSPORTATION", "COS_RETAIL",
              "RENT", "PROPERTY_INSURANCE", "DEPRECIATION"):
        assert c in codes, f"{c} tiene historico y regla de mapeo: tiene que obligar"


def test_innoceana_no_obliga():
    """Innoceana facturo 141k en 2024 y 150k en 2025 — y **cero en 2026**.

    El proyecto termino. Sin el filtro de «sigue viva», cada escenario nuevo
    arrastraria para siempre el aviso de una linea que ya no existe, y el aviso
    que grita todos los dias es un aviso que nadie mira.
    """
    codes = {L["line_code"] for L in obligatorias.lista()["lineas"]}
    assert "REV_INNOCEANA" not in codes
    assert "OPEX_INNOCEANA" not in codes


def test_solo_lineas_donde_entra_dato():
    """Nada de CALCULATED ni de totales.

    Avisar de `TOTAL_DEPRECIATIONS` le dice al owner que algo falta pero no
    donde cargarlo. `DEPRECIATION` si.
    """
    codes = {L["line_code"] for L in obligatorias.lista()["lineas"]}
    assert not [c for c in codes if c.startswith("TOTAL_") or c.startswith("SEC_")]


def test_cada_linea_trae_su_magnitud_y_donde_cargarla():
    """La pregunta del owner es «que cargo y en que orden»: sin monto no hay orden."""
    for L in obligatorias.lista()["lineas"]:
        assert L["referencia_usd"], f"{L['line_code']} sin monto de referencia"
        assert L["historico"], f"{L['line_code']} sin historico"
        assert L["donde_se_carga"], f"{L['line_code']} no dice donde se carga"


def test_el_archivo_es_json_valido_y_no_se_lee_dos_veces():
    """`lista()` cachea; el archivo del repo tiene que ser el mismo objeto."""
    datos = json.loads(obligatorias.ARCHIVO.read_text(encoding="utf-8"))
    assert len(datos["lineas"]) == len(obligatorias.lista()["lineas"])
    assert obligatorias.lista() is obligatorias.lista()


# ── El aviso ──────────────────────────────────────────────────────────────────

def test_avisa_de_la_linea_en_cero():
    todas = [L["line_code"] for L in obligatorias.lista()["lineas"]]
    rep = obligatorias.revisar(_pl([c for c in todas if c != "OH_UTILITIES"]),
                               "BUDGET", 0)
    assert not rep["vacio"]
    assert [f["line_code"] for f in rep["faltan"]] == ["OH_UTILITIES"]
    assert rep["magnitud_historica_usd"] > 0


def test_no_avisa_cuando_estan_todas():
    todas = [L["line_code"] for L in obligatorias.lista()["lineas"]]
    rep = obligatorias.revisar(_pl(todas), "BUDGET", 0)
    assert rep["faltan"] == []
    assert "tienen dato" in obligatorias.resumen_texto(rep)


def test_las_faltantes_salen_de_mayor_a_menor():
    """El orden ES la respuesta: primero lo que mas plata mueve."""
    rep = obligatorias.revisar({}, "BUDGET", 0)
    montos = [abs(f["referencia_usd"]) for f in rep["faltan"]]
    assert montos == sorted(montos, reverse=True)


def test_un_escenario_entero_vacio_se_dice_una_sola_vez():
    """Los Working 2028-2035 no tienen agujeros: no estan empezados."""
    rep = obligatorias.revisar({m: {} for m in TODOS}, "BUDGET", 0)
    assert rep["vacio"] is True
    texto = obligatorias.resumen_texto(rep)
    assert "VACIO" in texto and "sin empezar" in texto


def test_el_aviso_nunca_bloquea():
    """No hay campo de bloqueo, y no lo puede haber.

    Es la diferencia con la verificacion del upload, que si bloquea sus cuatro
    controles. Un presupuesto se arma por partes: bloquear seria un estorbo y
    en una semana el owner lo apagaria.
    """
    rep = obligatorias.revisar({}, "BUDGET", 0)
    assert "bloquea" not in rep and "bloqueantes" not in rep


# ── El corte del rolling forecast ─────────────────────────────────────────────

def test_el_forecast_solo_se_revisa_en_los_meses_que_aporta():
    """Corte en 6: enero-junio salen del Actual enlazado, no de este escenario.

    Con dato SOLO en enero-junio, el forecast no aporta nada — y el aviso tiene
    que decirlo, no darlo por bueno.
    """
    todas = [L["line_code"] for L in obligatorias.lista()["lineas"]]
    rep = obligatorias.revisar(_pl(todas, meses=list(range(1, 7))), "FORECAST", 6)
    assert rep["meses_revisados"] == list(range(7, 13))
    assert rep["meses_no_revisados"] == list(range(1, 7))
    assert rep["vacio"] is True, "los meses cerrados no cuentan como dato del forecast"


def test_un_budget_se_revisa_completo():
    rep = obligatorias.revisar({}, "BUDGET", 0)
    assert rep["meses_revisados"] == TODOS
    assert rep["meses_no_revisados"] == []


def test_un_forecast_sin_corte_se_revisa_completo():
    rep = obligatorias.revisar({}, "FORECAST", 0)
    assert rep["meses_revisados"] == TODOS


# ── Que no invente ────────────────────────────────────────────────────────────

def test_un_residuo_de_redondeo_no_es_dato():
    todas = [L["line_code"] for L in obligatorias.lista()["lineas"]]
    rep = obligatorias.revisar(_pl(todas, monto=0.0001), "BUDGET", 0)
    assert rep["cuantas_faltan"] == len(todas)


def test_una_linea_negativa_si_es_dato():
    """`OH_CAFETERIA` es el credito del reparto: viene en negativo y esta cargada."""
    rep = obligatorias.revisar(_pl(["OH_CAFETERIA"], monto=-500.0), "BUDGET", 0)
    assert "OH_CAFETERIA" not in [f["line_code"] for f in rep["faltan"]]


def test_no_toca_nada():
    """Modulo puro: revisar dos veces da lo mismo y no muta la lista."""
    antes = json.dumps(obligatorias.lista(), sort_keys=True)
    obligatorias.revisar(_pl(["REV_ROOMS"]), "BUDGET", 0)
    assert json.dumps(obligatorias.lista(), sort_keys=True) == antes


@pytest.mark.parametrize("tipo", ["ACTUAL", "BUDGET", "FORECAST"])
def test_no_revienta_con_entrada_vacia(tipo):
    rep = obligatorias.revisar({}, tipo, None)
    assert rep["hay_lista"] is True
    assert isinstance(obligatorias.resumen_texto(rep), str)


# ── La puerta ─────────────────────────────────────────────────────────────────
#
# El 2026-08-16 el router se escribio con `Depends(get_session)` y `get_session`
# es un `@asynccontextmanager`, no una dependencia de FastAPI. Las tres rutas
# quedaban registradas —el `/openapi.json` de produccion las mostraba— y la que
# tocaba la base devolvia 500 al primer clic. Se descubrio probandola, no
# leyendola. Esto lo prueba en un segundo.

@pytest.fixture(scope="module")
def cliente():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.lineas_obligatorias_api import router
    from app.db import get_db

    class _Res:
        def scalars(self):
            return self

        def all(self):
            return []

    class _DB:
        async def execute(self, *a, **k):
            return _Res()

        async def get(self, *a, **k):
            return None

    app = FastAPI()
    app.include_router(router, prefix="/api")

    async def _db():
        yield _DB()

    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def test_la_lista_se_puede_pedir(cliente):
    r = cliente.get("/api/lineas-obligatorias/lista/")
    assert r.status_code == 200
    assert len(r.json()["lineas"]) == len(obligatorias.lista()["lineas"])


def test_el_reporte_resuelve_la_sesion(cliente):
    """Si la dependencia de base esta mal cableada, esto da 500."""
    r = cliente.get("/api/lineas-obligatorias/reporte/")
    assert r.status_code == 200, r.text
    assert r.json()["escenarios"] == []


def test_lista_y_reporte_no_se_leen_como_un_id(cliente):
    """`/{scenario_id}/` va ULTIMA, o se traga las otras dos rutas."""
    assert cliente.get("/api/lineas-obligatorias/lista/").json().get("lineas") is not None
    assert "escenarios" in cliente.get("/api/lineas-obligatorias/reporte/").json()
    assert cliente.get("/api/lineas-obligatorias/no-existe/").status_code == 404
