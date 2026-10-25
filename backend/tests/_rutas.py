# -*- coding: utf-8 -*-
r"""Dónde está cada cosa, calculado desde el repo.

**Por qué existe (2026-08-14).** Once archivos de prueba tenían la ruta
`C:\FinPlan_CWL` escrita a mano. En esta máquina funcionan; en cualquier otra
—incluido el CI que acabamos de encender— la ruta no resuelve y el archivo sale
vacío. Y como esas pruebas empiezan con «si no hay fuente, `return`», **pasaban
en verde sin haber mirado nada**: 60 pruebas que no protegían nada fuera de acá.

Todo se calcula desde `__file__`, así que funciona igual en Windows, en Linux y
en cualquier carpeta donde se clone el repo.
"""
import os
import pathlib

# .../repo/backend/tests/_rutas.py → parents[2] = el repo
RAIZ = pathlib.Path(__file__).resolve().parents[2]
BACKEND = RAIZ / "backend"
FRONT = RAIZ / "frontend"

# Los Excel de referencia están versionados en la raíz. `DATA_DIR` permite
# apuntarlos a otro lado sin tocar las pruebas.
DATOS = pathlib.Path(os.getenv("DATA_DIR") or RAIZ)


def sin_comentarios(fuente: str) -> str:
    """El código de un archivo TS/TSX, sin sus comentarios.

    **Por qué existe (2026-10-25).** Tres veces en un día una prueba marcó como
    defecto el comentario que explicaba por qué NO cometerlo:

        · `"nan" in texto`        acertó dentro de «Mainte**nan**ce»;
        · `"isFinite" not in src` acertó en el comentario que dice no usarlo;
        · `"useState(5)" not in`  acertó en el comentario que lo cuenta.

    Es el mismo error siempre: buscar una cadena en el ARCHIVO cuando se quiso
    buscarla en el CÓDIGO. Y falla en la dirección cara — la prueba se pone
    roja sola y la respuesta fácil es debilitarla.

    ⚠️ No es un parser: una `//` dentro de un string (`"https://…"`) se lleva
    el resto de la línea. Para buscar código alcanza y sobra; no sirve para
    reescribir el archivo.
    """
    import re

    sin_bloque = re.sub(r"/\*.*?\*/", "", fuente, flags=re.S)
    return re.sub(r"//[^\n]*", "", sin_bloque)
