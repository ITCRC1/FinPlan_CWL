# -*- coding: utf-8 -*-
"""Los doce meses copiados en columna tienen que caer en los doce meses.

Owner, 2026-11-05, en el checkbook de costos: *«todavía no puedo hacer copy
paste»*.

## Lo que hacía, reproducido con sus datos

Levanté su pantalla en local —mismo escenario `Budget Working 2027`, mismo
departamento 0230, los datos traídos de producción— y pegué doce valores en
columna sobre enero de la cuenta 5701. Resultado:

    5701 enero = 11      (y febrero a diciembre vacíos)
    5702 enero = 22
    5703 enero = 33
    5704 enero = 44
    ...los otros ocho valores, descartados

O sea: **escribía plata en cuatro cuentas que el usuario no tocó** y no llenaba
ningún mes. Y en silencio. Desde afuera eso es exactamente «no se puede pegar».

## La regla

En esta grilla las columnas son meses. Un bloque de **una sola columna** pegado
sobre un mes son los meses de ESA línea, y se acuesta. Un bloque de varias
columnas ya trae su orientación puesta y no se toca: sigue bajando por las
filas, que es como se pega una tabla entera.

⚠️ Y **se dice en pantalla**. Acomodar solo una columna es magia, y la magia
que escribe plata no se perdona: la nota verde dice cuántos meses entraron y en
qué cuenta, así el usuario lo ve en el momento y no tres meses después en el
P&L.

## Por qué esta prueba compila el TypeScript

Las otras pruebas de `pegarGrilla.ts` leen el código. Ésta **corre la función**:
lo que estuvo mal no fue una palabra ausente en el archivo sino un reparto de
valores, y eso sólo se atrapa ejecutándolo. Verificado además a mano en la
pantalla levantada, con el pegado de verdad.
"""
import json
import pathlib
import shutil
import subprocess
import tempfile

import pytest

from tests._rutas import FRONT

PEGAR = FRONT / "lib" / "pegarGrilla.ts"
TSC = FRONT / "node_modules" / ".bin" / ("tsc.cmd" if shutil.which("cmd") else "tsc")


def _ejecutar(js_de_prueba: str):
    """Compila `pegarGrilla.ts` y corre un script de node contra él."""
    if not PEGAR.exists():
        pytest.skip(f"no está {PEGAR}")
    if not TSC.exists() or not shutil.which("node"):
        pytest.skip("hacen falta node y el tsc del frontend")
    with tempfile.TemporaryDirectory() as tmp:
        salida = pathlib.Path(tmp)
        r = subprocess.run(
            [str(TSC), str(PEGAR), "--target", "es2020", "--module", "commonjs",
             "--outDir", str(salida), "--skipLibCheck"],
            capture_output=True, text=True, timeout=180,
        )
        compilado = salida / "pegarGrilla.js"
        if not compilado.exists():
            pytest.skip(f"tsc no compiló: {r.stdout[-400:]}{r.stderr[-400:]}")
        guion = salida / "prueba.js"
        guion.write_text(
            f'const P = require({str(compilado).replace(chr(92), "/")!r});\n' + js_de_prueba,
            encoding="utf-8")
        r = subprocess.run(["node", str(guion)], capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, f"node falló: {r.stderr[-800:]}"
        return json.loads(r.stdout)


def test_una_columna_de_doce_se_acuesta():
    """El caso del owner, tal cual."""
    out = _ejecutar("""
      const bloque = ["11","22","33","44","55","66","77","88","99","110","121","132"]
        .map(v => [v]);
      const r = P.acostarColumna(bloque);
      console.log(JSON.stringify({ transpuesto: r.transpuesto, filas: r.bloque.length,
                                   fila: r.bloque[0] }));
    """)
    assert out["transpuesto"] is True
    assert out["filas"] == 1, "una columna tiene que quedar en UNA fila"
    assert out["fila"] == ["11", "22", "33", "44", "55", "66", "77", "88",
                           "99", "110", "121", "132"], "y en orden"


def test_un_bloque_de_varias_columnas_NO_se_toca():
    """Pegar una tabla entera sigue bajando por las filas."""
    out = _ejecutar("""
      const r = P.acostarColumna([["1","2","3"],["4","5","6"]]);
      console.log(JSON.stringify({ transpuesto: r.transpuesto, bloque: r.bloque }));
    """)
    assert out["transpuesto"] is False
    assert out["bloque"] == [["1", "2", "3"], ["4", "5", "6"]]


def test_una_sola_celda_NO_se_toca():
    """Una celda es escribir un número, no pegar una grilla."""
    out = _ejecutar("""
      const r = P.acostarColumna([["1054.50"]]);
      console.log(JSON.stringify({ transpuesto: r.transpuesto, bloque: r.bloque }));
    """)
    assert out["transpuesto"] is False
    assert out["bloque"] == [["1054.50"]]


def test_la_columna_con_su_rotulo_de_encabezado():
    """Arrastrando sobre Excel se va el rótulo adelante; se recorta y SIGUE
    siendo una columna de meses."""
    out = _ejecutar("""
      const crudo = P.celdasPegadas("Mes\\n11\\n22\\n33");
      const recortado = P.recortarRotulos(crudo);
      const r = P.acostarColumna(recortado);
      console.log(JSON.stringify({ transpuesto: r.transpuesto, fila: r.bloque[0] }));
    """)
    assert out["transpuesto"] is True
    assert out["fila"] == ["11", "22", "33"], "el rótulo se va, los tres meses quedan"


def test_la_pantalla_de_costos_la_usa_y_lo_dice():
    """El arreglo no sirve si la pantalla no lo llama, ni si lo hace callado."""
    src = (FRONT / "app" / "costs" / "checkbook" / "page.tsx").read_text(encoding="utf-8")
    assert "acostarColumna" in src, "la pantalla de costos no acuesta la columna"
    assert "pasteColumnaAcostada" in src, (
        "acomodar una columna sin decirlo es magia que escribe plata")
    for idioma in ("en", "es"):
        msgs = json.loads((FRONT / "messages" / f"{idioma}.json").read_text(encoding="utf-8"))
        for clave in ("pasteColumnaAcostada", "pasteOk"):
            assert clave in msgs["costs"], f"falta costs.{clave} en {idioma}.json"
