# -*- coding: utf-8 -*-
"""El Budget Package en vivo: la llave que lo abre y la grilla que devuelve.

Owner, 2026-11-06: *«automatiza este [Budget Package] de una, así como está…
cada tab»*, y sí, con la plantilla por posición y su sueldo.

## Qué defiende este archivo

1. **La llave es OTRA que la del consolidado y abre SÓLO lo que el paquete
   lee.** Abre la plantilla con sueldos: si abriera cualquier ruta, o si sirviera
   para escribir, sería una contraseña de administrador escrita en un Excel.
2. **Nace apagada.** Sin `PAQUETE_API_KEY` no hay ninguna llave válida.
3. **La grilla es la del exportador de siempre**, celda por celda: el Excel que
   se refresca no puede parecerse menos al libro del botón.
"""
import asyncio
import inspect
import io
import pathlib

import pytest
from openpyxl import load_workbook

from app import auth
from app.api import export_api
from app.errores import ErrorApi
from app.export.cuadro_excel import build_cuadros_workbook
from app.export.grilla import grilla_de_libro


class _Ruta:
    def __init__(self, path):
        self.path = path


class _Pedido:
    """Lo mínimo de un `Request` que mira la dependencia."""

    def __init__(self, metodo, plantilla):
        self.method = metodo
        self.scope = {"route": _Ruta(plantilla)}
        self.url = type("U", (), {"path": plantilla})()


def _entrar(monkeypatch, llave_env, llave, metodo, ruta):
    if llave_env is None:
        monkeypatch.delenv("PAQUETE_API_KEY", raising=False)
    else:
        monkeypatch.setenv("PAQUETE_API_KEY", llave_env)
    return asyncio.run(auth.get_current_user(
        request=_Pedido(metodo, ruta), authorization="", token=None,
        x_paquete_key=llave, db=None))


def test_la_llave_abre_las_rutas_del_paquete(monkeypatch):
    for metodo, ruta in auth.RUTAS_DEL_PAQUETE:
        # ⚠️ Con y sin `/api`: la ruta del router llega SIN el prefijo con que
        # la monta `main.py` (medido con TestClient el 2026-11-06: la llave
        # buena contestaba 401 en todas las rutas).
        for plantilla in (ruta, ruta.removeprefix("/api")):
            u = _entrar(monkeypatch, "secreto-largo", "secreto-largo", metodo, plantilla)
            assert u.id == auth.LECTOR_DEL_PAQUETE_ID
            assert u.role == "viewer"


def test_sin_variable_no_existe_ninguna_llave(monkeypatch):
    with pytest.raises(ErrorApi) as e:
        _entrar(monkeypatch, None, "cualquiera", "GET", "/api/payroll/posiciones/")
    assert e.value.status_code == 401


def test_la_llave_parecida_no_abre(monkeypatch):
    with pytest.raises(ErrorApi):
        _entrar(monkeypatch, "secreto-largo", "secreto-larg0", "GET",
                "/api/payroll/posiciones/")


@pytest.mark.parametrize("metodo,ruta", [
    ("GET", "/api/users/"),                          # fuera del paquete
    ("POST", "/api/scenarios/"),                     # escribir, aunque sea la misma ruta
    ("PUT", "/api/payroll/{scenario_id}/position/{id}/"),
    ("DELETE", "/api/scenarios/{scenario_id}/"),
])
def test_la_llave_NO_abre_nada_mas(monkeypatch, metodo, ruta):
    """⚠️ Una llave que abriera cualquier ruta sería una contraseña de
    administrador pegada en un Excel que se manda por correo."""
    with pytest.raises(ErrorApi) as e:
        _entrar(monkeypatch, "secreto-largo", "secreto-largo", metodo, ruta)
    assert e.value.status_code == 401


def test_la_unica_escritura_es_la_grilla_que_no_toca_la_base():
    escrituras = {r for m, r in auth.RUTAS_DEL_PAQUETE if m != "GET"}
    assert escrituras == {"/api/export/cuadros/grilla/"}
    fuente = inspect.getsource(export_api.grilla_de_cuadros)
    assert "db" not in fuente.split("):", 1)[0], "la grilla no recibe sesión de base"


def test_es_otra_llave_que_la_del_consolidado():
    fuente = inspect.getsource(auth.llave_del_paquete_valida)
    assert "PAQUETE_API_KEY" in fuente and "CONSOLIDADO_API_KEY" not in fuente


def test_llamada_a_mano_sin_cabecera_no_se_confunde_con_llave():
    """`lector_del_consolidado` llama a `get_current_user` sin la cabecera: lo
    que recibe es el `Header(...)` por defecto, que es un objeto verdadero."""
    with pytest.raises(ErrorApi) as e:
        asyncio.run(auth.get_current_user(authorization="", db=None))
    assert e.value.clave == "auth.no_autenticado"


CUADROS = [
    {"titulo": "Planning Report 2027 · Consolidado", "hoja": "Planning Consolidado",
     "columnas": [{"label": "Line Item", "formato": "texto"},
                  {"label": "Ene"}, {"label": "Feb"}, {"label": "Full Year"},
                  {"label": "Var %", "formato": "pct"}],
     "filas": [
         {"label": "REVENUES", "es_total": True, "valores": []},
         {"label": "Rooms", "nivel": 1, "valores": [100.5, 200, 300.5, 0.12]},
         {"label": "F&B", "nivel": 1, "valores": [10, 20, 30, -0.05]},
         {"label": "TOTAL", "es_total": True, "valores": [110.5, 220, 330.5, 0.1]},
     ]},
    {"titulo": "Estadísticas", "columnas": [{"label": "Stat", "formato": "texto"},
                                            {"label": "Ene", "formato": "num"}],
     "filas": [{"label": "Noches", "valores": [930]}]},
]


def test_la_grilla_es_el_libro_del_exportador_celda_por_celda():
    libro = build_cuadros_workbook(CUADROS)
    g = grilla_de_libro(libro)
    wb = load_workbook(io.BytesIO(libro), data_only=True)
    assert [h["nombre"] for h in g["hojas"]] == wb.sheetnames
    for h in g["hojas"]:
        ws = wb[h["nombre"]]
        for r, fila in enumerate(h["valores"], 1):
            for c, v in enumerate(fila, 1):
                o = ws.cell(r, c).value
                if isinstance(v, str):
                    v = v.lstrip(" ")
                assert v == o, (h["nombre"], r, c)


def test_la_grilla_lleva_estilo_formato_y_sangria():
    g = grilla_de_libro(build_cuadros_workbook(CUADROS))
    hoja = next(h for h in g["hojas"] if h["nombre"] == "Planning Consolidado")
    fila_rooms = next(f for f in hoja["valores"] if f[0] and f[0].strip() == "Rooms")
    assert fila_rooms[0].startswith(" "), "la sangría del detalle se perdió"
    r = hoja["valores"].index(fila_rooms)
    est = g["estilos"][hoja["estilos"][r][4]]
    assert est["formato"] and "%" in est["formato"], "la columna de % perdió su formato"
    total = next(i for i, f in enumerate(hoja["valores"]) if f[0] == "TOTAL")
    assert g["estilos"][hoja["estilos"][total][1]]["negrita"], "el total perdió la negrita"
    assert hoja["congelar"]


def test_la_ruta_del_frontend_exige_la_llave():
    ruta = (pathlib.Path(__file__).resolve().parents[2]
            / "frontend/app/api/paquete/route.ts").read_text(encoding="utf-8")
    assert 'req.headers.get("x-paquete-key")' in ruta
    assert "timingSafeEqual" in ruta
    assert "PAQUETE_API_KEY" in ruta
