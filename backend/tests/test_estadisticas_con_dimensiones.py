# -*- coding: utf-8 -*-
"""Las estadísticas de clase 9: catálogo, dimensiones y la fila que no se pierde.

**De dónde salió (owner, 2026-08-14).** Pidió abrir cuentas para todo lo que el
sistema cuenta —FTE, noches por tipo de habitación, kilos de lavandería, covers,
tratamientos de spa, pax de tours y bote, headcount, horas extras e
incapacidades— y cargarlas **por departamento y por posición**.

El escaneo encontró que «cuenta clase 9» eran TRES códigos escritos a mano en un
diccionario de Python, y que cualquier otra 9xxx que llegara en un archivo se
descartaba en silencio absoluto. Estas pruebas son las reglas que impiden que
eso vuelva.
"""
import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]
CATALOGO = RAIZ / "app" / "seed_data" / "stats_catalog.json"


# ─────────────────────────────────────────────────────────────────────────────
# El catálogo
# ─────────────────────────────────────────────────────────────────────────────

def test_el_catalogo_se_lee_y_se_valida():
    """`leer_catalogo` valida al leer. Si el JSON está torcido, truena acá y no
    en el arranque de producción."""
    from app.seed_stats import leer_catalogo
    cuentas = leer_catalogo()
    assert len(cuentas) >= 38, "el catálogo quedó más chico de lo que se sembró"


def test_ninguna_cuenta_repetida():
    from app.seed_stats import leer_catalogo
    codes = [c["code"] for c in leer_catalogo()]
    assert len(codes) == len(set(codes))


def test_las_tres_de_siempre_siguen_ahi():
    """9010/9020/9060 son las únicas que el sistema ya reportaba. Si alguna se
    cae del catálogo, el P&L pierde ocupación, ADR y RevPAR de un solo golpe."""
    from app.seed_stats import leer_catalogo
    por_code = {c["code"]: c for c in leer_catalogo()}
    for code, campo in (("9010", "rooms_available"), ("9020", "rooms_occupied"),
                        ("9060", "guests")):
        assert code in por_code, f"desapareció la cuenta {code}"
        assert por_code[code].get("legado") == campo, (
            f"{code} dejó de apuntar a `scenario_stats.{campo}`; se seguiría "
            "cargando pero el P&L dejaría de verlo"
        )


def test_el_catalogo_del_seed_conoce_las_del_importador():
    """`STAT_BY_ACCT` es el atajo que ya existía. No puede tener una cuenta que
    el catálogo no declare: sería un dato que entra sin definición."""
    from app.importers.gl_detail_importer import STAT_BY_ACCT
    from app.seed_stats import leer_catalogo
    codes = {c["code"] for c in leer_catalogo()}
    faltan = set(STAT_BY_ACCT) - codes
    assert not faltan, f"el importador conoce {sorted(faltan)} y el catálogo no"


def test_los_rangos_documentados_se_respetan():
    """CLAUDE.md §18.1 fija los rangos. Inventar códigos fuera de ellos deja el
    sistema y la documentación diciendo cosas distintas."""
    from app.seed_stats import leer_catalogo
    grupos_validos = {"9000", "9110", "9201", "9400", "9500", "9600", "9700",
                      "9900", "9980"}
    for c in leer_catalogo():
        assert c["grupo"] in grupos_validos, (
            f"{c['code']} declara el grupo {c['grupo']}, que no está en "
            f"CLAUDE.md §18.1 ni es uno de los agregados a propósito"
        )
        assert c["code"] >= c["grupo"], (
            f"{c['code']} dice pertenecer al grupo {c['grupo']} pero es menor"
        )


def test_aca_no_entra_dinero():
    """⚠️ La regla más importante del catálogo (owner, 2026-08-14).

    Habitaciones, pax y kilos son cantidades: viven en clase 9 sin discutirle
    nada al P&L. **La venta no.** Un ingreso de habitaciones abierto por canal
    es la MISMA plata que ya reporta `REV_ROOMS`, partida de otra forma; el día
    que la suma no diera igual habría dos verdades sobre el mismo dinero y
    ninguna avisaría — que es como aparecieron los $40,613 y los $71,556.

    La primera versión traía tres cuentas de venta que se cuadraban contra el
    P&L con una prueba. El owner las descartó, y es lo correcto: cuadrarlas
    MITIGA el riesgo; no tenerlas lo ELIMINA.
    """
    from app.seed_stats import leer_catalogo
    for c in leer_catalogo():
        assert not c.get("dinero"), f"{c['code']} entró como cuenta de dinero"
        assert c["unidad"] != "usd", (
            f"{c['code']} está en dólares. Las estadísticas son cantidades; la "
            "plata la reporta el P&L."
        )


def test_las_dimensiones_declaradas_existen():
    from app.models.stat_account import DIMENSIONES
    from app.seed_stats import leer_catalogo
    for c in leer_catalogo():
        malas = set(c.get("dims", [])) - set(DIMENSIONES)
        assert not malas, f"{c['code']} declara dimensiones inexistentes: {malas}"


def test_las_cuentas_de_planilla_se_abren_por_posicion():
    """Lo que el owner pidió explícito: horas y headcount por departamento Y por
    posición. Si alguna pierde la dimensión, el reporte de planilla se queda sin
    el corte que la justificaba."""
    from app.seed_stats import leer_catalogo
    por_code = {c["code"]: c for c in leer_catalogo()}
    for code in ("9900", "9901", "9980", "9981", "9985", "9986"):
        dims = set(por_code[code].get("dims", []))
        assert {"DEPT", "POSITION"} <= dims, (
            f"{code} dejó de abrirse por departamento y posición"
        )


def test_el_headcount_no_se_suma_entre_meses():
    """Un padrón no es aditivo: doce meses de 129 personas no son 1,548
    personas. Mismo criterio que `ClubMembershipStat`."""
    from app.seed_stats import leer_catalogo
    por_code = {c["code"]: c for c in leer_catalogo()}
    assert por_code["9900"]["agrega"] == "FIN"


def test_el_json_valida_lo_que_promete():
    """Las validaciones de `leer_catalogo` tienen que fallar de verdad, no ser
    decorativas."""
    import pytest
    from app import seed_stats

    bueno = json.loads(CATALOGO.read_text(encoding="utf-8"))

    def con(cuentas):
        datos = dict(bueno, cuentas=cuentas)
        original = seed_stats.ARCHIVO
        tmp = RAIZ / "tests" / "_tmp_stats.json"
        tmp.write_text(json.dumps(datos), encoding="utf-8")
        seed_stats.ARCHIVO = tmp
        try:
            return seed_stats.leer_catalogo()
        finally:
            seed_stats.ARCHIVO = original
            tmp.unlink(missing_ok=True)

    base = {"code": "9111", "grupo": "9110", "nombre_es": "x", "unidad": "covers"}

    with pytest.raises(ValueError, match="9 \\+ 3"):
        con([dict(base, code="7065")])
    with pytest.raises(ValueError, match="repetido"):
        con([base, dict(base)])
    with pytest.raises(ValueError, match="[Dd]imensión desconocida"):
        con([dict(base, dims=["PLANETA"])])
    with pytest.raises(ValueError, match="SUM o FIN"):
        con([dict(base, agrega="PROMEDIO")])
    with pytest.raises(ValueError, match="CANTIDADES"):
        con([dict(base, dinero=True)])
    with pytest.raises(ValueError, match="CANTIDADES"):
        con([dict(base, unidad="usd")])


# ─────────────────────────────────────────────────────────────────────────────
# La tabla de valores
# ─────────────────────────────────────────────────────────────────────────────

def test_las_dimensiones_no_son_nulables():
    """⚠️ En Postgres dos NULL no son iguales entre sí. Una restricción de
    unicidad sobre columnas nulables **deja pasar duplicados**: el mismo dato
    entraría dos veces y el total saldría doble sin que nada avise.

    Por eso las dimensiones vacías son cadena vacía. Esta prueba existe porque
    volver a `nullable=True` se ve inocente en una revisión de código.
    """
    from app.models.statistical_entry import StatisticalEntry
    cols = StatisticalEntry.__table__.columns
    for nombre in ("dept_code", "position_code", "room_type_code",
                   "dim_type", "dim_code"):
        c = cols[nombre]
        assert not c.nullable, (
            f"{nombre} quedó nulable: la restricción de unicidad deja de "
            "impedir el duplicado y el total se dobla en silencio"
        )
        assert c.default is not None and c.default.arg == "", (
            f"{nombre} perdió su valor por defecto de cadena vacía"
        )


def test_la_llave_unica_incluye_todas_las_dimensiones():
    """Si una dimensión se queda fuera de la llave, dos aperturas distintas de
    la misma cuenta chocan entre sí y una pisa a la otra."""
    from sqlalchemy import UniqueConstraint
    from app.models.statistical_entry import StatisticalEntry
    uq = [c for c in StatisticalEntry.__table__.constraints
          if isinstance(c, UniqueConstraint)]
    assert len(uq) == 1
    assert {c.name for c in uq[0].columns} == {
        "scenario_id", "account_code", "month", "dept_code", "position_code",
        "room_type_code", "dim_type", "dim_code",
    }


def test_la_estadistica_se_borra_con_el_escenario():
    """Sin cascada, borrar un escenario deja estadísticas huérfanas que después
    aparecen sumadas en otro lado."""
    from app.models.statistical_entry import StatisticalEntry
    fk = list(StatisticalEntry.__table__.c.scenario_id.foreign_keys)[0]
    assert fk.ondelete == "CASCADE"


def test_la_migracion_declara_las_dimensiones_no_nulables():
    """El modelo y la migración tienen que decir lo mismo. Si la migración las
    crea nulables, la base real permite el duplicado aunque el modelo diga que
    no — y las pruebas del modelo seguirían en verde."""
    src = (RAIZ / "alembic" / "versions" /
           "106_estadisticas_con_dimensiones.py").read_text(encoding="utf-8")
    for nombre in ("dept_code", "position_code", "room_type_code",
                   "dim_type", "dim_code"):
        linea = [l for l in src.splitlines() if f'"{nombre}"' in l and "Column" in l]
        assert linea, f"la migración no crea la columna {nombre}"
        assert "nullable=False" in linea[0] and 'server_default=""' in linea[0], (
            f"{nombre} en la migración no es NOT NULL DEFAULT ''"
        )


# ─────────────────────────────────────────────────────────────────────────────
# El importador ya no se traga las filas
# ─────────────────────────────────────────────────────────────────────────────

def test_el_importador_recoge_toda_la_clase_9():
    """La regla que faltaba. Hasta 2026-08-14 el bloque de clase 9 hacía
    `continue` sin más si la cuenta no era una de las tres conocidas: la fila
    desaparecía sin dejar rastro en ninguna parte."""
    import io
    src = io.open(RAIZ / "app" / "importers" / "gl_detail_importer.py",
                  encoding="utf-8").read()
    assert 'blk["stats_9"].append' in src, (
        "el importador dejó de recoger las filas de clase 9; las desconocidas "
        "vuelven a perderse en silencio"
    )
    assert "def filas_clase9" in src


def test_la_fila_de_clase_9_conserva_el_departamento():
    """Sin departamento no hay forma de cargar kilos por depto ni horas por
    posición, que es justo lo que se pidió."""
    import io
    src = io.open(RAIZ / "app" / "importers" / "gl_detail_importer.py",
                  encoding="utf-8").read()
    bloque = src[src.index('blk["stats_9"].append'):]
    bloque = bloque[:bloque.index("continue")]
    for campo in ("account_code", "dept_code", "meses", "legado"):
        assert f'"{campo}"' in bloque, f"la fila de clase 9 perdió `{campo}`"
