# -*- coding: utf-8 -*-
"""
UN HOTEL = UNA INSTALACIÓN. NADA DICE «CWL» A MANO.

**Modelo de despliegue (owner, 2026-08-12):** los cuatro hoteles son cuatro
proyectos independientes — base propia, app propia. No es multi-tenant en una
sola base. Por eso la identidad sale del ENTORNO (`HOTEL_ID`) y no de un
selector ni de una tabla de hoteles.

Había 20 literales `"CWL"` repartidos por la API, los importadores y los
defaults de columna. En Corcovado son inofensivos porque aciertan por
casualidad. En un despliegue de Amarena cada uno es:

* una fila estampada con el hotel equivocado (los `default="CWL"` de columna), o
* un `db.get(Hotel, "CWL")` que devuelve `None` y revienta sin explicar por qué.

Ninguna de las dos cosas da error en Corcovado, así que no se descubrirían hasta
tener el segundo hotel andando — que es el peor momento.
"""
import ast
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1] / "app"

# El seed declara la identidad (lee el entorno y crea la fila del hotel) y
# hotel_actual es la fuente. Los dos tienen que poder nombrar el default.
#
# Los otros dos son DATOS SEMILLA de Corcovado, no identidad filtrada: los seis
# tipos de habitación (`CWL_ROOM_TYPES`) y los componentes del paquete con la
# ruta Sierpe/Drake. Están gateados por hotel —`seed.py` no los siembra a un
# clon— y llevan «CWL» en el nombre de la constante justamente para que se vea
# de quién son. Una propiedad nueva carga los suyos.
PERMITIDOS = {"seed.py", "hotel_actual.py",
              "room_type_config.py", "package_menu.py"}


def test_no_quedan_literales_cwl_en_el_backend():
    """Se mira el AST, no el texto: un comentario que EXPLICA 'CWL' está bien.

    Lo que no puede haber es «CWL» ni «Corcovado» DENTRO de una cadena que el
    código usa como valor — un default de columna, un `db.get(Hotel, "CWL")`,
    o el encabezado de un Excel.

    ⚠️ **Esta prueba tenía un punto ciego y dejó pasar seis archivos.** Antes
    comparaba `nodo.value == "CWL"`, o sea la cadena EXACTA. En un f-string como
    `f"FinPlan CWL — OPEX {year}"` el trozo constante es `"FinPlan CWL — OPEX "`,
    que no es igual a `"CWL"` — así que la prueba pasaba en verde mientras cinco
    exportadores le mandaban el nombre de Corcovado al Excel del dueño de otro
    hotel. Ahora busca por CONTENIDO, no por igualdad.
    """
    culpables = []
    for p in sorted(RAIZ.rglob("*.py")):
        if p.name in PERMITIDOS:
            continue
        arbol = ast.parse(p.read_text(encoding="utf-8"))
        # Las docstrings son documentación, no valores: explicar que la 4500 la
        # comparte el Club de CWL es exactamente lo que un comentario debe hacer.
        docs = set()
        for n in ast.walk(arbol):
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                cuerpo = getattr(n, "body", None)
                if (cuerpo and isinstance(cuerpo[0], ast.Expr)
                        and isinstance(cuerpo[0].value, ast.Constant)
                        and isinstance(cuerpo[0].value.value, str)):
                    docs.add(id(cuerpo[0].value))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Constant) or not isinstance(nodo.value, str):
                continue
            if id(nodo) in docs:
                continue
            # Rutas de archivo del equipo de desarrollo. Son el default de una
            # variable de entorno (`DATA_DIR`) y viven en el disco de quien
            # programa, no en la identidad de ninguna propiedad.
            if nodo.value.startswith("C:/FinPlan_CWL"):  # ruta-a-proposito: es el patron que se BUSCA
                continue
            # `CWL_ROOM_TYPES` en un `__all__`: es el NOMBRE de un símbolo, no
            # un dato. Renombrarlo no haría nada por otra propiedad.
            if nodo.value.isidentifier():
                continue
            # Los diccionarios de respaldo de nombres de departamento traen
            # «Corcovado Bosque», que es un DEPARTAMENTO y no el hotel. Están
            # marcados en su propio archivo como respaldo muerto: los llamadores
            # pasan el catálogo de la base. Ver los comentarios de `*_excel.py`.
            if nodo.value in ("Corcovado Bosque",):
                continue
            if "CWL" in nodo.value or "Corcovado" in nodo.value:
                culpables.append(
                    f"{p.relative_to(RAIZ)}:{nodo.lineno}  {nodo.value[:48]!r}")
    assert not culpables, (
        "el nombre de Corcovado usado como VALOR — en un despliegue de otro "
        "hotel estampa el hotel equivocado:\n  " + "\n  ".join(culpables))


# Quién puede nombrarlas: el paquete `models/`, que es donde se DECLARAN (y su
# `__init__` que las reexporta), y el seed, que las siembra gateado por hotel.
# Declarar un dato semilla de Corcovado no le hace nada a nadie; servirlo desde
# un endpoint sí.
PUEDEN_USAR_SEMILLA = {"seed.py"}
PAQUETE_DE_MODELOS = "models"

# LÍNEA BASE — lo que ya estaba cuando se escribió esta regla (2026-08-13).
#
# No es una lista de perdonados: es el inventario de lo que falta mover a
# `seed_data/<HOTEL_ID>/`. Esta prueba impide que CREZCA. Cada vez que uno se
# arregla, se saca de acá y no puede volver.
#
# Lo que queda son DEFAULTS que solo disparan con la tabla vacía: molestos —hay
# que borrarle a mano a Amarena los tours de Drake— pero no corrompen dato ya
# cargado. Los dos que sí lo corrompían (`_canonical_room_types` y
# `_OTB_UNITS`) ya leen de `room_type_configs`.
SEMILLA_PENDIENTE = {
    # CWL_ROOM_TYPES salió de acá el 2026-08-13: los tipos de habitación y el
    # inventario del On The Books ahora se leen de `room_type_configs`. Era el
    # más caro de la lista — Amarena habría guardado sus noches reales bajo
    # «Sirena Suites», un tipo que ese hotel no tiene.
    # 2026-08-14: el paquete, las experiencias y los canales de venta salieron de
    # aca. Ya no se leen de constantes: viven en `app/seed_data/<HOTEL_ID>/` y una
    # propiedad sin carpeta abre la pantalla en blanco, que es la verdad.
    # 2026-08-16: salieron las dos ultimas de la API. `CWL_OPEX_ACCOUNTS` es
    # `seed_data/<HOTEL_ID>/opex_accounts.json` y `CWL_CHANNELS` —la lista de
    # canales del reporte de mix— es `canales_mix.json`. La constante
    # `CWL_CHANNELS` ya no existe: la borramos en vez de dejarla en el modelo,
    # para que no queden dos listas que puedan decir cosas distintas.
    # 2026-08-17: salio la ultima. `revenue_importer.py` leia
    # `CWL_DEFAULT_CHANNELS` y `CWL_DEFAULT_PACKAGE` como fallback cuando una
    # celda del Key Indicators viene vacia. Ahora lee `semilla("canales", hotel_id)`
    # y `semilla("paquete", hotel_id)` — los archivos de CWL ya existian con los
    # mismos valores, asi que esto no movio un numero. Las dos constantes siguen
    # vivas en `sales_channel_config.py`/`package_config.py` porque
    # `test_revenue.py` las usa como fixture de matematica conocida, fuera de
    # `app/` y por lo tanto fuera del alcance de este escaneo.
}

# Migraciones que ya corrieron con `server_default="CWL"`. No se pueden cambiar
# —ya están aplicadas—, así que quedan anotadas y la regla vigila que no aparezca
# una nueva. Limpiarlas es una migración propia que quite el default.
MIGRACIONES_CON_DEFAULT_CWL = {"054", "060", "062", "084", "088"}


def test_ningun_endpoint_sirve_los_datos_semilla_de_corcovado():
    """El punto ciego que la prueba de arriba no ve.

    Esa mira CADENAS. Pero lo que se cuela no es una cadena: es **importar un
    símbolo `CWL_*`** desde un endpoint. El nombre de la constante no aparece
    nunca como texto, así que pasa en verde.

    La auditoría previa al clonado (2026-08-13) encontró el patrón vivo en
    `revenue_api`: `_canonical_room_types()` armaba la grilla desde
    `CWL_ROOM_TYPES` en vez de leer `room_type_configs`, y varios endpoints
    devolvían los canales, las experiencias y el paquete de Corcovado —
    marcados `"seeded": true`— a cualquier hotel con la tabla vacía.

    En Corcovado acierta por casualidad. En Amarena, la pantalla donde se
    digitan las estadísticas reales guardaría las noches bajo «Sirena Suites»,
    un tipo de habitación que ese hotel no tiene. Sin error y sin aviso.
    """
    culpables = []
    for p in sorted(RAIZ.rglob("*.py")):
        if p.name in PUEDEN_USAR_SEMILLA:
            continue
        ruta = p.relative_to(RAIZ).as_posix()
        if ruta.split("/")[0] == PAQUETE_DE_MODELOS:
            continue
        arbol = ast.parse(p.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            nombres = []
            if isinstance(nodo, ast.ImportFrom):
                nombres = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.Name):
                nombres = [nodo.id]
            for n in nombres:
                if n.startswith("CWL_") and n not in SEMILLA_PENDIENTE.get(ruta, ()):
                    culpables.append(f"{ruta}:{nodo.lineno}  {n}")
    assert not culpables, (
        "estos usan datos semilla de Corcovado fuera del seed. Un clon los "
        "recibe como si fueran suyos:\n  " + "\n  ".join(sorted(set(culpables))))


def test_la_linea_base_de_semilla_no_esconde_lo_que_ya_se_arreglo():
    """Una entrada que ya no corresponde deja el hueco abierto para la próxima.

    Es el mismo cuidado que la lista de pantallas exentas del Excel: si nadie
    saca lo que se arregló, la lista deja de ser un inventario de deuda y pasa a
    ser un lugar donde esconder trabajo.
    """
    vivos: dict[str, set[str]] = {}
    for p in sorted(RAIZ.rglob("*.py")):
        arbol = ast.parse(p.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            nombres = ([a.name for a in nodo.names] if isinstance(nodo, ast.ImportFrom)
                       else [nodo.id] if isinstance(nodo, ast.Name) else [])
            for n in nombres:
                if n.startswith("CWL_"):
                    vivos.setdefault(p.relative_to(RAIZ).as_posix(), set()).add(n)
    sobran = {ruta: sorted(nn - vivos.get(ruta, set()))
              for ruta, nn in SEMILLA_PENDIENTE.items()
              if nn - vivos.get(ruta, set())}
    assert not sobran, f"ya no se usan; sacalos de SEMILLA_PENDIENTE: {sobran}"


def test_ninguna_migracion_estampa_cwl_en_el_esquema():
    """`server_default="CWL"` queda escrito en el ESQUEMA del clon.

    Hoy el ORM lo tapa (`default=HOTEL_ID` en los modelos), así que no se nota.
    Pero el default vive en la tabla de Amarena: cualquier INSERT que no pase
    por el ORM —una carga a mano, un script, una migración futura— estampa CWL
    en la base equivocada.
    """
    versiones = RAIZ.parents[0] / "alembic" / "versions"
    culpables = []
    for p in sorted(versiones.glob("*.py")):
        if p.name.split("_")[0] in MIGRACIONES_CON_DEFAULT_CWL:
            continue          # ya corrieron; se limpian con una migración propia
        for i, linea in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
            if "server_default" in linea and "CWL" in linea:
                culpables.append(f"{p.name}:{i}")
    assert not culpables, (
        "esta migración deja «CWL» de default en el esquema de las cuatro "
        "propiedades. Usá `default=HOTEL_ID` en el modelo, no un default de "
        "columna:\n  " + "\n  ".join(culpables))


def test_el_env_de_produccion_no_trae_la_url_de_nadie():
    """Un archivo commiteado con la URL de una propiedad es dato cruzado.

    `frontend/.env.production` viaja a los cuatro hoteles. Tenía la URL del
    backend de Corcovado: un despliegue de Amarena que no pisara la variable en
    Vercel habría escrito EN LA BASE DE CORCOVADO, sin dar error.
    """
    env = RAIZ.parents[1] / "frontend" / ".env.production"
    if not env.exists():
        return
    for linea in env.read_text(encoding="utf-8").split("\n"):
        limpia = linea.strip()
        if not limpia or limpia.startswith("#"):
            continue
        clave, _, valor = limpia.partition("=")
        assert not valor.strip(), (
            f"{env.name} define {clave.strip()} con un valor. Ese archivo está "
            "commiteado y viaja a las cuatro propiedades: cada una define lo "
            "suyo en el entorno de su proyecto de Vercel.")


def test_el_hotel_sale_del_entorno():
    from app.hotel_actual import HOTEL_ID, hotel_id
    assert HOTEL_ID  # nunca vacío
    assert hotel_id() == HOTEL_ID


def test_el_seed_y_el_helper_usan_la_misma_variable():
    """Si se separan, el seed crea un hotel y la API busca otro."""
    seed = (RAIZ / "seed.py").read_text(encoding="utf-8")
    helper = (RAIZ / "hotel_actual.py").read_text(encoding="utf-8")
    assert 'os.getenv("HOTEL_ID"' in seed
    assert 'os.getenv("HOTEL_ID"' in helper


# ─────────────────────────────────────────────────────────────────────────────
# Y lo mismo vale para las PRUEBAS (2026-08-14, al encender el CI).
#
# Once archivos tenían `C:\FinPlan_CWL` escrito a mano. En esta máquina andan; en
# el CI la ruta no resuelve, el archivo sale vacío y —como esas pruebas empiezan
# con «si no hay fuente, return»— **pasaban en verde sin haber mirado nada**.
# Sesenta pruebas que no protegían nada fuera de una computadora.
# ─────────────────────────────────────────────────────────────────────────────

def test_ninguna_prueba_tiene_una_ruta_absoluta():
    """Las rutas se calculan desde `__file__`, en `tests/_rutas.py`."""
    import re
    pruebas = pathlib.Path(__file__).resolve().parent
    patron = re.compile(r'["\'][A-Za-z]:[\/]|["\']/home/|["\']/Users/')
    culpables = []
    for p in sorted(pruebas.glob("*.py")):
        for n, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            if linea.lstrip().startswith("#"):
                continue          # un comentario que EXPLICA la ruta está bien
            if "ruta-a-proposito" in linea:
                continue          # la ruta es el patrón que se busca, no una que se usa
            if patron.search(linea):
                culpables.append(f"{p.name}:{n}: {linea.strip()[:90]}")
    assert not culpables, (
        "Ruta absoluta en una prueba. Fuera de esa máquina el archivo sale vacío "
        "y la prueba pasa sin mirar nada:\n  " + "\n  ".join(culpables)
        + "\nUsá `from tests._rutas import RAIZ, FRONT, DATOS`."
    )
