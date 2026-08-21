# -*- coding: utf-8 -*-
"""Que la instalación no pierda estructura — owner, 2026-08-20.

*«Necesito que fortalezcas esta app para que no pierda estructura.»*

Lo que se vigila acá no es que el inventario esté bien hoy: es que **no se pueda
quedar corto mañana**. Una semilla nueva que nadie agregue al inventario no
falla — simplemente deja de mirarse, y su ausencia se lee como cero. Por eso la
prueba central no cuenta: es una REGLA sobre los archivos del repo.
"""
import inspect
import json
import pathlib

from app import estructura
from app.estructura import GRUPO, INVENTARIO, PROPIEDAD

APP = pathlib.Path(estructura.__file__).resolve().parent
SEMILLAS = APP / "seed_data"


# ── La regla: ninguna semilla queda fuera ────────────────────────────────────

def test_ningun_seed_queda_FUERA_del_inventario():
    """⚠️ Esto es lo que hace que el chequeo siga sirviendo dentro de un año.

    Si alguien agrega `app/seed_nuevo.py` y no lo pone en el inventario, el
    chequeo va a seguir diciendo «estructura completa» sin haber mirado lo que
    ese seed llena. La prueba pasa de contador a regla: **el archivo nuevo
    obliga a la entrada nueva**.
    """
    en_disco = {p.stem for p in APP.glob("seed_*.py")}
    en_disco.discard("seed_data")          # es el paquete de archivos, no un seed
    cubiertos = {d.modulo for d in INVENTARIO}
    huerfanos = sorted(en_disco - cubiertos)
    assert not huerfanos, (
        f"estos seeds llenan tablas que el chequeo no mira: {huerfanos}. "
        f"Agregalos a app/estructura.py")


def test_el_inventario_no_apunta_a_seeds_que_ya_no_existen():
    """Al revés también: una entrada que apunta al vacío da falsa tranquilidad."""
    en_disco = {p.stem for p in APP.glob("seed_*.py")}
    fantasmas = sorted({d.modulo for d in INVENTARIO} - en_disco)
    assert not fantasmas, f"el inventario nombra seeds inexistentes: {fantasmas}"


# ── Ni un número escrito a mano ──────────────────────────────────────────────

def test_lo_esperado_SE_DERIVA_de_la_misma_fuente_que_lee_el_seed():
    """⚠️ Un número tecleado sería mentira en la primera semilla que alguien
    agregue, y este proyecto ya pagó dos veces por una lista escrita a mano.

    Se comprueba recontando la fuente por afuera: si `esperado()` devolviera una
    constante, este recuento y aquel se separarían apenas cambie el archivo.
    """
    por_clave = {d.clave: d for d in INVENTARIO}
    crudo = json.loads((SEMILLAS / "mapping_pl.json").read_text(encoding="utf-8"))
    assert por_clave["account_mapping"].esperado() == len(crudo["account_mapping"])
    assert por_clave["report_line_config"].esperado() == len(crudo["report_line_config"])

    stats = json.loads((SEMILLAS / "stats_catalog.json").read_text(encoding="utf-8"))
    assert por_clave["stat_accounts"].esperado() == len(stats["cuentas"])


def test_todas_las_fuentes_SE_PUEDEN_LEER():
    """Una fuente ilegible deja esa pieza en «no se puede verificar» para
    siempre, y nadie se entera: el renglón sigue apareciendo en amarillo."""
    rotas = []
    for d in INVENTARIO:
        try:
            n = d.esperado()
        except Exception as e:                                  # pragma: no cover
            rotas.append(f"{d.clave}: {e}")
            continue
        assert isinstance(n, int) and n >= 0, d.clave
    assert not rotas, rotas


def test_lo_del_GRUPO_espera_algo_de_verdad():
    """Si una pieza del grupo esperara cero, su control no podría fallar nunca
    — que es la definición de un control decorativo."""
    vacias = [d.clave for d in INVENTARIO
              if d.familia == GRUPO and d.esperado() == 0]
    assert not vacias, f"esperan cero y por lo tanto no controlan nada: {vacias}"


# ── Las dos familias ─────────────────────────────────────────────────────────

def test_hay_las_DOS_familias_y_no_significan_lo_mismo():
    familias = {d.familia for d in INVENTARIO}
    assert familias == {GRUPO, PROPIEDAD}


def test_lo_de_la_propiedad_sale_de_SU_carpeta():
    """⚠️ Es lo que impide que Amarena herede los datos de Corcovado. Cada
    pieza de la familia PROPIEDAD tiene que leer `seed_data/<HOTEL_ID>/`."""
    for d in INVENTARIO:
        if d.familia != PROPIEDAD:
            continue
        assert "<HOTEL_ID>" in d.fuente or "HOTEL_ID" in d.fuente, (
            f"{d.clave} es de la propiedad pero su fuente no depende del hotel: "
            f"{d.fuente}")


def test_una_propiedad_SIN_carpeta_no_hereda_nada():
    """Un hotel que todavía no tiene semillas propias tiene que dar CERO, no
    los números de Corcovado."""
    fuente = inspect.getsource(estructura)
    assert "if not ruta.exists():" in fuente
    assert "return 0" in fuente


# ── Cómo lo reporta el chequeo ───────────────────────────────────────────────

def test_el_chequeo_mide_INCOMPLETA_no_solo_vacia():
    """⚠️ El agujero que esto cierra: `account_mapping` con tres filas de 1.099
    pasaba el control anterior, y esas 1.096 cuentas que faltan no fallan —
    caen en ninguna línea del P&L."""
    from app.api import chequeo_api

    fuente = inspect.getsource(chequeo_api.chequeo)
    assert "hay < esperado" in fuente, "no compara contra lo esperado"
    assert "INVENTARIO" in fuente


def test_el_chequeo_tiene_TRES_estados():
    """«No se pudo mirar» no es «está bien». Este proyecto ya contó catorce
    presupuestos como cuadrados sin haber comparado nada."""
    from app.api import chequeo_api

    fuente = inspect.getsource(chequeo_api.chequeo)
    assert "sin_verificar" in fuente
    assert "estructura_sin_verificar" in fuente
    # Y no se pueda verificar NO cae en la rama OK.
    assert 'elif sin_verificar:' in fuente


def test_una_propiedad_SIN_semillas_NO_sale_en_verde():
    """⚠️ Lo encontró el ensayo del clon, no las pruebas.

    Corriendo el chequeo declarándome Amarena contra una base sin sus datos, el
    renglón contestó **«las 5 piezas propias de esta propiedad están
    cargadas»** — con cero filas. La razón: una propiedad sin carpeta de
    semillas espera CERO, así que `hay < esperado` no se cumplía nunca. Un
    control que sólo puede dar verde no es un control.

    Para la familia PROPIEDAD la pregunta no es «llegó a lo esperado» sino
    «hay ALGO»: cero es justamente la lista de lo que esa propiedad debe.
    """
    from app.api import chequeo_api

    fuente = inspect.getsource(chequeo_api.chequeo)
    assert "elif d.familia == PROPIEDAD and not hay:" in fuente, (
        "cero en una pieza de la propiedad se estaría contando como completa")


def test_lo_de_la_propiedad_NUNCA_sale_en_rojo():
    """En una propiedad recién abierta falta a propósito. Pintarlo de rojo el
    día uno enseñaría a ignorar el rojo — y el rojo hace falta para lo otro."""
    from app.api import chequeo_api

    fuente = inspect.getsource(chequeo_api.chequeo)
    i = fuente.find("estructura_propiedad")
    assert i > 0
    tramo = fuente[i:]
    assert '"error"' not in tramo.split("# ──")[0]


def test_no_se_pudo_mirar_NO_se_cuenta_como_completo():
    """`None` y `0` son cosas distintas y no pueden compartir rama."""
    from app.api import chequeo_api

    fuente = inspect.getsource(chequeo_api.chequeo)
    assert "if hay is None:" in fuente


def test_los_textos_nuevos_estan_en_LOS_DOS_idiomas():
    from app.textos import TEXTOS

    for clave in ("chequeo.estructura_titulo", "chequeo.estructura_ok",
                  "chequeo.estructura_incompleta", "chequeo.estructura_sin_verificar",
                  "chequeo.propiedad_titulo", "chequeo.propiedad_falta"):
        assert clave in TEXTOS, clave
        assert set(TEXTOS[clave]) >= {"es", "en"}, clave


# ── El Break-Even, que se cargaba a mano ─────────────────────────────────────

def test_el_break_even_ENTRA_POR_EL_ARRANQUE():
    """⚠️ Medido el 2026-08-20: estas dos tablas se cargaban con un script que
    **nadie llamaba**. Un clon levantaba con las dos vacías, y eso no da error:
    Costos de Grupos pierde el `be_section` con que separa PAYROLL de COST OF
    SALES, y Break-Even muestra ceros.

    Estructura que sólo existe si alguien se acuerda de correr un script es
    estructura que se va a perder.
    """
    from app import seed

    fuente = inspect.getsource(seed)
    assert "from app.seed_break_even import seed_break_even" in fuente
    assert "await seed_break_even(db)" in fuente


def test_la_semilla_del_break_even_es_DE_LA_PROPIEDAD():
    """Los porcentajes fijo/variable son de Corcovado, medidos contra su P&L.
    Sembrárselos a otra propiedad sería el mismo error del paquete y las
    experiencias, que ya se corrigió una vez."""
    from app import seed_break_even

    assert (SEMILLAS / "CWL" / "break_even" / "be_classification_seed.csv").exists()
    assert not (SEMILLAS / "break_even").exists(), (
        "quedó la carpeta vieja, común a todas las propiedades")
    assert "HOTEL_ID" in inspect.getsource(seed_break_even.carpeta)


def test_el_break_even_se_puede_sembrar_DOS_VECES():
    """Corre en cada despliegue: si no fuera idempotente, cada deploy duplicaría
    las 612 reglas. Y la llave lleva `pl_line` porque las filas `LINEA`
    colisionan todas en (property, '', '')."""
    from app import seed_break_even

    fuente = inspect.getsource(seed_break_even.seed_break_even)
    assert 'llave in ya' in fuente
    assert 'c["pl_line"]' in fuente
    # String vacío, jamás None: en Postgres NULL != NULL y la llave no aparearía.
    assert 'c["dept_code"] or ""' in fuente


# ── El mapeo: la siembra que se caia en silencio ─────────────────────────────

def test_la_clave_del_seed_ES_la_restriccion_de_la_tabla():
    """⚠️ El bug de 2026-08-20, en una línea.

    La clave del seed estaba escrita a mano y decía ser «la misma de las
    restricciones» sin serlo: a `uq_account_mapping` se le había agregado
    `vigente_desde` y la clave se quedó con cuatro columnas. Las dos reglas de
    la 7120 —hasta jun-2026 en A&G, desde jul-2026 en Credit Card Commissions—
    se veían como UNA, el seed intentaba insertar la segunda y **la siembra
    entera se caía en cada despliegue** con un `IntegrityError` que el
    `try/except` dejaba en una línea de log.

    Derivarla es lo que impide que vuelvan a separarse.
    """
    from sqlalchemy import UniqueConstraint

    from app.models.mapping import AccountMapping, ReportLineConfig
    from app.seed_mapping import _columnas_unicas

    for modelo in (AccountMapping, ReportLineConfig):
        dela_tabla = next(tuple(c.name for c in r.columns)
                          for r in modelo.__table__.constraints
                          if isinstance(r, UniqueConstraint))
        assert _columnas_unicas(modelo) == dela_tabla, modelo.__name__


def test_las_dos_reglas_de_la_7120_NO_son_la_misma():
    """La vigencia existe porque el mapeo cambia y los reportes ya enviados no
    pueden cambiar con él. Si la clave las confunde, una pisa a la otra."""
    import json

    from app.seed_mapping import ARCHIVO, _clave_mapeo

    datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    reglas = [r for r in datos["account_mapping"]
              if r["account_code"] == "7120"
              and r["source_department"] == "Departamento de Administración"
              and r["report_id"] == "P&L_DETAIL_OWNERS"]
    assert len(reglas) == 2, "el archivo dejó de traer las dos vigencias"
    assert _clave_mapeo(reglas[0]) != _clave_mapeo(reglas[1])


def test_NINGUNA_llave_del_archivo_se_repite():
    """Dos filas con la misma llave hacen que el seed intente insertar la
    segunda y se caiga el lote completo — que es exactamente lo que pasaba."""
    import collections
    import json

    from app.seed_mapping import ARCHIVO, _clave_linea, _clave_mapeo

    datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    for bloque, clave in (("report_line_config", _clave_linea),
                          ("account_mapping", _clave_mapeo)):
        repetidas = [k for k, n in collections.Counter(
            clave(r) for r in datos[bloque]).items() if n > 1]
        assert not repetidas, f"{bloque}: llaves repetidas {repetidas[:3]}"


def test_el_chequeo_compara_CONTENIDO_no_cantidad():
    """⚠️ El conteo cuadraba (1.099 = 1.099) mientras la siembra se caía. Contar
    no habría notado nada nunca."""
    from app.api import chequeo_api

    fuente = inspect.getsource(chequeo_api.chequeo)
    assert "chequeo.mapeo_desviado" in fuente
    assert "getattr(o, k, None) or None" in fuente, "no compara campo por campo"


def test_el_rojo_del_mapeo_se_reserva_para_lo_que_MUEVE_PLATA():
    """Las 29 diferencias que aparecieron eran todas `notes`. Pintarlas de rojo
    junto a un cambio de línea del P&L enseñaría a ignorar el rojo — y el rojo
    hace falta para lo otro: mover UNA cuenta re-expresó 102 líneas."""
    from app.api.chequeo_api import SOLO_DOCUMENTAN

    assert "notes" in SOLO_DOCUMENTAN
    # Y nada que rutee puede estar acá dentro.
    for campo in ("report_line_code", "report_section", "dept_code",
                  "source_department", "financial_nature", "rollup_operator"):
        assert campo not in SOLO_DOCUMENTAN, campo


def test_lo_que_esta_de_MAS_tampoco_es_neutro():
    """⚠️ Corcovado tiene 39 departamentos y el repo trae 37: 0115 Villas y
    0116 Residencias se agregaron a mano en la app.

    De más no es un error —la app deja agregarlos a propósito— pero **el seed no
    puede reproducirlos**: si esa base se reconstruye, se pierden y nadie lo
    diría. Un chequeo que solo mira lo que falta deja ese agujero abierto.
    """
    from app.api import chequeo_api

    fuente = inspect.getsource(chequeo_api.chequeo)
    assert "hay > esperado" in fuente
    assert "estructura_de_mas" in fuente


def test_los_ARCHIVOS_de_arranque_tambien_se_preguntan():
    """No llenan tablas —son las sugerencias que ofrece la pantalla— pero son
    estructura igual: sin ellos la propiedad abre en blanco, y **en blanco no
    explica por qué**. Faltaban en la lista de «lo que esta propiedad debe»."""
    from app.estructura import semillas_de_la_propiedad

    tiene, faltan = semillas_de_la_propiedad("CWL")
    assert "paquete.json" in tiene and not faltan
    # Una propiedad que todavía no existe debe TODO, y con nombre.
    tiene2, faltan2 = semillas_de_la_propiedad("NO_EXISTE")
    assert not tiene2 and "paquete.json" in faltan2


def test_el_catalogo_de_archivos_SE_DERIVA_de_las_carpetas():
    """⚠️ Escrito a mano, un archivo nuevo en Corcovado nunca se le pediría a
    las demás propiedades — y nadie se enteraría."""
    from app import estructura

    fuente = inspect.getsource(estructura.semillas_de_la_propiedad)
    assert "SEMILLAS.iterdir()" in fuente
    assert "glob(\"*.json\")" in fuente
