# -*- coding: utf-8 -*-
"""La configuración que re-expresa los reportes vive en Admin y se escribe con admin.

Owner, 2026-08-20: *«evaluá si acá deberíamos mover tabs a admin para proteger
la información, y favor moverlos a admin»* · *«la idea es que cuando llegue a
cada hotel se va a reestablecer la protección»*.

⚠️ **La protección va en el CÓDIGO, no en configuración por propiedad.** Así
cada clon nace protegido sin que nadie tenga que acordarse de reestablecerla —
que es exactamente lo que el owner pidió.
"""
import inspect
import pathlib

from fastapi.testclient import TestClient

from app.main import app

NAV = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "components"
       / "TopNav.tsx")

#: Lo que se movió a Admin. El criterio no es «es difícil»: es que **cambiarlo
#: mueve lo que todos leen**.
EN_ADMIN = ["accountMapping", "setupCuenta", "departamentos", "provisioning",
            "chequeo", "lineasObligatorias"]


def _grupo(texto: str, clave: str) -> str:
    ini = texto.index(f'key: "{clave}",')
    fin = texto.index("\n  },", ini)
    return texto[ini:fin]


def test_la_configuracion_esta_en_ADMIN_y_no_en_master_data():
    texto = NAV.read_text(encoding="utf-8")
    admin = _grupo(texto, "admin")
    master = _grupo(texto, "masterData")
    for clave in EN_ADMIN:
        assert f'key: "{clave}"' in admin, f"{clave} no está en Admin"
        assert f'key: "{clave}"' not in master, f"{clave} quedó también en Master Data"


def test_master_data_conserva_el_trabajo_DE_TODOS_LOS_DIAS():
    """No se movió todo: el tipo de cambio, los sets de habitación, las
    estadísticas y el mixer son carga y planificación, no configuración del
    grupo. Esconderlos habría trabado el trabajo diario sin proteger nada."""
    master = _grupo(NAV.read_text(encoding="utf-8"), "masterData")
    for clave in ("exchangeRate", "roomSets", "statistics", "canales"):
        assert f'key: "{clave}"' in master, clave


def test_ESCRIBIR_el_mapeo_exige_admin():
    """⚠️ **Lo que protege de verdad.** Estar en Admin es navegación: la ruta
    sigue respondiendo. Medido el 2026-08-20: los cinco endpoints de escritura
    del mapeo no pedían nada más que sesión — y acá **mover UNA cuenta de $6.500
    re-expresó 102 líneas del reporte**, con `foto_pl_totales` diciendo
    «IDÉNTICO»."""
    from app.api import mapping_api

    fuente = pathlib.Path(mapping_api.__file__).read_text(encoding="utf-8")
    assert fuente.count("dependencies=[Depends(get_current_admin)]") == 5
    assert "from app.auth import get_current_admin" in fuente


def test_LEER_el_mapeo_sigue_abierto():
    """Entender por qué una cuenta cae donde cae es trabajo de todos los días;
    esconderlo obligaría a preguntar en vez de mirar."""
    rutas = app.openapi()["paths"]
    lectura = [p for p in rutas
               if p.startswith("/api/mapping/") and "get" in rutas[p]]
    assert lectura, "no quedó ninguna lectura del mapeo"


def test_la_proteccion_VIAJA_CON_EL_CODIGO():
    """⚠️ Owner: «cuando llegue a cada hotel se va a reestablecer la
    protección». Si esto viviera en una tabla de configuración por propiedad,
    un clon nacería ABIERTO y habría que acordarse de cerrarlo. Al estar en el
    decorador, cada clon nace protegido."""
    from app.api import mapping_api

    fuente = pathlib.Path(mapping_api.__file__).read_text(encoding="utf-8")
    # No depende de ninguna tabla ni de ningún flag por hotel.
    assert "tab_enablement" not in fuente
    assert "@router.post" in fuente and "get_current_admin" in fuente


def test_un_colaborador_NO_puede_escribir_el_mapeo():
    """La puerta responde 401/403 sin sesión, y el `Depends` es de admin —
    probar el ENDPOINT, no la función."""
    cliente = TestClient(app, raise_server_exceptions=False)
    r = cliente.post("/api/mapping/accounts/", json={})
    assert r.status_code in (401, 403), r.status_code


def test_queda_ANOTADO_lo_que_sigue_abierto():
    """Medido: catálogo de departamentos (2 escrituras), estadísticas (2) y
    mixer (7) siguen sin exigir admin. Cerrarlos traba trabajo diario, así que
    es decisión del owner — pero no puede quedar sin escribir."""
    pend = (pathlib.Path(__file__).resolve().parents[2] / "docs"
            / "PENDIENTES.md").read_text(encoding="utf-8")
    assert "mixer" in pend.lower() or "sin exigir admin" in pend.lower()


def test_NINGUNA_entrada_de_la_barra_esta_DUPLICADA():
    """⚠️ **El defecto que esto evita, y ya ocurrió.** Al mover la
    configuración a Admin el 2026-08-20 quedaron TRES entradas repetidas
    —mapeo, setup de la cuenta y provisionamiento— porque Admin ya las tenía
    más abajo. La prueba anterior sólo comprobaba que estuvieran en Admin y no
    en Master Data: presencia, no unicidad. Un menú con la misma entrada dos
    veces no falla, se ve descuidado y hace dudar de cuál de las dos abre otra
    cosa.
    """
    import collections
    import re

    texto = NAV.read_text(encoding="utf-8")
    culpables = []
    for grupo in re.finditer(r'key: "(\w+)",\n    items: \[(.*?)\n    \],', texto, re.S):
        nombre, cuerpo = grupo.group(1), grupo.group(2)
        claves = re.findall(r'\{\s*key:\s*"([a-zA-Z0-9_]+)"', cuerpo)
        for k, n in collections.Counter(claves).items():
            if n > 1:
                culpables.append(f"{nombre} → {k} ×{n}")
    assert not culpables, "Entradas repetidas en la barra:\n  " + "\n  ".join(culpables)


#: Atajos DELIBERADOS: la misma pantalla llegada desde dos tabs, porque se usa
#: desde los dos lados. Con motivo escrito, como toda excepción de este repo.
#:
#: ⚠️ Y con una consecuencia que hay que saber: `Admin → Tabs & Reports` esconde
#: por CLAVE, así que apagar una de éstas la esconde **en los dos tabs**. Es lo
#: correcto —es la misma pantalla— pero no es obvio.
ATAJOS = {
    "importActuals": "subir actuales: se llega desde Escenarios y desde Admin",
    "control": "«¿dónde cayó la plata?»: se llega desde Planning y desde Admin",
}


def test_una_entrada_no_vive_en_DOS_grupos_salvo_los_atajos():
    """La misma pantalla en dos tabs es la otra forma del duplicado: se apaga en
    uno y sigue apareciendo en el otro. Los atajos deliberados van en `ATAJOS`
    CON su motivo — una excepción sin motivo es indistinguible de un olvido."""
    import collections
    import re

    texto = NAV.read_text(encoding="utf-8")
    donde = collections.defaultdict(set)
    for grupo in re.finditer(r'key: "(\w+)",\n    items: \[(.*?)\n    \],', texto, re.S):
        for k in re.findall(r'\{\s*key:\s*"([a-zA-Z0-9_]+)"', grupo.group(2)):
            donde[k].add(grupo.group(1))
    repetidas = {k: sorted(v) for k, v in donde.items()
                 if len(v) > 1 and k not in ATAJOS}
    assert not repetidas, (
        "Entradas en más de un tab sin motivo escrito. Agregalas a ATAJOS con "
        f"el suyo: {repetidas}")
