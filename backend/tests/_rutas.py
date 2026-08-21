# -*- coding: utf-8 -*-
"""Dónde está cada cosa, calculado desde el repo.

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
