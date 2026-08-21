# -*- coding: utf-8 -*-
"""El mixer: propiedades que no se pueden romper sin que esto avise.

Son pruebas de PROPIEDAD, no de caso: no fijan «55% da 0,7970» —eso cambia el día
que el owner renegocie— sino las reglas que tienen que valerse siempre.
"""
from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.engine import mixer_canales as mixer


@dataclass
class Canal:
    """Sirve igual para un `CanalComercial` que para uno resuelto: el mixer solo
    mira `mix_pct`, `comision_pct` y `entrada`."""
    code: str
    mix_pct: Decimal
    comision_pct: Decimal
    entrada: str = ""
    nombre: str = ""


@dataclass
class Override:
    code: str
    month: int
    mix_pct: Decimal
    comision_pct: Decimal


@dataclass
class Esc:
    year: int
    type: str
    version: str = "v1"
    is_locked: bool = False


def _d(x) -> Decimal:
    return Decimal(str(x))


#: El cuadro del owner (app de Compensación, Corcovado).
CORCOVADO = [
    Canal("B2B", _d("0.55"), _d("0.30"), "Travel Agent"),
    Canal("DIR_WEB", _d("0.15"), _d("0.10"), "Website"),
    Canal("DIR_TEL", _d("0.10"), _d("0.07"), "Direct Client"),
    Canal("CRC_DIRECT", _d("0.07"), _d("0.10"), ""),
    Canal("DIR_GROUPS", _d("0.06"), _d("0.10"), ""),
    Canal("EXEC_DIRECT", _d("0.03"), _d("0.10"), ""),
    Canal("OTA", _d("0.04"), _d("0.00"), "OTA"),
]


# ── La derivación ───────────────────────────────────────────────────────────

def test_el_mix_derivado_conserva_el_total():
    """Ningún sub-canal se pierde ni se cuenta dos veces al rodar a los 3."""
    assert mixer.suma_del_mix(mixer.derivar(CORCOVADO)) == mixer.suma_del_mix(CORCOVADO)


def test_la_comision_es_ponderada_y_no_simple():
    """El promedio simple le daría a la ejecutiva —3% del negocio— el mismo peso
    que al website —15%—, y la comisión derivada saldría más alta de lo que se
    paga de verdad."""
    directos = [c for c in CORCOVADO
                if mixer.ENTRADA_A_COMISION.get(c.entrada, "DIRECT") == "DIRECT"]
    simple = sum(c.comision_pct for c in directos) / len(directos)
    derivado = {d.channel: d for d in mixer.derivar(CORCOVADO)}["DIRECT"]
    assert derivado.commission_pct != simple
    # Y tiene que caer dentro del rango de lo que pagan sus componentes.
    assert min(c.comision_pct for c in directos) <= derivado.commission_pct
    assert derivado.commission_pct <= max(c.comision_pct for c in directos)


def test_un_canal_sin_entrada_es_venta_propia():
    """Los tres de atribución —CRC, grupos, ejecutiva— describen QUIÉN trajo la
    reserva. Igual hay que ubicarlos para la comisión, y son venta propia."""
    solo_atribucion = [c for c in CORCOVADO if not c.entrada]
    derivados = {d.channel: d for d in mixer.derivar(solo_atribucion)}
    assert derivados["DIRECT"].mix_pct == mixer.suma_del_mix(solo_atribucion)
    assert derivados["TA"].mix_pct == 0


def test_siempre_salen_los_tres_canales():
    """Aunque nadie venda por OTA, la fila tiene que existir: si desaparece, la
    pantalla muestra dos canales y se lee como si el tercero no existiera."""
    derivados = mixer.derivar([Canal("X", _d("1"), _d("0"), "Website")])
    assert [d.channel for d in derivados] == list(mixer.DERIVADOS)


def test_el_net_factor_es_el_mismo_de_los_dos_lados():
    """El mixer no puede inventar otra forma de calcular lo que el motor ya
    calcula, o los dos números se separan sin que nadie lo note."""
    from app.models.sales_channel_config import compute_net_factor

    class Fila:
        def __init__(self, d):
            self.mix_pct, self.commission_pct = d.mix_pct, d.commission_pct

    derivados = mixer.derivar(CORCOVADO)
    assert mixer.net_factor(derivados) == compute_net_factor(
        [Fila(d) for d in derivados])


def test_la_venta_directa_no_es_gratis():
    """La razón de ser del mixer. FinPlan tenía DIRECT en 0% y el cuadro del
    owner dice 7–10%: si el derivado vuelve a dar cero, el error volvió."""
    derivado = {d.channel: d for d in mixer.derivar(CORCOVADO)}["DIRECT"]
    assert derivado.commission_pct > 0


# ── El mix tiene que cerrar ─────────────────────────────────────────────────

def test_un_mix_que_no_cierra_se_detecta():
    """Un mix que no suma 100% deja el Net Factor sobre una base que no es el
    total, y el error se propaga a todo el ingreso sin que nada falle."""
    assert mixer.mix_cierra(CORCOVADO)
    assert not mixer.mix_cierra(CORCOVADO[:-1])


def test_el_catalogo_del_repositorio_cierra():
    """El archivo que se siembra tiene que cumplir la misma regla."""
    from app.seed_canales_comerciales import leer
    assert abs(sum(Decimal(str(c["mix_pct"])) for c in leer()) - 1) < Decimal("0.0001")


# ── La cascada ──────────────────────────────────────────────────────────────

def test_sin_excepcion_manda_el_mix_base():
    """Es lo que hace que un escenario nuevo nazca bien: sin nada guardado,
    hereda el base en vez de una constante vieja."""
    resueltos = mixer.resolver(CORCOVADO, [])
    assert [r.mix_pct for r in resueltos] == [c.mix_pct for c in CORCOVADO]
    assert all(r.origen == "base" for r in resueltos)


def test_el_anual_del_escenario_pisa_el_base():
    overs = [Override("B2B", 0, _d("0.40"), _d("0.25"))]
    b2b = {r.code: r for r in mixer.resolver(CORCOVADO, overs)}["B2B"]
    assert (b2b.mix_pct, b2b.comision_pct, b2b.origen) == (_d("0.40"), _d("0.25"), "escenario")


def test_el_mes_pisa_al_anual():
    overs = [Override("B2B", 0, _d("0.40"), _d("0.25")),
             Override("B2B", 3, _d("0.70"), _d("0.32"))]
    marzo = {r.code: r for r in mixer.resolver(CORCOVADO, overs, 3)}["B2B"]
    abril = {r.code: r for r in mixer.resolver(CORCOVADO, overs, 4)}["B2B"]
    assert (marzo.mix_pct, marzo.origen) == (_d("0.70"), "mes")
    # Abril no tiene excepción propia: cae al anual, no al base.
    assert (abril.mix_pct, abril.origen) == (_d("0.40"), "escenario")


def test_pedir_el_anual_ignora_las_excepciones_de_mes():
    """`month=0` es «todo el año», no «enero»: una excepción de marzo no puede
    contaminar la vista anual."""
    overs = [Override("B2B", 3, _d("0.70"), _d("0.32"))]
    b2b = {r.code: r for r in mixer.resolver(CORCOVADO, overs, 0)}["B2B"]
    assert b2b.origen == "base"


# ── A quién manda el mixer ──────────────────────────────────────────────────

@pytest.mark.parametrize("esc", [
    Esc(2027, "BUDGET"), Esc(2027, "FORECAST"), Esc(2028, "BUDGET"),
])
def test_manda_sobre_lo_que_se_construye_desde_2027(esc):
    """Owner: «a partir de enero 2027, el forecast, el budget, todo lo que se
    construye ahí, como auxiliar, tiene que dar con esos parámetros»."""
    assert mixer.gobierna(esc)[0]


@pytest.mark.parametrize("esc,parte_del_motivo", [
    (Esc(2026, "BUDGET", "Final"), "2026"),
    (Esc(2027, "ACTUAL"), "ACTUAL"),
    (Esc(2027, "BUDGET", is_locked=True), "enllavado"),
])
def test_no_toca_lo_que_ya_es_lo_que_es(esc, parte_del_motivo):
    """Budget Final 2026 —«ya es lo que es»—, los ACTUAL —registran lo que pasó,
    no se planifican— y los enllavados —su foto es historia—."""
    # El motor devuelve la CLAVE del motivo y sus datos, no la frase: no se
    # entera del idioma. El texto vive en `app/textos.py` y lo resuelve quien
    # contesta. Se comprueba el criterio en LOS DOS idiomas — mirando solo el
    # español, el inglés podría perder la explicación sin que nadie se entere.
    from app.textos import t

    aplica, clave, params = mixer.gobierna(esc)
    assert not aplica
    assert clave, "un escenario excluido sin motivo no se puede discutir"
    assert parte_del_motivo in t("es", clave, **params)
    assert t("en", clave, **params) != clave, f"falta el inglés de {clave}"


def test_siempre_dice_por_que_no():
    """Un escenario excluido sin motivo no se puede discutir: la pantalla
    muestra la lista completa y el motivo es lo que la hace legible."""
    for esc in [Esc(2026, "BUDGET"), Esc(2027, "ACTUAL"),
                Esc(2027, "BUDGET", is_locked=True)]:
        assert mixer.gobierna(esc)[1].strip(), "sin clave de motivo"


# ── Lo que de verdad manda ──────────────────────────────────────────────────

def test_las_tarifas_le_ganan_al_mix():
    """El motor prefiere `net_rate / rack_rate` sobre el mix de canales.

    Se descubrio midiendo produccion: en TODOS los escenarios con datos manda la
    tarifa. O sea que aplicar el mixer escribe las filas y no mueve un numero
    mientras la tarifa neta no se regenere — un no-op silencioso, que es
    exactamente la clase de error que este sistema ya sufrio varias veces.

    Si alguien invierte esta precedencia, el mixer empieza a mover plata sola y
    esta prueba tiene que ser lo que avise.
    """
    from app.engine.revenue_calculator import _effective_net_factor

    class RC:
        def __init__(self, rack, net):
            self.rack_rate, self.net_rate = _d(rack), _d(net)

    # Con tarifas: el factor sale de ellas, sin mirar el mix.
    assert _effective_net_factor([RC("100", "82.2")]) == _d("0.822000")
    # Sin tarifas: recien ahi cae al mix.
    assert _effective_net_factor([]) is None
    assert _effective_net_factor([RC("0", "50")]) is None


def test_el_net_factor_de_canales_es_por_mes():
    """Las 36 filas (3 canales x 12 meses) NO pueden dar doce veces el factor.

    ⚠️ **Esta prueba afirmaba lo contrario, y la afirmacion era falsa.** Decia
    «el motor filtra por mes antes de sumar» — y el motor NO filtraba:
    `calculate_revenue` le pasaba los 36 canales enteros a `compute_net_factor`,
    que sumaba sin dividir y devolvia **9,5640** en el Budget Working 2027.

    Medido el 2026-08-20: ocho escenarios (presupuestos 2028 a 2035) caian en
    ese camino, porque tienen 36 canales y cero tarifas. Multiplicaban cero
    porque estan vacios, pero el camino se abre en cuanto alguien cargue
    tarifas netas dejando el rack en cero.

    Arreglado en el ORIGEN: `compute_net_factor` es ahora un promedio
    **ponderado** —divide por la suma de las mezclas— asi que da lo mismo se
    filtre o no. Una regla que depende de que cada lector se acuerde de filtrar
    no es una regla; esta lo es.
    """
    from app.models.sales_channel_config import compute_net_factor

    class Fila:
        def __init__(self, month, mix, com):
            self.month, self.mix_pct, self.commission_pct = month, _d(mix), _d(com)

    doce_meses = [Fila(m, "0.5", "0.2") for m in range(1, 13)] + \
                 [Fila(m, "0.5", "0.0") for m in range(1, 13)]
    de_un_mes = [f for f in doce_meses if f.month == 1]
    assert compute_net_factor(de_un_mes) == _d("0.9")
    # Los doce meses dan LO MISMO que uno. Antes daba 10.8, o sea 12x.
    assert compute_net_factor(doce_meses) == _d("0.9")
    assert compute_net_factor(doce_meses) <= _d("1"), "un factor neto no pasa de 1"


def test_el_seed_no_pisa_lo_que_el_owner_edita():
    """El owner dijo «lo arreglo ya en vivo». Si el seed reescribiera el mix en
    cada arranque, ese arreglo duraria hasta el proximo deploy y volveria solo al
    del archivo — sin que nada avise, que es la peor forma de perderlo.

    El seed solo rellena el mix cuando NADIE cargo ninguno.
    """
    import inspect
    from app import seed_canales_comerciales as seed

    fuente = inspect.getsource(seed.seed_canales)
    # La comision del owner nunca se toca en una fila que ya existe.
    assert "actuales[code].comision_pct" not in fuente
    # Y el mix solo se rellena bajo la guarda de que no haya ninguno cargado.
    assert "if sin_mix:" in fuente


# ── La base sobre la que se simula la plata ─────────────────────────────────

def test_la_base_comisionable_no_es_solo_habitaciones():
    """El factor NO toca solo habitaciones: el motor tambien lo aplica a la
    comida, la bebida, las actividades y el transporte del paquete
    (`pax x tarifa x nf`). Simular sobre habitaciones sola SUBESTIMA la comision
    y el impacto — y el numero sale creible igual, que es lo peligroso.
    """
    from app.api.mixer_api import LINEAS_COMISIONABLES, LINEAS_DE_HABITACIONES

    assert set(LINEAS_DE_HABITACIONES) < set(LINEAS_COMISIONABLES)
    for linea in ("REV_FB", "REV_TOURS", "REV_TRANSPORTATION"):
        assert linea in LINEAS_COMISIONABLES


def test_la_sostenibilidad_no_paga_comision():
    """Es una cuota fija por persona por noche: el motor la calcula SIN el
    factor. Meterla en la base infla la venta rack y con ella la comision
    simulada, sin que nada lo delate."""
    from app.api.mixer_api import LINEAS_COMISIONABLES

    assert "REV_SUSTAINABILITY" not in LINEAS_COMISIONABLES


def test_el_motor_sigue_aplicando_el_factor_donde_creemos():
    """Si alguien deja de multiplicar el paquete por el factor —o empieza a
    multiplicar la sostenibilidad—, la base de la simulacion queda mintiendo.
    Esto lee el motor para que ese cambio no pase callado."""
    import inspect
    from app.engine import revenue_calculator as rc

    fuente = inspect.getsource(rc.calculate_revenue)
    for linea in ("food_rev", "act_rev", "trans_rev"):
        assert f"{linea} = " in fuente and "* nf" in fuente.split(f"{linea} = ")[1][:120], \
            f"{linea} ya no se multiplica por el factor"
    # La sostenibilidad se calcula despues y sin `nf`.
    sust = fuente.split("sust_cfg")[-1]
    assert "* nf" not in sust.split("result.sustainability")[0]
