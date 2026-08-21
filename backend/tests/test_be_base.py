# -*- coding: utf-8 -*-
"""LA BASE DEL BREAK-EVEN — la capa que mapea el GL a REV / COST / OPEX.

Pedido del owner (2026-08-17): *«creá una tabla intermedia donde se mapee el GL
en REV, COST, OPEX y todo lo demás… que pase por el filtro y de ahí se jale para
el tab. Y que se valide que todos los datos peguen con el P&L.»*

El cuadre contra producción vive en `scripts/cuadre_base_break_even` (los cinco
escenarios, al centavo). Acá quedan fijados los **criterios**, que son lo que se
puede romper sin que ningún total avise.
"""
from decimal import Decimal

from app.api import _be_base as bb

D = Decimal


def fila(dept="0110", cuenta="6000", linea="OPEX_ROOMS",
         seccion="OPERATING EXPENSES", monto="100", slug="rooms", reparte=False):
    return bb.FilaBase(dept, cuenta, linea, seccion, D(monto), slug, reparte)


# ─── Lo que entra a la base de costo, y lo que no ────────────────────────────

def test_la_seccion_de_ingreso_no_entra_al_costo():
    """El defecto que el owner vio primero: `$4.667.098 de ingreso` dentro del
    costo fijo y el equilibrio en $12,4 M. Las 612 reglas son todas de costo, así
    que una cuenta `4xxx` no encuentra regla y cae al default 100% fijo."""
    f = fila(cuenta="4000", linea="REV_ROOMS", seccion="REVENUES")
    assert f.es_ingreso and not f.es_costo


def test_una_fila_sin_linea_entra_al_costo_para_que_se_VEA():
    """Sin línea no se puede saber si es costo. Se deja pasar a propósito: cae
    en «Por defecto: 100% fijo», que es una pantalla. Descartarla sería la única
    opción que no aparece en ningún lado."""
    assert fila(linea="", seccion="").es_costo


def test_las_secciones_de_costo_son_lista_BLANCA():
    """Con lista negra, una sección nueva entraría al costo en silencio — y eso
    **baja** el equilibrio, o sea que el error se ve como buena noticia."""
    assert "KPIs" not in bb.SECCIONES_DE_COSTO
    assert "GOP" not in bb.SECCIONES_DE_COSTO
    assert "EBITDA" not in bb.SECCIONES_DE_COSTO
    # Y el impuesto SÍ entra: su regla lo marca `excluded_from_be`, el motor lo
    # saca del costo fijo pero lo resta al neto. Sin él el neto no cierra.
    assert "TAX / NET PROFIT" in bb.SECCIONES_DE_COSTO


def test_los_que_reparten_quedan_fuera_del_costo():
    """Cafetería y Lavandería reparten todo y netean 0,00. No se contaban dos
    veces, pero ensuciaban «Por defecto: 100% fijo» con filas de un centavo, y
    eso hace parecer que falta clasificar plata donde no falta."""
    base = bb.BaseBE(filas=[fila(monto="100"),
                            fila(dept="0220", slug="cafeteria", reparte=True)])
    assert len(base.costos()) == 1


# ─── El ingreso: de dónde sale, y por qué NO del GL ──────────────────────────

def test_el_ingreso_sale_del_PL_y_no_del_GL():
    """⚠️ Medido: en el `BUDGET Working 2027` la primera versión daba $0 contra
    $6.374.026 del P&L. Por dos motivos, y ninguno es que falte el dato:
    `_sources` **no devuelve ingreso** en modo `checkbook` (es una fuente de
    costo), y esos escenarios están en `revenue_source = 'drivers'`, donde el
    ingreso lo calcula el motor y `revenue_entries` es un espejo.

    Un cero por «no hay filas» y un cero por «no vendió» se ven idénticos."""
    base = bb.BaseBE(
        filas=[],                                   # el GL, vacío de ingreso
        ingreso_pl={"REV_ROOMS": D("6374026.18")},  # el P&L, que sí lo tiene
        depto_de_linea={"REV_ROOMS": "rooms"},
    )
    assert base.total_ingreso_del_gl() == 0
    assert base.ingreso_por_departamento() == {"rooms": D("6374026.18")}


def test_no_se_suman_los_dos_vocabularios_de_la_misma_linea():
    """⚠️ El motor emite `REV_TRANSPORT` **y** `REV_TRANSPORTATION`, porque
    `canonicalize_pl_lines` es ADITIVO. Sumar «todo lo que empiece con REV_»
    contaba el mismo peso dos veces: en el `ACTUAL 2024` daba $2.120.135 contra
    $2.055.687, y la diferencia eran exactamente los $64.448,17 de
    Transportation.

    Un duplicado que cae justo sobre un departamento entero no se ve como
    duplicado: se ve como un departamento que vendió el doble."""
    assert bb._canonica("REV_TRANSPORT") == "REV_TRANSPORTATION"
    assert bb._canonica("REV_CROWTHER") == "REV_CROWTHER_LAB"
    # Una canónica se queda como está.
    assert bb._canonica("REV_ROOMS") == "REV_ROOMS"


def test_el_ingreso_sin_departamento_se_informa_y_no_se_reparte():
    """Repartirlo se lo daría a todos; sumarlo a uno le daría a ese un margen
    que no es suyo. Hoy son `REV_SUSTAINABILITY` y `REV_MISC_OTHER`."""
    base = bb.BaseBE(
        ingreso_pl={"REV_ROOMS": D("100"), "REV_SUSTAINABILITY": D("30")},
        depto_de_linea={"REV_ROOMS": "rooms"},
    )
    assert base.ingreso_por_departamento() == {"rooms": D("100")}
    assert base.ingreso_sin_departamento() == D("30")
    assert base.total_ingreso() == D("130")


# ─── El cuadre que pidió el owner ────────────────────────────────────────────

def test_el_cuadre_caza_una_linea_que_se_pierde_en_el_reparto():
    """Un ingreso mal atribuido **no se ve**: el total del hotel queda igual y
    solo se mueve el margen de un departamento contra otro."""
    base = bb.BaseBE(
        ingreso_pl={"REV_ROOMS": D("100"), "REV_SPA": D("30")},
        depto_de_linea={"REV_ROOMS": "rooms", "REV_SPA": "spa"},
    )
    assert all(c.cuadra for c in bb.validar_contra_pl(base, D("130")))
    # Y si el P&L dice otra cosa, lo dice.
    malos = [c for c in bb.validar_contra_pl(base, D("200")) if not c.cuadra]
    assert len(malos) == 1 and malos[0].diferencia == D("-70")


def test_los_totales_del_reporte_nunca_entran():
    """`TOTAL_REVENUES` es la suma de las otras líneas. Si entrara, cada peso se
    contaría dos veces **y los totales seguirían cuadrando entre sí**, al doble:
    el error más difícil de ver de todos."""
    assert "TOTAL_REVENUES" in bb.LINEAS_QUE_SON_TOTALES
    assert "SEC_REVENUES" in bb.LINEAS_QUE_SON_TOTALES
    assert "TOTAL_OPERATING_EXPENSES" in bb.LINEAS_QUE_SON_TOTALES


# ─── El departamento del ingreso sale del MAPEO DE CUENTAS ───────────────────

def test_el_depto_del_ingreso_sale_del_account_mapping():
    """Owner: *«los canales entran al principio y los resultados que van al GL
    son el final del proceso»* · *«debe tomar todas las cuentas»*.

    Y las cuentas **ya estaban**: `account_mapping` trae las 19 lineas de
    ingreso con su departamento (`REV_ROOMS` -> `0110/4000`,
    `REV_SUSTAINABILITY` -> `280/4880`). No habia que inventar nada; habia que
    mirar la tabla correcta — la MISMA que resuelve el costo.
    """
    mappings = [
        {"report_line_code": "REV_ROOMS", "dept_code": "0110", "account_code": "4000"},
        {"report_line_code": "REV_SUSTAINABILITY", "dept_code": "280", "account_code": "4880"},
        # El vocabulario viejo tambien tiene que aterrizar en la canonica.
        {"report_line_code": "REV_TRANSPORT", "dept_code": "0152", "account_code": "4400"},
    ]
    slug_de_dept = {"0110": "rooms", "280": "miscelaneos", "0152": "transportation"}
    m = bb._lineas_de_ingreso_por_departamento(mappings, slug_de_dept)
    assert m["REV_ROOMS"] == "rooms"
    assert m["REV_SUSTAINABILITY"] == "miscelaneos"
    assert m["REV_TRANSPORTATION"] == "transportation"


def test_derivarlo_de_los_grupos_perdia_departamentos():
    """⚠️ La version anterior lo sacaba de los grupos de `pl_engine`
    (`dept -> grupo -> atributo -> REV_*`) y **perdia plata en silencio**: los
    departamentos `280` (Miscelaneos) y `0205` (Claro Huerta) caen en
    `OTHER_OVERHEAD` en esa cadena, asi que `REV_MISC_OTHER` y
    `REV_SUSTAINABILITY` salian SIN departamento — $308.405 en el
    `BUDGET Final 2026`.

    El P&L seguia cuadrando: el total del hotel no se movia, solo faltaba
    margen en departamentos que nadie estaba mirando. Esta prueba fija que la
    cadena vieja NO alcanza, para que no se vuelva a elegir por comodidad.
    """
    from app.engine import pl_engine
    for dept in ("280", "0205"):
        grupo = pl_engine.group_for_dept(dept)
        assert pl_engine.GROUP_TO_REVENUE_LINE.get(grupo) is None, (
            f"{dept} ahora si tiene linea de ingreso por grupo: revisar si la "
            f"derivacion por grupos ya seria suficiente")


# ─── El Control toma TODAS las cuentas, tambien las de ingreso ───────────────

def test_el_trazado_incluye_el_ingreso():
    """Owner: *«debe tomar todas las cuentas»*.

    `_sources` era una fuente de COSTO —OPEX, Costos, Planilla, Repartos— y el
    tab de Control lo decia en su propio texto («payroll, OPEX, costs»). Por eso
    mostraba **«MONTO QUE SE PIERDE $0» sin haber mirado un peso de ingreso**:
    no es que no se perdiera nada, es que veia la mitad.

    Solo hace falta en modo `checkbook`; en `imported` el detalle GL ya trae las
    `4xxx` como cualquier otra fila.
    """
    import inspect
    from app.api import audit_api
    fuente = inspect.getsource(audit_api._sources)
    assert "_filas_de_ingreso" in fuente, (
        "el trazado dejo de incluir el ingreso: el Control vuelve a decir "
        "«se pierde $0» sin mirarlo")


def test_el_ingreso_del_trazado_no_inventa_cuentas():
    """El (departamento, cuenta) sale del `account_mapping`, la MISMA autoridad
    que resuelve el costo. Si alguien pone una tabla aparte, se desincroniza el
    dia que se mueva una cuenta de departamento."""
    import inspect
    from app.api import audit_api
    fuente = inspect.getsource(audit_api._filas_de_ingreso)
    assert "load_active_account_mappings" in fuente
    assert "REVENUE_LINE_ACCOUNT" not in fuente, (
        "volvio a usar el mapa escrito a mano, que solo cubre las 3 del Club")


# ─── «Sin movimiento» NO es «muerta» ─────────────────────────────────────────

def test_una_regla_sin_monto_no_es_basura_y_no_se_borra():
    """⚠️ Medido el 2026-08-17, y contradice lo que decia la pantalla.

    De las **271** reglas que no aparecen en NINGUNO de los 20 escenarios, las
    **271** son combinaciones (departamento, cuenta) validas y ruteables en el
    `account_mapping`. **Cero** son basura: son cuentas normales del catalogo
    —`6028 Housing`, `7185 Equipment Rental`, `6002 Day Off`— a las que nadie
    les presupuesto plata todavia.

    No estan muertas: estan **esperando**. Y borrarlas seria el peor arreglo
    posible, porque el dia que alguien presupueste esa cuenta caeria al default
    100% fijo — en silencio, y en la direccion que SUBE el equilibrio sin que
    nadie sepa por que.

    El medidor que lo comprueba: `scripts/que_son_las_reglas_sin_monto`.

    Esta prueba fija el CRITERIO en la pantalla, que es donde se toma la
    decision equivocada: mientras diga que son cuentas que esperan y no reglas
    rotas, nadie va a proponer borrarlas.

    ⚠️ **El texto ya no vive en la pantalla, vive en el catálogo de idiomas**
    (2026-08-19). La pantalla dice `t("huerfanasTitulo")` y el texto está en
    `messages/es.json` y `messages/en.json`. Esta prueba antes buscaba el
    literal dentro del `.tsx` y por eso se rompió al extraer los textos: el
    criterio seguía intacto, cambió de archivo.

    Y ahora mira **los dos idiomas**. Si solo mirara el español, la pantalla en
    inglés podría volver a llamarlas reglas rotas sin que nadie se enterara —
    que es el mismo agujero de antes, corrido un idioma.
    """
    import json

    from tests._rutas import FRONT

    pantalla = (FRONT / "app" / "break-e" / "sin-clasificar" / "page.tsx").read_text(
        encoding="utf-8")
    assert 'huerfanasTitulo' in pantalla, (
        "la seccion ya no usa la clave del titulo: revisar que no se haya "
        "reemplazado por un texto escrito a mano")

    esperado = {"es": "todavía sin monto", "en": "still with no amount"}
    prohibido = {"es": "se renombró", "en": "was renamed"}
    for idioma, trozo in esperado.items():
        cat = json.loads((FRONT / "messages" / f"{idioma}.json").read_text(
            encoding="utf-8"))
        titulo = cat["breakEven"]["huerfanasTitulo"]
        assert trozo in titulo, (
            f"[{idioma}] la seccion volvio a presentarlas como reglas rotas: "
            f"{titulo!r}")
        entero = json.dumps(cat, ensure_ascii=False)
        assert prohibido[idioma] not in entero, (
            f"[{idioma}] volvio el texto que decia que son cuentas renombradas: "
            "medido, es falso")


# ─── Los cuatro defectos que encontro la auditoria del 2026-08-17 ────────────

def test_reparte_exige_que_el_departamento_NETEE_cero():
    """⚠️ El filtro marcaba «reparte» a cualquiera con una cuenta 4900/4901/4999
    y le borraba TODAS las filas de costo.

    En el `BUDGET Working 2027` el reparto de Villas y Residencias asienta un
    credito `4999` de −$92.176,74 **dentro del propio 0110**, asi que Rooms
    quedaba marcado como repartidor y se caia entero de la base: **$553.855,87**
    del departamento con el 59% del ingreso. En pantalla mostraba 97,6% de
    margen contra el 82,9% del P&L.

    La justificacion escrita —«reparten todo su costo y netean 0,00»— es cierta
    para Cafeteria (0,00) y Lavanderia (0,01), y medible­mente falsa para Rooms,
    que netea $553.855,85. Ahora se comprueba, no se supone.
    """
    assert bb.UMBRAL_NETEA_CERO > 0
    import inspect
    fuente = inspect.getsource(bb.construir)
    assert "UMBRAL_NETEA_CERO" in fuente, (
        "volvio a marcar «reparte» solo por la cuenta, sin mirar si netea cero")


def test_se_completa_lo_que_el_PL_calcula_y_el_GL_no_tiene():
    """El fee de gerencia (3%), la reserva de capital (4%) y el impuesto no
    existen como fila de GL: el motor los calcula como porcentaje.

    Medido en el `Working 2027`: faltaban $446.181,84 de costo y $559.115,34 de
    impuesto. El modulo declaraba un neto de $2.882.508 contra $1.304.602 del
    reporte, y la unica validacion en pantalla decia «$0,00 ✓».
    """
    import inspect
    fuente = inspect.getsource(bb._completar_con_lo_que_calcula_el_pl)
    # Las dos trampas medidas tienen que seguir cubiertas:
    assert "reglas_gl[code]" in fuente, (
        "se inyecta sin la cuenta real: el impuesto cae a 100% fijo y el "
        "equilibrio se va $680k arriba")
    assert "abs(suma - brecha)" in fuente, (
        "se inyecta sin comprobar que las lineas ausentes expliquen la brecha: "
        "mete plata que no falta")


def test_lo_que_no_se_puede_explicar_NO_se_tapa():
    """Si las lineas ausentes no explican la brecha, no se completa nada y se
    avisa. Un hueco que no se puede atribuir es lo que no puede volver a pasar
    en silencio — en `ACTUAL 2024` la brecha es −$3.085 y las lineas ausentes
    suman $11.757: taparlo seria inventar."""
    import inspect
    fuente = inspect.getsource(bb._completar_con_lo_que_calcula_el_pl)
    assert "avisos.append" in fuente
