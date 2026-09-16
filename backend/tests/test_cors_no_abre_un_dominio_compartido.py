# -*- coding: utf-8 -*-
"""CORS no puede abrirse a un dominio COMPARTIDO con credenciales.

`allow_credentials=True` mas un comodin sobre `vercel.app` —o sobre
`up.railway.app`— significa que cualquier app de cualquier persona alojada en
ese dominio puede pedirle a esta API con la sesion de quien la abra.

El comodin de Vercel existia y el propio comentario del archivo lo marcaba como
«problema arrastrado». Se quito el 2026-09-16, cuando el frontend ya vivia en
Railway y ese origen habia dejado de ser la app.

Cada propiedad declara su frontend en `CORS_ORIGINS`, con la URL EXACTA.
"""
import io
import pathlib
import re

MAIN = pathlib.Path(__file__).resolve().parents[1] / "app" / "main.py"

#: Dominios donde cualquiera puede publicar. Un comodin sobre ellos no es un
#: permiso: es una puerta abierta.
COMPARTIDOS = ("vercel.app", "railway.app", "netlify.app", "pages.dev",
               "herokuapp.com", "onrender.com", "fly.dev")


def _codigo() -> str:
    """El archivo sin comentarios: lo que CORRE, no lo que explica."""
    src = io.open(MAIN, encoding="utf-8").read()
    return "\n".join(l for l in src.split("\n")
                     if not l.lstrip().startswith("#"))


def test_no_hay_comodin_sobre_un_dominio_compartido():
    codigo = _codigo()
    m = re.search(r"allow_origin_regex\s*=\s*(.+)", codigo)
    assert m is None, (
        f"CORS usa un regex de origenes ({m.group(1).strip() if m else ''}). "
        "Con allow_credentials=True eso abre la API a cualquier app del dominio")


def test_ningun_origen_fijo_vive_en_un_dominio_compartido():
    """`localhost` es la excepcion obvia: no es compartido con nadie."""
    codigo = _codigo()
    i = codigo.index("allow_origins=[")
    lista = codigo[i:codigo.index("]", i)]
    malos = [d for d in COMPARTIDOS if d in lista]
    assert not malos, (
        f"origen fijo en un dominio compartido: {malos}. La URL de cada "
        "propiedad va en CORS_ORIGINS, que es por despliegue")


def test_las_credenciales_siguen_encendidas():
    """No es que se apaguen: la app las necesita. Por eso importa lo de arriba —
    si algun dia se apagaran, este guard perderia su razon y hay que revisarlo."""
    assert "allow_credentials=True" in _codigo()


def test_cada_propiedad_declara_su_frontend():
    assert 'os.getenv("CORS_ORIGINS"' in _codigo()
