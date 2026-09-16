# -*- coding: utf-8 -*-
"""Cuando «Pasar a Final» bloquea, el owner tiene que ver QUE no cuadra.

Owner, 2026-09-15: «aprete el boton y me dio este error». El mensaje decia que
los totales de control no coincidian con el detalle y que revisara «bucket por
bucket» — sin mostrar NINGUN bucket.

El informe existia: el backend lo manda en `detail.bloques`, con lo que declara
el archivo, lo que consolida el detalle y la diferencia, por control y por mes.
La pantalla de `import-actuals` ya lo dibujaba; la de Pre-Cierre lo tiraba.

Es el mismo patron que el error del espejo: el backend lo dice y el frontend no
lo lee. Por eso se vigila desde aca.
"""
import inspect
import io
import pathlib

FRONT = pathlib.Path(__file__).resolve().parents[2] / "frontend"


def test_el_backend_manda_el_informe_y_no_un_error_pelado():
    from app.api import scenarios_api
    src = inspect.getsource(scenarios_api.import_gl_detail)
    assert '"bloques"' in src and '"texto"' in src, (
        "el 409 tiene que traer el informe: el error ES el reporte")


def test_el_cliente_del_precierre_lo_reconoce():
    """`pasarPrecierreAFinal` tiraba el detalle y dejaba un mensaje generico."""
    src = io.open(FRONT / "lib" / "api.ts", encoding="utf-8").read()
    i = src.index("export async function pasarPrecierreAFinal")
    cuerpo = src[i:i + 2000]
    assert "ErrorDeVerificacion" in cuerpo, (
        "sin esto el owner ve «no coinciden» y no cual ni por cuanto")
    assert "detail?.bloques" in cuerpo or "detail?.bloques" in cuerpo


def test_la_pantalla_lo_dibuja():
    src = io.open(FRONT / "app" / "pre-cierre" / "page.tsx", encoding="utf-8").read()
    assert "ErrorDeVerificacion" in src
    assert "function Verificacion(" in src, (
        "tiene que haber un cuadro que lo muestre, no solo atraparlo")
    assert "setBloqueo" in src


def test_el_texto_manda_al_BOTON_y_no_a_un_parametro():
    """El backend dice «volve a subir con confirmar_diferencias=true», que es un
    parametro de query. En la pantalla hay un BOTON que hace exactamente eso, y
    mandar al owner a inventar una URL es mandarlo a ningun lado."""
    import json
    for loc in ("es", "en"):
        d = json.loads(io.open(FRONT / "messages" / f"{loc}.json",
                               encoding="utf-8").read())
        txt = d["precierre"]["verificacionQueHacer"]
        assert "confirmar_diferencias" not in txt, (
            f"[{loc}] el texto de la pantalla no puede mandar a un parametro de query")
        assert ("Pasar aunque" in txt) or ("Pass even if" in txt), (
            f"[{loc}] tiene que nombrar el boton que resuelve")
