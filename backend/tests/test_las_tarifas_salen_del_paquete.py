# -*- coding: utf-8 -*-
"""Los recuadros del Revenue Checkbook salen del paquete del escenario.

Owner, 2026-10-22: *«llena esto en forma automática de la vista anterior al
precio neto»*.

## El desfase que esto cierra

Los nueve recuadros cargaban de `seed_data/<HOTEL>/driver_rates.json`, un
archivo **fijo por hotel**. Las inclusiones del paquete viven por **escenario**.
Medido en el `BUDGET Working 2027`: la semilla decía Tours 342 y la pantalla
mostraba **0**, porque alguien lo había editado a mano y la semilla no tiene
dónde guardar eso. Dos fuentes para el mismo precio, y la que mandaba no sabe
de escenarios.

## Lo que NO cambia

El P&L. Con `revenue_source = 'drivers'` el motor calcula con `package_configs`
(108/101/35/28), no con estos recuadros. Esto alinea la calculadora de la
pantalla; llevar las tarifas del paquete al estado de resultados es otra
decisión.
"""
from decimal import Decimal

import pytest

from app.engine.tarifas_del_paquete import (CAJAS, SIN_COMISION,
                                            tarifas_del_paquete)

#: El Classic tal como está en producción en el BUDGET Working 2027.
CLASSIC = {
    "name": "Classic Experience Package", "nights": 3, "days": 4,
    "es_base": True,
    "items": [
        {"inclusion": "Lodging", "unit": "per room/night",
         "unit_price": None, "enabled": True},
        {"inclusion": "Full Pension (Meals)", "unit": "per pax/night",
         "unit_price": "126", "enabled": True},
        {"inclusion": "Sustainability Fee", "unit": "per pax/night",
         "unit_price": "30.97", "enabled": True},
        {"inclusion": "Transport Sierpe/Drake <-> CWL", "unit": "per pax/stay",
         "unit_price": "150", "enabled": True},
        {"inclusion": "Natural juices / coffee / tea", "unit": "per pax/day",
         "unit_price": "0", "enabled": False},
        {"inclusion": "Tour San Pedrillo", "unit": "per pax/stay",
         "unit_price": "168", "enabled": True},
        {"inclusion": "Tour a Cano", "unit": "per pax/stay",
         "unit_price": "174", "enabled": True},
    ],
}
NF = Decimal("0.797")


def test_saca_las_tarifas_que_el_owner_ve_en_pantalla():
    """Los cuatro recuadros, con los números de producción."""
    r = tarifas_del_paquete([CLASSIC], NF)
    assert r["disponible"]
    assert r["tarifas"]["food"] == 126
    assert r["tarifas"]["transport"] == 150
    assert r["tarifas"]["sust_rate"] == pytest.approx(30.97)
    assert r["tarifas"]["nights_per_stay"] == 3


def test_los_dos_tours_se_SUMAN():
    """El recuadro pide el total por estadía: San Pedrillo 168 + Caño 174.

    Es el origen del 342 que la semilla tenía escrito. Si en vez de sumar se
    quedara con el último, el checkbook llenaría Tours con 174 y perdería
    $348.000 en el año sin que nada avisara.
    """
    r = tarifas_del_paquete([CLASSIC], NF)
    assert r["tarifas"]["tours"] == 342
    cajas = {d["caja"]: d for d in r["detalle"]}
    assert cajas["tours"]["inclusiones"] == ["Tour San Pedrillo", "Tour a Cano"]


def test_el_sustainability_NO_lleva_comision():
    """⚠️ Owner, 2026-10-22: *«no paga comisión, se cobra en el hotel»*.

    Lo paga el huésped en recepción, así que la agencia no toca esa plata. Su
    neto es su rack. Coincide con el motor, que ya lo tiene
    `is_commissionable=False`.

    La pantalla de Package Components SÍ se lo descontaba —mostraba $24,68 en
    vez de $30,97— y por eso su total neto salía $6,29 por pax-noche bajo.
    """
    r = tarifas_del_paquete([CLASSIC], NF)
    assert r["neto"]["sust_rate"] == pytest.approx(30.97), (
        "el sustainability no comisiona: su neto es su rack")
    assert "sust_rate" in SIN_COMISION


def test_lo_que_SI_comisiona_se_descuenta():
    """El contrapeso: esto no es «quitarle el factor a todo».

    Sin esta prueba el arreglo anterior se puede «lograr» dejando de aplicar el
    factor neto en todas las líneas, y el ingreso del paquete subiría un 20 %
    de golpe.
    """
    r = tarifas_del_paquete([CLASSIC], NF)
    assert r["neto"]["food"] == pytest.approx(100.42, abs=0.01)
    assert r["neto"]["transport"] == pytest.approx(119.55, abs=0.01)
    assert r["neto"]["tours"] == pytest.approx(272.57, abs=0.01)


def test_la_inclusion_apagada_y_la_sin_precio_no_entran():
    """Los jugos están en 0 y apagados; el Lodging entra por el rack de
    habitaciones. Si alguno colara, se contaría dos veces."""
    r = tarifas_del_paquete([CLASSIC], NF)
    todas = [i for d in r["detalle"] for i in d["inclusiones"]]
    assert "Lodging" not in todas
    assert not any("juice" in x.lower() for x in todas)
    assert "Lodging" not in r["sin_casa"], (
        "sin precio no es lo mismo que sin casa: el Lodging no es una alerta")


def test_una_inclusion_RENOMBRADA_no_vale_cero():
    """⚠️ La defensa de fondo, y la razón de que exista `sin_casa`.

    Las inclusiones se reconocen por su texto. El `es_base` del modelo nació
    por esto mismo un nivel más arriba: *«antes se buscaba la que tuviera
    "classic" EN EL NOMBRE: renombrarla hacía que ese tab pasara a mostrar otra
    sin avisar»*.

    Si un renombre dejara la caja en cero y nada lo dijera, el checkbook se
    llenaría con menos ingreso y el total seguiría viéndose razonable.
    """
    raro = {**CLASSIC, "items": [
        *[i for i in CLASSIC["items"] if "Tour" not in i["inclusion"]],
        {"inclusion": "Caminata guiada San Pedrillo", "unit": "per pax/stay",
         "unit_price": "168", "enabled": True},
    ]}
    r = tarifas_del_paquete([raro], NF)
    assert "tours" not in r["tarifas"], "no debería inventar una tarifa"
    assert "Caminata guiada San Pedrillo" in r["sin_casa"], (
        "una inclusión con precio que no encuentra caja TIENE que salir "
        "reportada, no desaparecer en silencio")


def test_una_unidad_cambiada_se_AVISA():
    """El transporte por noche en vez de por estadía da 3× el monto.

    Nada en la plata lo delataría: el número sale grande pero plausible.
    """
    raro = {**CLASSIC, "items": [
        {**i, "unit": "per pax/night"} if "Transport" in i["inclusion"] else i
        for i in CLASSIC["items"]]}
    r = tarifas_del_paquete([raro], NF)
    avisos = {a["caja"] for a in r["unidad_rara"]}
    assert "transport" in avisos


def test_manda_la_experiencia_marcada_es_base():
    """Hay tres experiencias (Classic 3N/4D, VIP 4N/5D, Grupo NH). Sólo la
    marcada alimenta los recuadros, y el VIP tiene OTRA cantidad de noches: si
    se colara, la conversión estadía→noche saldría mal."""
    vip = {"name": "VIP Experience Package", "nights": 4, "days": 5,
           "es_base": False, "items": [
               {"inclusion": "Full Pension (Meals)", "unit": "per pax/night",
                "unit_price": "999", "enabled": True}]}
    r = tarifas_del_paquete([vip, CLASSIC], NF)
    assert r["experiencia"] == "Classic Experience Package"
    assert r["tarifas"]["food"] == 126
    assert r["tarifas"]["nights_per_stay"] == 3


def test_sin_paquete_dice_que_NO_hay_en_vez_de_devolver_ceros():
    """Llenar doce meses con ceros se ve igual que llenarlos bien.

    Es el mismo criterio que ya tenía la pantalla con la semilla: sin tarifas,
    el botón se apaga.
    """
    assert tarifas_del_paquete([], NF)["disponible"] is False
    vacia = {"name": "X", "nights": 3, "days": 4, "es_base": True, "items": []}
    assert tarifas_del_paquete([vacia], NF)["disponible"] is False


def test_el_acento_no_rompe_el_reconocimiento():
    """La pantalla está en dos idiomas y las inclusiones se escriben a mano."""
    es = {"name": "Paquete", "nights": 3, "days": 4, "es_base": True, "items": [
        {"inclusion": "Alimentación completa", "unit": "per pax/night",
         "unit_price": "126", "enabled": True},
        {"inclusion": "Tarifa de Sostenibilidad", "unit": "per pax/night",
         "unit_price": "30.97", "enabled": True},
    ]}
    r = tarifas_del_paquete([es], NF)
    assert r["tarifas"]["food"] == 126
    assert r["tarifas"]["sust_rate"] == pytest.approx(30.97)
    assert r["sin_casa"] == []


def test_toda_caja_declara_si_comisiona():
    """Una caja nueva tiene que decidir esto explícitamente.

    Si alguien agrega una fila a `CAJAS` con una tupla de tres, el módulo
    reventaría al desempacar; esta prueba lo dice antes y con nombre.
    """
    for fila in CAJAS:
        assert len(fila) == 4, f"{fila[0]} no declara si comisiona"
        assert isinstance(fila[3], bool)


# ═══════════════════════════════════════════════════════════════════════════
# Lo que el MOTOR consume. Owner, 2026-10-22: *«asegúrate que el checkbook
# calcule en función de estos rates»*.
#
# `package_configs` guarda todo por pax-noche; el paquete tiene inclusiones por
# estadía. Si la conversión se equivoca, el ingreso sale 3 veces arriba o abajo
# y el total sigue viéndose plausible.
# ═══════════════════════════════════════════════════════════════════════════
from app.engine.tarifas_del_paquete import (SUST_NO_PAGA_DEFECTO,  # noqa: E402
                                            a_tarifas_del_motor,
                                            cobrado_de_sustainability)


def test_lo_que_es_por_ESTADIA_se_divide_entre_las_noches():
    """342 por estadía de 3 noches son 114 por pax-noche, no 342."""
    m = a_tarifas_del_motor(tarifas_del_paquete([CLASSIC], NF), 10)
    assert m["ACTIVITIES"] == Decimal("114.0000")
    assert m["TRANSPORT"] == Decimal("50.0000")


def test_lo_que_YA_es_por_noche_no_se_divide():
    """El contrapeso: dividir el Food entre 3 lo dejaría en 42."""
    m = a_tarifas_del_motor(tarifas_del_paquete([CLASSIC], NF), 10)
    assert m["FOOD"] == Decimal("126")


def test_el_90_por_ciento_entra_en_la_tarifa_del_sustainability():
    """Owner: *«se calcula al 90 % ya que algunas personas no pagan»*.

    El motor no tiene dónde guardar un supuesto de cobro —su fórmula es
    `pax-noche × tarifa`— así que el 90 % se mete en el número. Lo que guarda
    es lo que se RECAUDA, no lo que se cobra.
    """
    m = a_tarifas_del_motor(tarifas_del_paquete([CLASSIC], NF), 10)
    assert m["SUSTAINABILITY"] == Decimal("27.8730")   # 30,97 × 0,90


def test_el_porcentaje_va_en_PORCENTAJE():
    """El recuadro de la pantalla y la semilla lo guardan como 10, no como 0,10."""
    assert cobrado_de_sustainability(10) == Decimal("0.90")
    assert cobrado_de_sustainability(0) == Decimal("1")
    assert cobrado_de_sustainability(Decimal("1.5")) == Decimal("0.985")
    assert cobrado_de_sustainability(None) == (
        Decimal("1") - SUST_NO_PAGA_DEFECTO / Decimal("100"))


def test_una_FRACCION_se_rechaza_en_vez_de_adivinarse():
    """⚠️ El borde que esta prueba existe para no cruzar.

    Con la regla «si es menor que 1 es fracción», `0.5` sería 50 % y `1.5` sería
    1,5 %: dos vecinos a cien veces de distancia, y los dos resultados se ven
    plausibles. Entre 0 y 1 no se puede saber, así que se dice en vez de
    suponer.
    """
    with pytest.raises(ValueError, match="ambiguo"):
        cobrado_de_sustainability(Decimal("0.10"))


def test_un_porcentaje_imposible_revienta_en_vez_de_pasar():
    """Un 150 % de no-pago daría una tarifa NEGATIVA y el ingreso restaría."""
    for malo in (150, -5):
        with pytest.raises(ValueError):
            cobrado_de_sustainability(malo)


def test_una_linea_SIN_tarifa_no_se_escribe():
    """⚠️ Lo que el sincronizador NO debe hacer.

    Si una inclusión se renombra y cae en `sin_casa`, su caja queda vacía.
    Escribir cero en `package_configs` le borraría esa línea al presupuesto y
    el total seguiría viéndose razonable.
    """
    sin_tours = {**CLASSIC, "items": [i for i in CLASSIC["items"]
                                      if "Tour" not in i["inclusion"]]}
    m = a_tarifas_del_motor(tarifas_del_paquete([sin_tours], NF), 10)
    assert "ACTIVITIES" not in m, "sin tarifa es NO TOCAR, no poner cero"
    assert m["FOOD"] == Decimal("126"), "las demás sí se escriben"


def test_las_noches_de_la_experiencia_mandan_la_conversion():
    """El VIP es 4N/5D: los mismos 342 por estadía son 85,50 por noche."""
    vip = {**CLASSIC, "name": "VIP", "nights": 4, "days": 5}
    m = a_tarifas_del_motor(tarifas_del_paquete([vip], NF), 10)
    assert m["ACTIVITIES"] == Decimal("85.5000")


# ═══════════════════════════════════════════════════════════════════════════
# El sincronizador corre en el RECÁLCULO, no solo al guardar el paquete.
#
# Owner, 2026-10-22, mirando la pantalla de Package Components: *«no hay dónde
# guardar acá»*. Y tenía razón: el guardado es automático y el botón queda
# apagado cuando nada cambió. Puesto solo en el guardado, un escenario cuyo
# paquete YA estaba escrito —los seis presupuestos 2027— no tenía forma de
# llegar al motor sin hacerle una edición falsa.
# ═══════════════════════════════════════════════════════════════════════════
import inspect  # noqa: E402

from app.engine import recalculate as _rec  # noqa: E402
from app.engine.tarifas_del_paquete import (  # noqa: E402
    sincronizar_tarifas_del_motor)


def test_el_RECALCULO_baja_las_tarifas_al_motor():
    """Sin esto, el paquete y el motor solo coinciden si alguien edita algo."""
    fuente = inspect.getsource(_rec.recalculate_scenario)
    assert "sincronizar_tarifas_del_motor" in fuente, (
        "el recálculo tiene que bajar las tarifas del paquete al motor; "
        "dejarlo solo en el guardado deja fuera a todo escenario ya escrito")


def test_baja_las_tarifas_ANTES_de_calcular_el_ingreso():
    """El orden es la mitad del arreglo.

    `calculate_revenue` lee `package_configs`. Si la sincronización corriera
    después, el recálculo calcularía con las tarifas VIEJAS y escribiría las
    nuevas: la pantalla mostraría las nuevas y el P&L el número de las
    anteriores, y haría falta recalcular dos veces para que cuadraran — sin que
    nada dijera por qué.
    """
    fuente = inspect.getsource(_rec.recalculate_scenario)
    assert (fuente.index("sincronizar_tarifas_del_motor")
            < fuente.index("load_revenue_results")), (
        "la sincronización va ANTES de leer el ingreso")


def test_el_aviso_dice_el_ANTES_y_el_DESPUES():
    """Una tarifa que se mueve sola y en silencio es el modo de falla más caro
    que tiene el sistema: el total sigue cuadrando y la plata cambia de línea."""
    texto = _rec._describir_tarifa(
        {"componente": "ACTIVITIES", "antes": 101.0, "despues": 114.0})
    assert "101" in texto and "114" in texto and "ACTIVITIES" in texto
    nueva = _rec._describir_tarifa(
        {"componente": "FOOD", "antes": None, "despues": 126.0})
    assert "—" in nueva and "126" in nueva


def test_un_escenario_SIN_paquete_no_escribe_nada():
    """⚠️ El endpoint sugiere una plantilla para que la pantalla no salga en
    blanco. Si el sincronizador cayera a esa misma semilla, una SUGERENCIA se
    escribiría sola en el motor de un escenario que nunca la pidió."""
    fuente = inspect.getsource(sincronizar_tarifas_del_motor)
    assert "experiencias_del_escenario" in fuente, (
        "tiene que leer la BD, no el endpoint que cae a la semilla")
    assert 'if not derivado.get("disponible"):' in fuente
