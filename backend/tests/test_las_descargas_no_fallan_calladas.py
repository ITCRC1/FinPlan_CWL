# -*- coding: utf-8 -*-
"""Una descarga protegida se PIDE, no se navega con el token en la URL.

Owner, 2026-09-15: «no baja nada en el upload file».

`dlUrl` arma el link con el token que hay CUANDO SE DIBUJA la pantalla, y el
token vive 10 minutos de inactividad. Pasado ese rato el `<a href>` apunta a una
URL vencida: el backend contesta 401 en JSON, el navegador lo abre y no baja
nada — sin error, sin aviso, sin archivo.

Medido contra produccion el 2026-09-15:

    GET /api/precierre/x/detalle.xlsx?token=vencido  ->  401  application/json

Un 401 en JSON detras de un `<a download>` es invisible: el usuario ve que «no
pasa nada» y no tiene como saber que su sesion caduco.
"""
import io
import pathlib

FRONT = pathlib.Path(__file__).resolve().parents[2] / "frontend"


def _api() -> str:
    return io.open(FRONT / "lib" / "api.ts", encoding="utf-8").read()


def test_hay_una_forma_de_bajar_pidiendo_el_archivo():
    src = _api()
    assert "export async function bajarArchivo" in src
    i = src.index("export async function bajarArchivo")
    cuerpo = src[i:i + 1200]
    assert "authHeaders()" in cuerpo, (
        "el token tiene que leerse al hacer clic, no al dibujar la pantalla")
    assert "errorLegible" in cuerpo, "y el fallo tiene que verse"


def test_las_rutas_del_precierre_ya_no_llevan_el_token_incrustado():
    src = _api()
    i = src.index("export const precierreExcelUrl")
    cuerpo = src[i:i + 500]
    assert "dlUrl(" not in cuerpo, (
        "con `dlUrl` el token queda congelado en el href y se vence")


def test_la_pantalla_las_baja_pidiendolas():
    src = io.open(FRONT / "app" / "pre-cierre" / "page.tsx", encoding="utf-8").read()
    assert "bajarArchivo" in src
    assert "href={dl[k]}" not in src, "el `<a href>` con token es el defecto"
    assert "href={hojaExcelUrl}" not in src


def test_el_fallo_de_una_descarga_se_muestra():
    src = io.open(FRONT / "app" / "pre-cierre" / "page.tsx", encoding="utf-8").read()
    i = src.index("function Descargas(")
    cuerpo = src[i:i + 2000]
    assert "setFallo" in cuerpo, (
        "una descarga que falla en silencio es exactamente el defecto original")
