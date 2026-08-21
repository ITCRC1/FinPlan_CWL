# -*- coding: utf-8 -*-
"""El A&B abierto en comida / bebida / misceláneos.

**De dónde salió (owner, 2026-08-14).** Su cuadro de cierre abre el A&B por los
dos lados —venta y costo— y saca el % de costo de cada uno.

**Cómo cambió a mitad de camino.** La primera versión agrupaba **adivinando por
el nombre** de la cuenta («Food», «Beer», «Bev Cost»…), porque el P&L tenía UNA
sola línea para todo el A&B. Después el owner pidió separar el costo de ventas y
partir el ingreso, así que el corte pasó a vivir en el mapeo: `REV_FB`,
`REV_FB_BEV`, `REV_FB_MISC`, `COS_FB_FOOD`, `COS_FB_BEV`, `COS_FB_MISC`.

La heurística se borró. El grupo de una cuenta se decide en un solo lugar —el
mapeo— y no en dos que pueden discrepar.

Dos cosas que aparecieron por el camino y quedan anotadas acá:

* `OPEX_FB` **no era el costo de ventas**: llevaba también la planilla del
  departamento y 50 cuentas de opex. Tomarlo entero triplicaba el % de costo, y
  seguía pareciendo un porcentaje razonable de mirar.
* La línea `REV_PRIVATE_BAR` **no es un bar**: sus cuentas se llaman «Ingreso
  Tienda» y sus costos son ropa y zapatos. Parear «F&B Beverage» contra ella
  —lo que más se parecía por el nombre— habría dado un número que se ve bien y
  está mal.
"""
import io
import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SEED = RAIZ / "app" / "seed_data" / "mapping_pl.json"
FUENTE = RAIZ / "app" / "api" / "fb_detalle_api.py"


def _cuentas(linea: str, dept: str = "0120") -> set[str]:
    datos = json.loads(SEED.read_text(encoding="utf-8"))
    return {str(r["account_code"]) for r in datos["account_mapping"]
            if r.get("report_line_code") == linea
            and str(r.get("dept_code") or "") == dept}


def _src() -> str:
    return io.open(FUENTE, encoding="utf-8").read()


# ─────────────────────────────────────────────────────────────────────────────
# El corte vive en el mapeo
# ─────────────────────────────────────────────────────────────────────────────

def test_las_seis_lineas_del_cuadro_existen_y_tienen_cuentas():
    """Si una queda vacía, esa fila del cuadro sale en cero y el desglose deja
    de sumar el total del A&B — sin que nada avise."""
    from app.api.fb_detalle_api import LINEAS_COS, LINEAS_ING
    for lineas in (LINEAS_ING, LINEAS_COS):
        for grupo, code in lineas.items():
            assert _cuentas(code), f"la línea {code} ({grupo}) no tiene cuentas"


def test_ninguna_cuenta_esta_en_dos_grupos():
    """Una cuenta en dos líneas se contaría dos veces: el total del A&B saldría
    inflado y cada fila por separado se vería bien."""
    from app.api.fb_detalle_api import LINEAS_COS, LINEAS_ING
    for lineas in (LINEAS_ING, LINEAS_COS):
        vistas: dict[str, str] = {}
        for grupo, code in lineas.items():
            for cta in _cuentas(code):
                assert cta not in vistas, (
                    f"la cuenta {cta} está en {vistas.get(cta)} y en {grupo}")
                vistas[cta] = grupo


def test_el_costo_es_solo_clase_5():
    """⚠️ Antes se tomaba `OPEX_FB` entero, que lleva la planilla del
    departamento y 50 cuentas de opex. El «F&B Food Cost» del owner son
    $8,293.16 sobre $21,986.55 —37.7%—; con la planilla adentro se iba al triple
    y seguía pareciendo un porcentaje razonable de mirar."""
    from app.api.fb_detalle_api import LINEAS_COS
    for grupo, code in LINEAS_COS.items():
        for cta in _cuentas(code):
            assert cta.startswith("5"), (
                f"{cta} en {code} no es clase 5: infla el costo de ventas")


def test_el_ingreso_es_solo_clase_4():
    from app.api.fb_detalle_api import LINEAS_ING
    for grupo, code in LINEAS_ING.items():
        for cta in _cuentas(code):
            assert cta.startswith("4"), f"{cta} en {code} no es un ingreso"


def test_el_reparto_es_el_que_marco_el_owner():
    """El mapeo que mandó sobre su propia pantalla de Account Mapping."""
    assert _cuentas("REV_FB") == {"4110"}
    assert _cuentas("REV_FB_BEV") == {"4120", "4125", "4130", "4131"}
    assert _cuentas("REV_FB_MISC") == {"4132"}
    assert _cuentas("COS_FB_FOOD") == {"5101", "5102", "5103"}
    assert _cuentas("COS_FB_BEV") == {"5150", "5151", "5152", "5153", "5154", "5155"}
    assert _cuentas("COS_FB_MISC") == {"5161", "5162", "5163", "5164", "5165"}


def test_los_traspasos_entre_cocina_y_barra_van_cruzados():
    """«Bar to Food» (5102) es bebida que se consume en cocina: su costo es de
    COMIDA. «Food to Bar» (5155) es al revés. Agrupándolos por la primera
    palabra del nombre los dos caen mal, y los dos porcentajes salen torcidos en
    direcciones opuestas — peor que un solo error, porque el total sigue
    cuadrando."""
    assert "5102" in _cuentas("COS_FB_FOOD")     # Bar to Food
    assert "5155" in _cuentas("COS_FB_BEV")      # Food to Bar


def test_ya_no_se_adivina_por_el_nombre():
    """La heurística se borró a propósito. Si vuelve, el grupo de una cuenta se
    decidiría en DOS lugares —el mapeo y una tabla de palabras— y el día que
    discrepen nadie va a saber cuál manda."""
    src = _src()
    assert "def clasificar" not in src
    assert "LINEAS_ING" in src and "LINEAS_COS" in src


def test_las_cuentas_no_estan_escritas_a_mano():
    src = _src()
    for numero in ("4110", "4125", "5101", "5150"):
        assert f'"{numero}"' not in src, (
            f"la cuenta {numero} quedó escrita a mano en el endpoint")


def test_el_desglose_suma_el_total_por_construccion():
    src = _src()
    assert 'fila["ing_total"] = sum(float(d[f"ing_{g}"]) for g in GRUPOS)' in src
    assert 'fila["cos_total"] = sum(float(d[f"cos_{g}"]) for g in GRUPOS)' in src


def test_no_suma_las_dos_fuentes():
    """El GL y los checkbooks se ELIGEN, no se suman. Sumarlos da exactamente el
    doble — ya pasó con el gasto por clase (2,100,673 contra 1,170,402)."""
    src = _src()
    assert "if gl:" in src and "else:" in src


def test_el_departamento_de_ab_es_el_0120():
    from app.api.fb_detalle_api import DEPT_FB
    assert DEPT_FB == "0120"


def test_la_linea_private_bar_no_tiene_cuentas_de_bar():
    """Deja constancia del hallazgo: si alguien quiere parear «F&B Beverage»
    contra `REV_PRIVATE_BAR` porque el nombre calza, acá ve que sus cuentas son
    de TIENDA."""
    datos = json.loads(SEED.read_text(encoding="utf-8"))
    nombres = " ".join(
        (r.get("account_name_example") or "") for r in datos["account_mapping"]
        if r.get("report_line_code") == "REV_PRIVATE_BAR").lower()
    assert "tienda" in nombres
    for palabra in ("beer", "liquor", "wine", "beverage"):
        assert palabra not in nombres, (
            "REV_PRIVATE_BAR ahora sí tiene cuentas de bar; revisar si el "
            "desglose de A&B tiene que incluirla")


def test_el_cargador_del_motor_no_trae_el_nombre_de_la_cuenta():
    """`recalc.load_active_account_mappings` devuelve cinco campos para el motor
    del P&L. Fue la causa de que todas las cuentas de A&B salieran «sin
    clasificar» cuando el grupo dependía del nombre. Queda anotado por si
    alguien vuelve a apoyarse en él."""
    import inspect
    from app.engine import recalculate
    assert "account_name_example" not in inspect.getsource(
        recalculate.load_active_account_mappings)
