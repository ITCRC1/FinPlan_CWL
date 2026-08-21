# -*- coding: utf-8 -*-
"""
TODA PANTALLA CON UN CUADRO SE PUEDE BAJAR A EXCEL.

El encargo del dueño fue literal: «todo debe ser objetivo de poder bajar a Excel
con formatos profesionales». Esta prueba es la que decide si eso se cumplió, y
la que impide que la próxima pantalla nazca sin el botón.

Lee el código del frontend. No es elegante, pero es lo único que puede vigilar
una regla que vive repartida en ~60 archivos de React — y ya hubo un caso en
este repo (`test_un_hotel_por_instalacion`) donde este tipo de prueba encontró lo
que una revisión a ojo no.

Dos reglas:

1. **Nadie arma Excel en el navegador.** La librería `xlsx` que trae el frontend
   es la edición Community y NO escribe estilos de celda: negrita, relleno,
   bordes y formato de moneda son de la versión paga. Cualquier pantalla que la
   use está produciendo, por definición, un archivo sin formato.

2. **Toda pantalla con `<table>` ofrece descarga**, sea con el exportador
   genérico (`bajarCuadros`) o con un endpoint propio del backend.
"""
import pathlib
import re

import pytest

APP = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "app"

# Pantallas con `<table>` que a propósito NO bajan a Excel. Cada una con su
# motivo: sin motivo escrito, esto se convierte en el lugar donde se esconde el
# trabajo que no se hizo.
SIN_EXCEL_A_PROPOSITO = {
    "admin/users": "lista de usuarios — no es un cuadro financiero y llevaría correos a un archivo suelto",
    "operation-insight/on-the-books": "puerto fiel de Tab 8 de DAILY-OPS — el original exporta por Ctrl+P (Imprimir PDF), no Excel; se preservó tal cual, sin agregar algo que la fuente no tiene",
}

# Marcas de que la pantalla ofrece descarga: el exportador genérico, o un
# endpoint propio del backend (los checkbooks y el reporte del dueño ya tienen
# el suyo, hecho a medida, y no hay razón para migrarlos).
OFRECE_DESCARGA = ("bajarCuadros", "downloadExcel", "/export/", "Excel(", "ExcelUrl(")


def _paginas():
    for p in sorted(APP.rglob("page.tsx")):
        yield p.parent.relative_to(APP).as_posix(), p.read_text(encoding="utf-8", errors="ignore")


def test_nadie_arma_el_excel_en_el_navegador():
    """`xlsx` Community no escribe estilos: con esa librería el formato profesional
    es imposible por más código que se escriba."""
    culpables = [ruta for ruta, src in _paginas()
                 if re.search(r"""from\s+['"]xlsx['"]""", src)]
    assert not culpables, (
        "estas pantallas siguen armando el Excel en el navegador con SheetJS "
        "Community, que no escribe negrita, relleno, bordes ni formato de "
        f"moneda: {culpables}")


def test_toda_pantalla_con_cuadro_se_puede_bajar():
    faltan = []
    for ruta, src in _paginas():
        if "<table" not in src:
            continue
        if ruta in SIN_EXCEL_A_PROPOSITO:
            continue
        if not any(m in src for m in OFRECE_DESCARGA):
            faltan.append(ruta)
    assert not faltan, (
        f"{len(faltan)} pantallas muestran un cuadro y no lo dejan bajar: {faltan}")


def test_nadie_recalcula_sin_mirar_los_avisos():
    """El recálculo devuelve 200 aunque quede a medias.

    El servidor manda `avisos` cuando algo NO se pudo recalcular — un escenario
    sin tipo de cambio, una regla de reparto que no encuentra su origen, líneas
    en colones sin TC del mes. Siete pantallas ignoraban ese campo y ponían
    «✓ Recalculado» pase lo que pase, que es de dónde sale el reclamo de
    siempre: «apreté y no cambió nada». Había cambiado lo que se podía, y lo
    que no, no avisaba nadie.

    La regla no es «pasá por tal función»: es **quien llame, que lea**. Lo más
    cómodo es `recalcularYContar` o `<RecalcButton>`, que ya lo hacen; una
    pantalla que agrupa los avisos de varios escenarios a su manera también
    cumple, y ahí forzar el helper sería peor.
    """
    raiz = APP.parent
    culpables = []
    for p in sorted(raiz.rglob("*.ts*")):
        ruta = p.relative_to(raiz).as_posix()
        if ruta == "lib/api.ts" or "node_modules" in ruta or ".next" in ruta:
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        if "recalculateScenario" in src and "avisos" not in src:
            culpables.append(ruta)
    assert not culpables, (
        "llaman a recalculateScenario y nunca miran `avisos`: van a decir "
        "«✓ Recalculado» aunque el recálculo haya quedado a medias. Usá "
        f"`recalcularYContar` o `<RecalcButton>`: {culpables}")


@pytest.mark.parametrize("ruta", sorted(SIN_EXCEL_A_PROPOSITO))
def test_las_excepciones_siguen_existiendo(ruta):
    """Una excepción a una pantalla borrada es una excepción que ya no protege
    nada, y queda tapando el hueco de la que venga después con ese nombre."""
    assert (APP / ruta / "page.tsx").exists(), (
        f"{ruta} está en la lista de excepciones pero ya no existe: sacala")
