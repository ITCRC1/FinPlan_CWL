# -*- coding: utf-8 -*-
"""Costos para Negociación de Grupos — Fase 1.

El módulo calcula cuánto cuesta atender un grupo, en dólares por unidad de
servicio, para poder negociar sin destruir margen (`COSTOS_GRUPOS.md`).

Estas pruebas vigilan las tres decisiones que se tomaron al medir ANTES de
construir, y que no se ven leyendo el código después.
"""
import calendar
import io
import os
import re

from app.seed_costos_grupos import CERRADOS, MAPA, PARAMETROS

RAIZ = os.path.join(os.path.dirname(__file__), "..")


# ── La decisión de fondo ────────────────────────────────────────────────────

def test_no_se_crearon_tablas_de_hechos():
    """⚠️ La decisión que sostiene todo el módulo.

    El spec describe cuatro tablas `fact_*`. Ninguna se creó: el P&L mensual,
    el overhead y los no-operativos ya los produce el motor, y los volúmenes ya
    viven en `stat_accounts` / `statistical_entries` / `scenario_stats`.

    Copiarlos sería tener dos fuentes del mismo número — y la copia se queda
    vieja el día que alguien recalcula el escenario, **sin que nada falle**.
    """
    mig = io.open(os.path.join(RAIZ, "alembic", "versions",
                               "130_costos_grupos_config.py"),
                  encoding="utf-8").read()
    creadas = re.findall(r'op\.create_table\(\s*"(\w+)"', mig)
    assert creadas, "la migración no crea nada"
    for t in creadas:
        assert t.startswith("cfg_"), (
            f"la migración creó `{t}`: este módulo sólo puede crear "
            f"configuración. Los hechos se leen del motor")


def test_la_capa_de_lectura_no_copia_a_una_tabla():
    src = io.open(os.path.join(RAIZ, "app", "engine", "costos_grupos.py"),
                  encoding="utf-8").read()
    assert "compute_pl_month" in src, "dejó de leer del motor del P&L"
    assert "ScenarioStat" in src, "dejó de leer los volúmenes de habitaciones"
    assert "db.add(" not in src, (
        "la capa de lectura empezó a escribir: si guarda lo que lee, vuelve a "
        "haber dos fuentes del mismo número")


# ── El calendario ───────────────────────────────────────────────────────────

def test_el_mapa_cubre_los_doce_meses():
    assert sorted(MAPA) == list(range(1, 13))


def test_el_calendario_reproduce_las_cifras_del_spec():
    """334 días abiertos y, a 30 habitaciones, 10.020 habitaciones-noche.

    Es el número contra el que se valida la capacidad, y el que —dividiendo el
    overhead— da los $216 por habitación disponible del §7.
    """
    dias = {m: calendar.monthrange(2026, m)[1] for m in range(1, 13)}
    assert sum(dias.values()) == 365
    abiertos = sum(d for m, d in dias.items() if m not in CERRADOS)
    assert abiertos == 334, f"días abiertos = {abiertos}, el spec dice 334"
    assert abiertos * 30 == 10_020


def test_el_mes_cerrado_es_octubre():
    """El spec lo daba «por confirmar» (§8, hueco 8). Confirmado contra
    producción: en el Forecast Working 2026 y el Budget Final 2027 octubre
    tiene CERO habitaciones disponibles.

    ⚠️ Pero no está en todos los escenarios: el Budget Working 2027 y los
    Actuals lo tienen abierto, y suman 10.950 en vez de 10.020. Esa diferencia
    mueve el overhead por habitación de $216 a $198 — un 9% del piso.
    """
    assert CERRADOS == {10}


def test_las_temporadas_son_las_tres_del_spec():
    assert set(MAPA.values()) == {"ALTA", "MEDIA", "BAJA"}
    # ALTA arranca en diciembre: el ciclo comercial no es el año calendario.
    assert MAPA[12] == "ALTA"
    # Noviembre en MEDIA es una decisión COMERCIAL que el spec marca como
    # revisable, no un hecho contable. Si cambia, cambia acá y en ningún otro
    # lado — por eso el mapa es dato y no código.
    assert MAPA[11] == "MEDIA"
    assert MAPA[9] == "BAJA" and MAPA[10] == "BAJA"


# ── Los parámetros ──────────────────────────────────────────────────────────

def test_los_defaults_son_los_del_spec():
    assert PARAMETROS["management_fee_pct"] == "0.03"
    assert PARAMETROS["margen_protegido_pct"] == "0.15"
    assert PARAMETROS["metodo_absorcion"] == "M2"
    assert PARAMETROS["tratamiento_mes_cerrado"] == "B"
    assert PARAMETROS["incluir_capital_en_piso"] == "NO"


def test_el_credito_de_sustainability_arranca_APAGADO():
    """⚠️ El hueco 1 del spec, y el más caro si se olvida.

    El Sustainability Fee son $238.325 con CERO costo asignado. Si el aporte a
    conservación es su contrapartida, el fee **no es margen libre** y
    acreditarlo contra el piso sobrestima el margen del grupo en hasta $92 por
    habitación-noche.

    El ejemplo principal del spec (§4.3) muestra la columna «neto de SF» bien
    grande — el riesgo real es que se construya como la vista normal.
    """
    assert PARAMETROS["sustainability_libre"] == "NO"


def test_el_escenario_base_esta_fijado_y_es_el_que_el_owner_eligio():
    """Entre escenarios la capacidad va de 10.020 a 10.950 habitaciones-noche,
    así que «el escenario» no es un detalle: mueve el 9% del piso.

    Verificado que el Forecast Working 2026 reproduce las semillas del §7:
    3.600 disponibles, 2.587 ocupadas, 4.883 noches-huésped, 71,86%.
    """
    assert PARAMETROS["escenario_base"] == "FORECAST/2026/Working"


# ── La corrección a la validación 2 ─────────────────────────────────────────

def test_la_validacion_de_overhead_no_pide_lo_imposible():
    """El spec §6.2 pide «Σ overhead asignado por cualquier método = overhead
    total». Con el default M2 eso NO puede cumplirse: reparte entre
    habitaciones DISPONIBLES y el piso lo aplica a una VENDIDA, así que con
    71,86% de ocupación se asignaría el 71,86%.

    No es un error del modelo: la parte de las habitaciones vacías no la paga
    ningún grupo. Quien garantiza que el año cierre es la Golden Rate, que
    divide entre ocupadas. Lo que se controla es que los COMPONENTES sumen el
    total.
    """
    src = io.open(os.path.join(RAIZ, "app", "engine", "costos_grupos.py"),
                  encoding="utf-8").read()
    assert "componentes de overhead = overhead total" in src, (
        "la validación 2 volvió a comparar el overhead ASIGNADO contra el "
        "total: con M2 es aritméticamente imposible que pase")


def test_la_capacidad_no_asume_las_habitaciones():
    """Son 30 en CWL, pero el módulo se clona a Amarena, Oxígen y Ojochal. Un
    30 escrito en el código daría un cuadre falso en las tres."""
    src = io.open(os.path.join(RAIZ, "app", "engine", "costos_grupos.py"),
                  encoding="utf-8").read()
    assert 'await db.get(Hotel, hotel_id)' in src
    assert not re.search(r"def _habitaciones", src), (
        "volvió una constante de habitaciones en el motor")


# ── Fase 2 · las fórmulas salieron de PROBARLAS contra las semillas ─────────
#
# El §7 del spec existe para una cosa: validar que el motor reproduce los
# números conocidos antes de construir pisos encima. Se corrió contra el
# escenario base y cinco de siete dieron exactas. Las dos que no, enseñaron
# algo — y por eso quedan escritas acá y no borradas.

from app.engine.costos_grupos import absorcion
from app.seed_costos_grupos import COMPOSICION


def test_el_costo_propio_de_transporte_incluye_su_costo_de_venta():
    """La semilla dice $30,80 por habitación ocupada. Con `OPEX_TRANSPORTATION`
    sola da **$16,78**. Sumando `COS_TRANSPORTATION`:
    (43.416,93 + 36.253,07) / 2.587 = **$30,80**, exacta.

    Sin esto, el piso de transporte sale a la mitad — y como el número igual
    «se ve razonable», nadie lo nota.
    """
    assert "COS_TRANSPORTATION" in COMPOSICION[("TRANSPORTATION", "propio")]


def test_sustainability_va_SEPARADO_de_other_misc():
    """⚠️ Decisión del owner (2026-08-19), y contradice a la semilla del spec.

    **Cómo se descubrió:** la semilla dice $92,12 por habitación ocupada y
    $48,81 por noche-huésped, y el §8 habla de $238.325. Con
    `REV_SUSTAINABILITY` sola daba $54,38 y $28,81 — no cerraba. Sumándole
    `REV_MISC_OTHER` daba **238.325,28** → $92,12 y $48,81, las dos exactas.
    O sea que en el libro de origen eran **un mismo cubo**, y eso explicaba el
    departamento que faltaba en la lista del §3.2.

    **El owner decidió separarlos.** Con eso:
      * Sustainability baja de $92,12 a **$54,38** por habitación ocupada.
      * «Other / Misc» pasa a ser un departamento propio, con **$97.656** de
        contribución en cuatro meses.
      * La semilla del §7 **deja de reproducir, a propósito**: describía el
        libro de origen, no cómo el owner quiere leerlo de ahora en adelante.

    Esto cambia la Golden Rate, que resta la contribución de los demás
    departamentos: con dos departamentos en vez de uno, la resta es la misma en
    total pero deja de esconderse dentro del fee.
    """
    assert COMPOSICION[("SUSTAINABILITY", "ingreso")] == ["REV_SUSTAINABILITY"]
    assert COMPOSICION[("MISC_OTHER", "ingreso")] == ["REV_MISC_OTHER"]


def test_la_composicion_es_editable_y_no_vive_en_el_codigo():
    """El owner pidió que fuera editable, y tenía razón: la composición es
    donde uno se equivoca —Transporte salía a la mitad por una cuenta— y donde
    cada propiedad difiere. En la tabla, corregirla es una fila; en el código,
    un despliegue."""
    motor = io.open(os.path.join(RAIZ, "app", "engine", "costos_grupos.py"),
                    encoding="utf-8").read()
    assert "async def cargar_composicion" in motor
    assert "CfgComposicion" in motor, "el motor dejó de leer la composición"
    assert "COMPONENTES = {" not in motor, (
        "volvió una composición escrita en el motor: el owner pidió que fuera "
        "editable")


def test_el_costo_propio_de_fb_incluye_las_tres_cuentas_de_venta():
    """(170.056,48 + 129.073,94 + 44.271,53 + 3.476,84) / 4.883 = $71,04."""
    for c in ("OPEX_FB", "COS_FB_FOOD", "COS_FB_BEV", "COS_FB_MISC"):
        assert c in COMPOSICION[("FB", "propio")]


def test_M1_no_se_puede_usar_para_pisos():
    """⚠️ Es la regla que sostiene el módulo entero (§1).

    Repartir el overhead como % del revenue es circular: si se concede un
    descuento, baja el revenue y baja el overhead asignado en la misma
    proporción, así que **el piso se mueve junto con el precio y nunca se
    alcanza**. Por eso el método no está implementado: no alcanza con
    documentarlo, tiene que ser imposible de llamar por accidente.
    """
    import pytest
    with pytest.raises(ValueError, match="circular"):
        absorcion([], "M1")


# ── Fase 3 · los pisos, y la prueba que sostiene el modulo entero ───────────

from decimal import Decimal

from app.engine.costos_grupos import (
    MesDeCostos, Pisos, gross_up, pisos_habitacion,
)


def test_el_gross_up_despeja_en_vez_de_sumar():
    """⚠️ El error que parece trivial y cuesta plata.

    El fee y la comisión son porcentajes SOBRE EL PRECIO. Cobrar `costo + 25%`
    deja corto: sobre un precio de 100 con 25% de comisión quedan 75, no 80.

    El spec §4.3: 322,66 con fee 3% y comisión 25% da **448,14**, no 322,66 ×
    1,28 = 413,00. Son $35 por habitación-noche de diferencia, en contra.
    """
    v = gross_up(Decimal("322.66"), Decimal("0.03"), Decimal("0.25"))
    assert abs(v - Decimal("448.14")) < Decimal("0.01")
    # Y con el margen protegido del 15% (Piso 4 del spec): 566,07
    v4 = gross_up(Decimal("322.66"), Decimal("0.03"), Decimal("0.25"), Decimal("0.15"))
    assert abs(v4 - Decimal("566.07")) < Decimal("0.01")
    # Piso 2 del spec, sólo el costo propio: 147,86
    v2 = gross_up(Decimal("106.46"), Decimal("0.03"), Decimal("0.25"))
    assert abs(v2 - Decimal("147.86")) < Decimal("0.01")


def test_no_hay_precio_que_alcance_cuando_los_puntos_suman_uno():
    """Una división por casi-cero devuelve un número enorme que parece un
    precio. Mejor que avise."""
    import pytest
    with pytest.raises(ValueError, match="no hay precio"):
        gross_up(Decimal("100"), Decimal("0.03"), Decimal("0.90"), Decimal("0.15"))


def _mes(costo_rooms, oh, disp, ocup, revenue_rooms):
    return MesDeCostos(
        mes=1, temporada="ALTA", dias_abiertos=31,
        revenue_por_dept={"REV_ROOMS": Decimal(revenue_rooms)},
        costo_por_dept={"OPEX_ROOMS": Decimal(costo_rooms)},
        overhead_por_componente={"OH_ADMIN": Decimal(oh)},
        hab_disponibles=disp, hab_ocupadas=Decimal(ocup),
        noches_huesped=Decimal(ocup) * 2,
    )


COMP = {("ROOMS", "propio"): ["OPEX_ROOMS"], ("ROOMS", "venta"): [],
        ("SUSTAINABILITY", "ingreso"): ["REV_SUSTAINABILITY"]}
PAR = {"management_fee_pct": "0.03", "margen_protegido_pct": "0.15",
       "sustainability_libre": "NO"}


def test_VALIDACION_6_el_piso_no_se_mueve_al_conceder_un_descuento():
    """⚠️ **La prueba que sostiene el módulo entero** (spec §6.6 y §1).

    El modelo anterior asignaba overhead como % del revenue del departamento.
    Para leer un P&L está bien y concilia. **Para fijar un piso es circular:**
    si se concede un descuento, baja el revenue y baja el overhead asignado en
    la misma proporción, así que el piso baja junto con el precio **y nunca se
    alcanza**. Por eso el «descuento máximo 56,8%» de la política era un techo
    contable, no un piso operativo.

    Acá se concede un 20% de descuento —el revenue cae— y se verifica que los
    cuatro pisos dan EXACTAMENTE lo mismo. Si algún día se mueven, hay un
    porcentaje sobre revenue infiltrado en el cálculo.
    """
    base = [_mes(100_000, 200_000, 930, 600, 500_000)]
    # El mismo mes con 20% menos de ingreso. El costo y la capacidad no cambian:
    # conceder un descuento no hace que el hotel gaste menos ni tenga menos
    # habitaciones.
    con_descuento = [_mes(100_000, 200_000, 930, 600, 400_000)]

    a = pisos_habitacion(base, COMP, PAR, Decimal("0.25"))
    b = pisos_habitacion(con_descuento, COMP, PAR, Decimal("0.25"))

    for campo in ("marginal", "departamental", "integral", "con_margen"):
        assert getattr(a, campo) == getattr(b, campo), (
            f"el piso «{campo}» se movió al conceder un descuento: hay un "
            f"porcentaje sobre revenue infiltrado en el cálculo")


def test_los_cuatro_pisos_van_de_menor_a_mayor():
    """Si el marginal saliera por encima del integral, la matriz de
    autorización del §4.9 quedaría al revés y la zona roja autorizaría más que
    la verde."""
    p = pisos_habitacion([_mes(100_000, 200_000, 930, 600, 500_000)],
                         COMP, PAR, Decimal("0.25"))
    assert p.marginal <= p.departamental <= p.integral <= p.con_margen


def test_el_credito_de_sustainability_solo_aplica_si_esta_encendido():
    """Apagado por defecto (hueco 1 del spec): si el aporte a conservación es
    la contrapartida del fee, acreditarlo contra el piso sobrestima el margen
    del grupo en hasta $92 por habitación-noche."""
    mes = [_mes(100_000, 200_000, 930, 600, 500_000)]
    mes[0].revenue_por_dept["REV_SUSTAINABILITY"] = Decimal("60000")
    comp = dict(COMP)
    apagado = pisos_habitacion(mes, comp, PAR, Decimal("0.25"))
    encendido = pisos_habitacion(
        mes, comp, {**PAR, "sustainability_libre": "SI"}, Decimal("0.25"))
    assert apagado.credito_sustainability == Decimal("0")
    assert encendido.credito_sustainability > 0
    assert encendido.integral < apagado.integral


# ── Fase 4 · la Golden Rate ─────────────────────────────────────────────────

from app.engine.costos_grupos import golden_rate


def test_restar_un_departamento_que_PIERDE_sube_la_tarifa():
    """⚠️ El signo que engaña, y con Club Madresal no es un detalle.

    La Golden Rate resta la contribución de los demás departamentos. Un
    departamento que PIERDE plata tiene contribución negativa, así que restarla
    **sube** la tarifa. Es correcto —esa pérdida la tiene que cubrir alguien—
    pero es al revés de lo que uno espera al «sumar un departamento».

    En el Budget 2027 Working, Club Madresal pierde **$228.470**. Incluirlo
    sube la Golden Rate en vez de bajarla.
    """
    base = [_mes(100_000, 200_000, 930, 600, 500_000)]
    comp_sin = {("ROOMS", "propio"): ["OPEX_ROOMS"], ("ROOMS", "ingreso"): ["REV_ROOMS"]}
    comp_con = dict(comp_sin)
    comp_con[("CLUB", "ingreso")] = ["REV_CLUB"]
    comp_con[("CLUB", "propio")] = ["OPEX_CLUB"]
    # Club con ingreso 10.000 y costo 50.000: pierde 40.000.
    base[0].revenue_por_dept["REV_CLUB"] = Decimal("10000")
    base[0].costo_por_dept["OPEX_CLUB"] = Decimal("50000")

    sin_club = golden_rate(base, comp_sin, PAR, Decimal("0.25"))
    con_club = golden_rate(base, comp_con, PAR, Decimal("0.25"))
    assert con_club.tarifa > sin_club.tarifa, (
        "incluir un departamento que pierde tiene que SUBIR la Golden Rate: "
        "su pérdida la cubre alguien")
    assert con_club.detalle_contribucion["CLUB"] < 0


def test_la_golden_rate_es_menor_aislando_la_temporada_alta():
    """⚠️ Por qué el spec la declara ANUAL y no estacional.

    Aislada, la alta parece necesitar mucho menos: en esos meses el volumen es
    alto y los demás departamentos aportan de sobra. Esa base ignora el mes
    cerrado, la baja y la estructura que corre los doce meses. **Vender alta
    contra una Golden Rate estacional destruye el año.**

    Medido contra producción: año completo $645,39 · sólo alta $217,45.
    """
    alta = [_mes(50_000, 60_000, 930, 500, 400_000)]
    baja = [_mes(50_000, 140_000, 930, 100, 40_000)]
    solo_alta = golden_rate(alta, COMP, PAR, Decimal("0.25"))
    anual = golden_rate(alta + baja, COMP, PAR, Decimal("0.25"))
    assert solo_alta.tarifa < anual.tarifa


def test_la_golden_rate_desglosa_de_donde_sale():
    """Un número que Ventas tiene que defender no puede ser una caja negra."""
    g = golden_rate([_mes(100_000, 200_000, 930, 600, 500_000)],
                    COMP, PAR, Decimal("0.25"))
    assert g.requerido == (g.costo_propio_rooms + g.overhead + g.no_operativo
                           + g.capital - g.contribucion_ajena)


# ── Fase 4b · comisión máxima por capas ─────────────────────────────────────

from app.engine.costos_grupos import comision_maxima, erosion_combinada


def test_VALIDACION_7_con_factor_uno_la_capa1_es_el_margen_integral():
    """⚠️ El control que detecta el gross-up mal aplicado (spec §6.7).

    El revenue del P&L ya viene NETO de comisión de agencias. Calcular el techo
    contra ese revenue la descuenta **dos veces** y el techo sale
    artificialmente bajo — o sea, se rechaza negocio que sí convenía.

    Donde NO hay comisión embebida (tienda, spa, consumo en sitio: factor 1.0),
    los dos números tienen que coincidir exactamente. Sólo donde sí la hay se
    separan — y esa separación es el valor del cálculo.
    """
    mes = [_mes(100_000, 200_000, 930, 600, 500_000)]
    mes[0].revenue_por_dept["REV_FB"] = Decimal("200000")
    mes[0].costo_por_dept["OPEX_FB"] = Decimal("120000")
    comp = {("ROOMS", "propio"): ["OPEX_ROOMS"], ("ROOMS", "ingreso"): ["REV_ROOMS"],
            ("FB", "propio"): ["OPEX_FB"], ("FB", "ingreso"): ["REV_FB"]}

    capas = comision_maxima(mes, comp, PAR, {"ROOMS": Decimal("0.8220")})
    porc = {c.concepto: c for c in capas}
    # F&B se vende directo: factor 1.0 → los dos números coinciden.
    assert porc["FB"].factor_neto == Decimal("1")
    assert abs(porc["FB"].capa1 - porc["FB"].margen_integral) < Decimal("0.0001")
    # Habitaciones lleva comisión embebida → SE SEPARAN, y eso es correcto.
    assert porc["ROOMS"].capa1 > porc["ROOMS"].margen_integral


def test_el_overhead_no_se_carga_dos_veces_dentro_del_paquete():
    """⚠️ Tercera contradicción interna del spec, y voltea la conclusión.

    §4.2 dice que F&B, tours, spa y transporte entran con su costo **propio** y
    que **no se les carga overhead por separado**, «para no duplicar la
    absorción dentro de un mismo paquete». Pero §4.8 define `C = costo propio +
    overhead asignado` para todos.

    Se implementó §4.2 —el overhead va sólo a Habitaciones, que es la que
    reserva la capacidad— y por eso los techos de los demás departamentos dan
    mucho más altos que en la tabla del spec: F&B 34,2% contra 8,4%, Tours
    47,7% contra 23,5%. La conclusión del spec («F&B, Spa, Tienda, Tours y
    Transporte no aguantan una comisión de 25%») se invierte con esta regla.
    """
    mes = [_mes(100_000, 500_000, 930, 600, 500_000)]
    mes[0].revenue_por_dept["REV_FB"] = Decimal("200000")
    mes[0].costo_por_dept["OPEX_FB"] = Decimal("120000")
    comp = {("ROOMS", "propio"): ["OPEX_ROOMS"], ("ROOMS", "ingreso"): ["REV_ROOMS"],
            ("FB", "propio"): ["OPEX_FB"], ("FB", "ingreso"): ["REV_FB"]}
    capas = {c.concepto: c for c in comision_maxima(mes, comp, PAR, {})}
    # El costo de F&B es su costo propio y nada más.
    assert capas["FB"].costo == Decimal("120000")
    # El de Habitaciones sí carga el overhead completo.
    assert capas["ROOMS"].costo > Decimal("100000")


def test_descuento_y_comision_se_MULTIPLICAN():
    """Un 20% de descuento con 25% de comisión erosiona **40%, no 45%**.
    Sumarlos sobrestima el daño y hace rechazar negocio que convenía."""
    e = erosion_combinada(Decimal("0.20"), Decimal("0.25"))
    assert abs(e - Decimal("0.40")) < Decimal("0.0001")


# ─── Fase 7 · el rack y el descuento máximo ──────────────────────────────────

from app.engine.costos_grupos import (
    TarifaRack, descuentos, factor_neto_del_rack, pisos_habitacion,
)


def _rack(nombre, orden, rack, neto, pax="1.8"):
    return TarifaRack(room_type_id="rt-%d" % orden, nombre=nombre, orden=orden,
                      rack=Decimal(rack), neto=Decimal(neto), pax=Decimal(pax))


def test_el_descuento_maximo_sale_del_rack_no_del_neto():
    """`descuento_max = 1 - piso/rack`. Contra el NETO daria otro numero."""
    d = descuentos([_rack("Deluxe King", 1, "1000", "797")], Decimal("600"))[0]
    assert d.descuento_max == Decimal("0.4")          # 1 - 600/1000
    assert d.descuento_max != Decimal("1") - Decimal("600") / Decimal("797")


def test_un_rack_que_no_cubre_el_piso_se_marca_no_alcanza():
    """No es «descuento chico»: es vender bajo costo a tarifa plena.

    Medido en produccion: en temporada BAJA, Agujas y Sirena tienen rack
    $596,13 contra un Piso 4 de $1.012,56 - o sea -69,9%.
    """
    d = descuentos([_rack("Agujas Queen", 3, "596.13", "475.12")],
                   Decimal("1012.56"))[0]
    assert d.alcanza is False
    assert d.descuento_max < 0


def test_el_mismo_piso_da_holgura_muy_distinta_segun_la_categoria():
    """Por eso la tabla va por tipo y no un numero solo para el hotel.

    Un «40% a los grupos» parejo estaria bajo costo en la categoria estandar y
    dejaria plata sobre la mesa en la suite.
    """
    racks = [_rack("Agujas Queen", 3, "596.13", "475.12"),
             _rack("Residencia", 8, "1700", "1354.90")]
    ds = {d.nombre: d.descuento_max
          for d in descuentos(racks, Decimal("525.77"))}   # Piso 4, ALTA
    assert ds["Agujas Queen"] < Decimal("0.15")
    assert ds["Residencia"] > Decimal("0.65")
    politica = Decimal("0.40")
    assert politica > ds["Agujas Queen"]              # bajo costo
    assert politica < ds["Residencia"]                # plata sobre la mesa


def test_el_factor_neto_sale_del_tarifario_no_de_los_canales():
    """⚠️ `compute_net_factor(channels)` devuelve **9,5639** en produccion.

    Un factor mayor que 1 multiplicaria el ingreso por nueve. El motor lo
    esquiva porque prefiere el de las tarifas; aca se toma el mismo camino a
    proposito, no por casualidad.
    """
    fn = factor_neto_del_rack([_rack("Deluxe King", 1, "839.52", "669.10"),
                               _rack("Agujas Queen", 3, "596.13", "475.12")])
    assert fn is not None
    assert Decimal("0.79") < fn < Decimal("0.80")
    assert fn <= Decimal("1")


def test_sin_tarifario_el_factor_neto_es_None_y_no_cero():
    """El Forecast Working 2026 tiene CERO tarifas. `None` dice «no se»;
    un 0 diria «todo es comision» y el piso saldria infinito."""
    assert factor_neto_del_rack([]) is None
    assert factor_neto_del_rack([_rack("X", 1, "0", "0")]) is None


def test_una_tarifa_en_cero_no_entra_en_la_tabla_de_descuentos():
    """Dividir por un rack de 0 reventaria; saltarla es lo correcto."""
    ds = descuentos([_rack("Sin tarifa", 1, "0", "0"),
                     _rack("Con tarifa", 2, "800", "637.60")], Decimal("500"))
    assert [d.nombre for d in ds] == ["Con tarifa"]


def test_el_piso_marginal_nunca_queda_en_cero_sin_avisar():
    """⚠️ El defecto que esto atrapa: Habitaciones NO tiene costo de venta en
    USALI, asi que la suma daba CERO y el Piso 1 salia en $0,00 - «regalalo».
    Medido en produccion: $0,00 en las tres temporadas del Forecast 2026.

    Cae al costo propio completo, que es conservador, y queda MARCADO.
    """
    meses = [_mes("100000", "0", 930, "500", "300000")]
    comp = {("ROOMS", "propio"): ["OPEX_ROOMS"]}      # sin ("ROOMS","venta")
    p = pisos_habitacion(meses, comp, {"metodo_absorcion": "M2"},
                         Decimal("0.203"))
    assert p.marginal > 0
    assert p.marginal_estimado is True
    assert p.costo_variable == p.costo_propio


def test_con_clasificacion_real_el_piso_marginal_no_queda_marcado():
    """El contrapunto: si el variable existe, se usa y NO se marca."""
    meses = [_mes("100000", "0", 930, "500", "300000")]
    comp = {("ROOMS", "propio"): ["OPEX_ROOMS"],
            ("ROOMS", "venta"): ["OPEX_ROOMS"]}
    p = pisos_habitacion(meses, comp, {"metodo_absorcion": "M2"},
                         Decimal("0.203"))
    assert p.marginal_estimado is False
