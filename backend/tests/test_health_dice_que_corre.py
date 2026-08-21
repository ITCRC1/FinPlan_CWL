# -*- coding: utf-8 -*-
"""`/health` dice qué propiedad, qué commit y qué migración están corriendo.

**El problema (owner, 2026-08-14).** Con cuatro despliegues del mismo repo, la
pregunta «¿el hotel 3 ya tiene el arreglo?» obligaba a entrar a Railway. Y un
despliegue atrasado no se delata solo: la app responde igual de bien con el
código de la semana pasada.

El caso feo es el desfase entre CÓDIGO y BASE. Si el commit trae una migración
que no corrió, la app arranca contra un esquema viejo y revienta en la primera
consulta que use la columna nueva — con un error de SQL que no menciona la
palabra «migración» por ningún lado.
"""
import asyncio
import pathlib
import re


def test_el_head_del_codigo_es_uno_solo():
    """Dos cabezas = el árbol de migraciones se bifurcó y `alembic upgrade head`
    no sabría cuál aplicar. Vale la pena que una prueba lo grite."""
    from app.version import head_del_codigo
    head = head_del_codigo()
    assert head, "no se pudo calcular la cabeza de las migraciones"
    assert "," not in head, (
        f"el árbol de migraciones tiene más de una cabeza: {head}. "
        "Hay que encadenarlas antes de desplegar."
    )


def test_el_head_se_calcula_del_arbol_y_no_de_una_constante():
    """Una constante escrita a mano se olvida en la migración siguiente."""
    from app.version import head_del_codigo
    versiones = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
    revs, padres = set(), set()
    rx_r = re.compile(r'^revision(?:\s*:[^=\n]+)?\s*=\s*["\']([^"\']+)["\']', re.M)
    rx_d = re.compile(r'^down_revision(?:\s*:[^=\n]+)?\s*=\s*["\']([^"\']+)["\']', re.M)
    for p in versiones.glob("*.py"):
        t = p.read_text(encoding="utf-8", errors="ignore")
        if (m := rx_r.search(t)):
            revs.add(m.group(1))
        if (d := rx_d.search(t)):
            padres.add(d.group(1))
    assert head_del_codigo() == sorted(revs - padres)[0]


def test_lee_las_dos_formas_de_escribir_la_revision():
    """El repo usa `revision = "104"` y `down_revision: Union[str, None] = "103"`.

    Ignorar la segunda daba CUATRO cabezas donde hay una — que es como se
    descubrió."""
    from app.version import _RE_REV, _RE_DOWN
    assert _RE_REV.search('revision = "104"').group(1) == "104"
    assert _RE_REV.search('revision: str = "104"').group(1) == "104"
    assert _RE_DOWN.search('down_revision: Union[str, None] = "103"').group(1) == "103"
    assert _RE_DOWN.search("down_revision = '103'").group(1) == "103"


def test_health_no_se_cae_si_la_base_no_contesta():
    """Un health check que muere con la base arrastra al balanceador y esconde
    justo el dato que se venía a buscar."""
    from app.main import health
    r = asyncio.run(health())
    assert r["status"] == "healthy"
    assert r["hotel_id"]
    assert r["alembic_codigo"]
    assert "migraciones_al_dia" in r


def test_health_no_filtra_nada_sensible():
    """Es público a propósito — se abre para comparar los cuatro despliegues —
    así que no puede llevar credenciales ni la URL de la base."""
    from app.main import health
    r = asyncio.run(health())
    texto = str(r).lower()
    for prohibido in ("password", "postgres://", "postgresql", "secret", "token", "@"):
        assert prohibido not in texto, f"/health está exponiendo «{prohibido}»"


def test_hay_integracion_continua():
    """La prueba que nadie corre no protege nada: fue exactamente lo que pasó con
    el `HOTEL_ID` sin importar, que vivió un día en producción en verde."""
    raiz = pathlib.Path(__file__).resolve().parents[2]
    flujos = list((raiz / ".github" / "workflows").glob("*.yml"))
    assert flujos, "no hay ningún workflow de CI"
    texto = "\n".join(f.read_text(encoding="utf-8") for f in flujos)
    assert "pytest" in texto, "el CI no corre las pruebas del backend"
    assert "tsc --noEmit" in texto, "el CI no revisa los tipos del frontend"
    assert "npm run build" in texto, "el CI no construye el frontend"
