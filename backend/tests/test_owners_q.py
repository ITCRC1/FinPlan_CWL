"""Owners Q — el fixture dorado de junio 2026 como test de regresión.

QUÉ PRUEBA ESTO Y QUÉ NO.

Prueba el MOTOR: que las 48 filas se resuelvan en el orden correcto, que los
subtotales y los calculados reproduzcan al centavo el archivo que SCP recibió,
que las estadísticas salgan de donde tienen que salir, que las guardas de
división por cero devuelvan vacío y no cero, y que la convención de signos sea
reversible.

NO prueba la cañería que va del GL a las `Línea P&L` — eso es el P&L, que ya
tiene sus propias pruebas, y se valida en vivo con `/reports/owners-q/`.

El truco para alimentar el motor sin base: cada fila DETAIL del fixture se
inyecta como si todo su monto viniera de su PRIMERA `Línea P&L`. El motor no
sabe la diferencia —solo suma— y así los subtotales quedan probados contra
números reales sin depender de que junio esté cargado.
"""
import csv
import json
import pathlib
from decimal import Decimal

import pytest

from app.engine import owners_q as motor

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "fixture_SCPCWL_JUN2026.csv"
SEED = pathlib.Path(__file__).parent.parent / "app" / "seed_data" / "owners_q.json"

TOL_MONTO = Decimal("0.01")
TOL_RATIO = Decimal("0.0001")

#: Las columnas de valor de cada bloque y el bloque al que pertenecen.
COL_DE_BLOQUE = {"ptd_actual": "A", "ptd_budget": "E", "ptd_py": "K",
                 "ytd_actual": "R", "ytd_budget": "V", "ytd_py": "AB"}


# ─── Carga ────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def catalogo():
    datos = json.loads(SEED.read_text(encoding="utf-8"))
    filas = datos["report_lines"]
    ruteo = {m["linea_pl"]: m["report_code"] for m in datos["report_line_mapping"]}
    return filas, ruteo


@pytest.fixture(scope="module")
def fixture_filas():
    """{report_code: {columna: Decimal|None}} — celda vacía queda en None."""
    out = {}
    with open(FIXTURE, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            celdas = {}
            for k, v in r.items():
                if "__" not in k:
                    continue
                col = k.split("__")[0]
                celdas[col] = None if (v or "").strip() == "" else Decimal(v)
            out[r["report_code"]] = celdas
    return out


def _datos_desde_fixture(filas, fx, columna) -> motor.DatosPeriodo:
    """Inyecta los DETAIL del fixture como `Línea P&L`."""
    lineas = {}
    for f in filas:
        if f["line_type"] != "DETAIL":
            continue
        v = fx.get(f["report_code"], {}).get(columna)
        lps = f.get("lineas_pl") or []
        if not lps:
            continue                      # fila que siempre da 0 y no tiene líneas
        v = Decimal(0) if v is None else v
        # Las filas `signed` las NIEGA el motor al pasarlas a signo natural, y
        # el fixture ya trae el valor natural. Se inyecta invertido para que el
        # viaje de ida y vuelta devuelva lo que SCP recibió.
        if f["nature"] == "signed":
            v = -v
        lineas[lps[0]] = v
        for extra in lps[1:]:
            lineas[extra] = Decimal(0)

    # El ADR (fila 11) sale de REV_ROOMS sin REV_ROOMS_OTHER: se despeja del
    # propio fixture para no asumirlo.
    adr = fx["STAT_ADR"][columna]
    occ = fx["STAT_ROOMS_OCCUPIED"][columna]
    if adr is not None and occ is not None:
        rooms_total = lineas.get("REV_ROOMS", Decimal(0))
        lineas["REV_ROOMS"] = adr * occ
        lineas["REV_ROOMS_OTHER"] = rooms_total - adr * occ

    return motor.DatosPeriodo(lineas=lineas, rooms_occupied=occ or Decimal(0))


# ─── El fixture dorado ────────────────────────────────────────────────────────
@pytest.mark.parametrize("bloque,columna", sorted(COL_DE_BLOQUE.items()))
def test_subtotales_reproducen_el_fixture(catalogo, fixture_filas, bloque, columna):
    """Los 11 SUBTOTAL/CALC contra el archivo real de junio, celda por celda."""
    filas, ruteo = catalogo
    datos = _datos_desde_fixture(filas, fixture_filas, columna)
    dias = 30 if bloque.startswith("ptd") else 181       # junio / ene-jun 2026
    calc = motor.valores_de_filas(filas, ruteo, datos, dias, 30)

    malas = []
    for f in filas:
        if f["line_type"] not in ("SUBTOTAL", "CALC"):
            continue
        esperado = fixture_filas[f["report_code"]][columna]
        obtenido = calc[f["report_code"]]
        if esperado is None:
            continue
        if abs(Decimal(obtenido) - esperado) > TOL_MONTO:
            malas.append(f"f{f['row_no']} {f['report_code']}: "
                         f"esperado {esperado} obtenido {obtenido}")
    assert not malas, "\n".join(malas)


@pytest.mark.parametrize("bloque,columna", sorted(COL_DE_BLOQUE.items()))
def test_estadisticas_reproducen_el_fixture(catalogo, fixture_filas, bloque, columna):
    """Filas 9 a 14: disponibles, ocupadas, ADR, Occ%, RevPar y Total RevPar."""
    filas, ruteo = catalogo
    datos = _datos_desde_fixture(filas, fixture_filas, columna)
    dias = 30 if bloque.startswith("ptd") else 181
    calc = motor.valores_de_filas(filas, ruteo, datos, dias, 30)

    for code in ("STAT_ROOMS_AVAILABLE", "STAT_ROOMS_OCCUPIED", "STAT_ADR",
                 "STAT_OCC", "STAT_REVPAR", "STAT_TOTAL_REVPAR"):
        esperado = fixture_filas[code][columna]
        if esperado is None:
            continue
        obtenido = Decimal(calc[code])
        tol = TOL_MONTO if code in ("STAT_ROOMS_AVAILABLE", "STAT_ROOMS_OCCUPIED") else TOL_RATIO
        assert abs(obtenido - esperado) <= tol, \
            f"{code} col {columna}: esperado {esperado} obtenido {obtenido}"


def test_cifras_ancla(catalogo, fixture_filas):
    """Las 7 cifras ancla del §9.1 — el Gate B."""
    anclas = {
        "TOT_OPERATING_REVENUE": (Decimal("153902.6928"), Decimal("3447426.3342")),
        "TOT_DEPARTMENTAL_EXPENSES": (Decimal("128784.8813"), Decimal("1243555.1060")),
        "TOT_UNDISTRIBUTED": (Decimal("176980.0274"), Decimal("1112333.8184")),
        "GOP": (Decimal("-151862.2159"), Decimal("1091537.4097")),
        "EBITDA": (Decimal("-164890.7759"), Decimal("922911.6259")),
        "ADJUSTED_EBITDA": (Decimal("-171705.0094"), Decimal("738293.0621")),
        "NET_INCOME_BEFORE_TAXES": (Decimal("-199667.9702"), Decimal("469643.4910")),
    }
    filas, ruteo = catalogo
    for columna, dias, idx in (("A", 30, 0), ("R", 181, 1)):
        datos = _datos_desde_fixture(filas, fixture_filas, columna)
        calc = motor.valores_de_filas(filas, ruteo, datos, dias, 30)
        for code, esperados in anclas.items():
            assert abs(Decimal(calc[code]) - esperados[idx]) <= TOL_MONTO, \
                f"{code} col {columna}"


@pytest.mark.parametrize("columna", ["A", "E", "K", "R", "V", "AB"])
def test_identidades(catalogo, fixture_filas, columna):
    """Las identidades del §9.2 sobre los valores del propio fixture."""
    filas, _ = catalogo
    calculadas = [{
        "report_code": f["report_code"], "nature": f["nature"],
        "celdas": {columna: fixture_filas[f["report_code"]][columna]},
    } for f in filas]
    assert motor.verificar_identidades(calculadas, columna) == []


def test_d1_la_brecha_es_other_rooms_revenue(catalogo, fixture_filas):
    """§9.3 — la brecha entre el ADR y el POR de la fila 16 es `REV_ROOMS_OTHER`.

    PTD: 79.310,6108 − (478,63 × 162) = 1.772,55 — calza al centavo con el spec.

    ⚠️ YTD: el spec dice 17.892,89 y da **17.872,89**. El error está en el
    documento, no en el dato: `619,33 × 2.854 = 1.767.567,82`, no 1.767.547,82.
    El fixture trae 1.785.440,7114 (idéntico al spec) y la resta da 17.872,89.
    Son $20,00 exactos de aritmética mal hecha en la prosa del §9.3.

    Se ancla al FIXTURE, que es la fuente dorada, no a la prosa. Y no se ajusta
    el ADR para que calce con el documento — que es justo lo que el §9.3
    prohíbe hacer.
    """
    for columna, esperado in (("A", Decimal("1772.55")), ("R", Decimal("17872.89"))):
        rooms = fixture_filas["REV_ROOMS_TOTAL"][columna]
        adr = fixture_filas["STAT_ADR"][columna]
        occ = fixture_filas["STAT_ROOMS_OCCUPIED"][columna]
        brecha = rooms - adr * occ
        assert abs(brecha - esperado) <= Decimal("0.01"), \
            f"col {columna}: brecha {brecha}, esperada {esperado}"


def test_revpar_no_es_adr_por_occ(fixture_filas):
    """R4 — la inconsistencia es INTENCIONAL. Si esto empieza a fallar es que
    alguien "arregló" el ADR y rompió la fidelidad con lo que SCP recibe."""
    adr = fixture_filas["STAT_ADR"]["A"]
    occ = fixture_filas["STAT_OCC"]["A"]
    revpar = fixture_filas["STAT_REVPAR"]["A"]
    assert abs(revpar - adr * occ) > Decimal("1")


# ─── Reglas del motor ─────────────────────────────────────────────────────────
def test_la_convencion_es_reversible(catalogo, fixture_filas):
    """Invertir dos veces devuelve el original (§6)."""
    filas, _ = catalogo
    original = [{
        "report_code": f["report_code"], "nature": f["nature"],
        "celdas": {c: Decimal("100.5") for c in motor.COLUMNAS_VARIACION},
    } for f in filas]
    copia = [{**f, "celdas": dict(f["celdas"])} for f in original]
    motor.aplicar_convencion(copia)
    motor.aplicar_convencion(copia)
    for a, b in zip(original, copia):
        assert a["celdas"] == b["celdas"], a["report_code"]


def test_la_convencion_solo_toca_los_gastos(catalogo):
    filas, _ = catalogo
    calculadas = [{
        "report_code": f["report_code"], "nature": f["nature"],
        "celdas": {c: Decimal("10") for c in motor.COLUMNAS_VARIACION},
    } for f in filas]
    motor.aplicar_convencion(calculadas)
    for f in calculadas:
        esperado = Decimal("-10") if f["nature"] == "expense" else Decimal("10")
        assert f["celdas"]["I"] == esperado, f["report_code"]


def test_interest_expense_nunca_se_invierte(catalogo):
    """La fila 52 es `signed`: entra con su signo natural y la 56 la SUMA."""
    filas, _ = catalogo
    f52 = next(f for f in filas if f["report_code"] == "INTEREST_EXPENSE")
    assert f52["nature"] == "signed"
    f56 = next(f for f in filas if f["report_code"] == "NET_INCOME_BEFORE_TAXES")
    signos = {o["code"]: o["sign"] for o in f56["operandos"]}
    assert signos["INTEREST_EXPENSE"] == 1, "la 52 se SUMA en la 56"
    assert signos["TOT_DA"] == -1


def test_d7_financial_losses_va_a_la_fila_52(catalogo):
    """D7 RESUELTO con evidencia numérica, no por criterio.

    El default del spec mandaba `FINANCIAL_LOSSES` a la fila 46 (OTHER NON OP).
    Medido contra el fixture en la columna Prior Year, la alternativa —fila 52,
    junto al interés bancario— es la única que explica las DOS filas a la vez:

        FL(jun-25) = −232,13 → f46 4.709,41−(−232,13) = 4.941,54  ✔ fixture
                               f52 −(128,49+(−232,13)) =  103,64  ✔ fixture
        FL(ytd)    = +579,30 → f46 15.899,77−579,30 = 15.320,47   ✔ fixture
                               f52 −(1.069,96+579,30) = −1.649,26 ✔ fixture

    El diferencial cambiario puede ser GANANCIA (junio 2025 lo fue), y por eso
    la fila 52 es `signed` y la 56 la suma.
    """
    filas, ruteo = catalogo
    f46 = next(f for f in filas if f["report_code"] == "NONOP_OTHER")
    f52 = next(f for f in filas if f["report_code"] == "INTEREST_EXPENSE")
    assert f46["lineas_pl"] == ["OTHER_EXPENSES"]
    assert set(f52["lineas_pl"]) == {"BANK_INTEREST", "FINANCIAL_LOSSES"}
    assert ruteo["FINANCIAL_LOSSES"] == "INTEREST_EXPENSE"


def test_la_fila_signed_pasa_a_signo_natural(catalogo):
    """El P&L guarda el gasto en positivo; la fila 52 lo reporta natural.

    Verificado contra el fixture: en las dos columnas de Budget la diferencia
    era exactamente la negación (−226,01 vs +226,01 en el mes).
    """
    filas, ruteo = catalogo
    datos = motor.DatosPeriodo(
        lineas={"BANK_INTEREST": Decimal("226.01"), "FINANCIAL_LOSSES": Decimal("0")},
        rooms_occupied=Decimal("100"))
    calc = motor.valores_de_filas(filas, ruteo, datos, 900, 1)
    assert calc["INTEREST_EXPENSE"] == Decimal("-226.01")

    # Diferencial cambiario a favor y mayor que el interés → la fila da POSITIVO.
    datos2 = motor.DatosPeriodo(
        lineas={"BANK_INTEREST": Decimal("128.49"),
                "FINANCIAL_LOSSES": Decimal("-232.13")},
        rooms_occupied=Decimal("100"))
    assert motor.valores_de_filas(filas, ruteo, datos2, 900, 1)["INTEREST_EXPENSE"] \
        == Decimal("103.64")


def test_division_por_cero_da_vacio_no_cero(catalogo):
    """Un mes cerrado por temporada: sin habitaciones no hay ADR, y decir 0
    sería afirmar que se vendió a cero."""
    filas, ruteo = catalogo
    datos = motor.DatosPeriodo(lineas={}, rooms_occupied=Decimal(0))
    calc = motor.valores_de_filas(filas, ruteo, datos, dias_periodo=30, habitaciones=30)
    assert calc["STAT_ADR"] is None
    calc0 = motor.valores_de_filas(filas, ruteo, datos, dias_periodo=0, habitaciones=30)
    assert calc0["STAT_OCC"] is None
    assert calc0["STAT_REVPAR"] is None


def test_porcentaje_var_con_base_cero():
    assert motor._porcentaje_var(Decimal("5"), Decimal("0")) == Decimal("1")
    assert motor._porcentaje_var(Decimal("-5"), Decimal("0")) == Decimal("-1")
    assert motor._porcentaje_var(Decimal("0"), Decimal("0")) == Decimal("0")
    # El denominador va en VALOR ABSOLUTO: con base negativa el signo lo pone
    # el movimiento, no la base. Una base de −6 que se mueve −3 es −50%.
    assert motor._porcentaje_var(Decimal("-3"), Decimal("-6")) == Decimal("-0.5")
    assert motor._porcentaje_var(Decimal("3"), Decimal("-6")) == Decimal("0.5")


def test_el_residual_aterriza_por_naturaleza(catalogo):
    """§3.3 — nada se descarta: ingreso a la 19, gasto a la 36."""
    filas, ruteo = catalogo
    datos = motor.DatosPeriodo(
        lineas={}, rooms_occupied=Decimal("100"),
        residual_revenue=Decimal("1234.56"), residual_expense=Decimal("789.01"))
    calc = motor.valores_de_filas(filas, ruteo, datos, 30, 30)
    assert calc["REV_MISC_TOTAL"] == Decimal("1234.56")
    assert calc["UND_MISC"] == Decimal("789.01")


def test_las_filas_que_siempre_dan_cero_se_imprimen(catalogo):
    """SCP consolida por POSICIÓN: omitirlas le rompe la consolidación."""
    filas, _ = catalogo
    siempre_cero = {"REV_FAIR_TRADE", "UND_ESDG", "NONOP_INCOME",
                    "NONOP_PROPERTY_TAXES", "ASSET_PROJECT_MGMT_FEES"}
    presentes = {f["report_code"] for f in filas}
    assert siempre_cero <= presentes
    assert len(filas) == 48


def test_una_linea_ruteada_a_otra_fila_falla_el_build(catalogo):
    """No cae en un residual silencioso: rompe."""
    filas, ruteo = catalogo
    malo = dict(ruteo)
    malo["OPEX_ROOMS"] = "EXP_FB"       # estaba en EXP_ROOMS
    with pytest.raises(motor.ReporteError):
        motor.valores_de_filas(filas, malo, motor.DatosPeriodo(), 30, 30)


def test_ciclo_en_operandos_se_detecta():
    filas = [
        {"row_no": 1, "report_code": "A", "label": "a", "indent": 1,
         "line_type": "CALC", "nature": "profit", "lineas_pl": [],
         "operandos": [{"code": "B", "sign": 1}]},
        {"row_no": 2, "report_code": "B", "label": "b", "indent": 1,
         "line_type": "CALC", "nature": "profit", "lineas_pl": [],
         "operandos": [{"code": "A", "sign": 1}]},
    ]
    with pytest.raises(motor.ReporteError, match="ciclo"):
        motor.valores_de_filas(filas, {}, motor.DatosPeriodo(), 30, 30)


def test_rooms_available_son_dias_por_capacidad(catalogo):
    """900 en junio (30×30) y 5.430 en el acumulado (181×30) — NO los 990 del
    KPI interno, que usa 33 habitaciones."""
    filas, ruteo = catalogo
    datos = motor.DatosPeriodo(lineas={}, rooms_occupied=Decimal("162"))
    assert motor.valores_de_filas(filas, ruteo, datos, 30, 30)["STAT_ROOMS_AVAILABLE"] == 900
    assert motor.valores_de_filas(filas, ruteo, datos, 181, 30)["STAT_ROOMS_AVAILABLE"] == 5430


def test_dias_del_mes_y_ytd():
    assert motor.dias_del_mes(2026, 6) == 30
    assert motor.dias_ytd(2026, 6) == 181
    assert motor.dias_ytd(2026, 12) == 365


def test_el_catalogo_cubre_las_lineas_pl(catalogo):
    """Cada `Línea P&L` cae en UNA fila, por los dos caminos, sin choques."""
    filas, ruteo = catalogo
    por_catalogo = {lp: f["report_code"] for f in filas for lp in (f["lineas_pl"] or [])}
    assert set(por_catalogo) == set(ruteo)
    assert por_catalogo == ruteo
    assert len(ruteo) == 68


# ─── Versionado del mapeo (§8) ────────────────────────────────────────────────
class _Regla:
    """Doble de una fila de `account_mapping`, con y sin vigencia."""
    def __init__(self, desde=None, hasta=None):
        self.vigente_desde, self.vigente_hasta = desde, hasta


def test_vigencia_una_regla_sin_fechas_rige_siempre():
    from app.engine.recalculate import _vigente_en
    r = _Regla()
    assert _vigente_en(r, None)                 # la vigente hoy
    assert _vigente_en(r, "2020-01")
    assert _vigente_en(r, "2099-12")


def test_vigencia_el_corte_de_d9():
    """La regla vieja de la 7120 muere en jun-2026; la nueva nace en jul-2026.

    Es lo que hace que junio —ya enviado a SCP— siga devolviendo lo mismo al
    reejecutarse, y que el P&L del día a día use la nueva sin ambigüedad.
    """
    from app.engine.recalculate import _vigente_en
    vieja = _Regla(hasta="2026-06")
    nueva = _Regla(desde="2026-07")

    assert _vigente_en(vieja, "2026-06") and not _vigente_en(nueva, "2026-06")
    assert _vigente_en(nueva, "2026-07") and not _vigente_en(vieja, "2026-07")
    # Ningún mes las tiene a las dos: sin solape no hay ambigüedad.
    for anio in (2025, 2026, 2027):
        for m in range(1, 13):
            p = f"{anio}-{m:02d}"
            assert not (_vigente_en(vieja, p) and _vigente_en(nueva, p)), p
    # Y «hoy» agarra solo la nueva: la vieja tiene corte pasado.
    assert _vigente_en(nueva, None) and not _vigente_en(vieja, None)


def test_una_regla_sin_las_columnas_no_revienta():
    """Cualquier cosa anterior a la migración 123 cuenta como vigente siempre."""
    from app.engine.recalculate import _vigente_en
    assert _vigente_en(object(), None)
    assert _vigente_en(object(), "2026-06")


def test_el_periodo_entra_en_la_llave_del_cache():
    """Pedir el mapeo de junio y el de hoy son dos respuestas distintas; si
    compartieran entrada de caché, ganaría la que se calculó primero."""
    import inspect
    from app.engine import recalculate
    src = inspect.getsource(recalculate.load_active_account_mappings)
    assert 'clave = ("account_mapping", report_id, periodo)' in src
    src_anual = inspect.getsource(recalculate._pl_del_ano)
    assert "(_CLAVE_ANUAL, scenario.id, periodo)" in src_anual
