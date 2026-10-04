# -*- coding: utf-8 -*-
"""El pax se carga por categoria y por mes, y escribe lo que el motor multiplica.

Owner, 2026-10-04, peleando con el «Pax min / Pax max» del Inventario: *«no
puedo guardar»* · *«evalua poner mejor un tab solo para pax que ya existe pero
que tome los datos por mes y por unidad, y despues haga la explosion por
habitacion»* · *«y que permita poner decimales»*.

## Los tres defectos que esto cierra

1. **El Inventario no dejaba guardar, y no era el backend.** Un PUT de prueba
   contra produccion contestaba 200. El campo era `type="number"` sobre una
   columna ENTERA y el owner escribe `2,1`: en configuracion regional española
   el navegador deja ese valor invalido, el borrador nunca queda distinto del
   guardado y no se manda nada. Se ve como si tomara el dato y volviera solo.
2. **`pax_min` y `pax_max` no alimentaban nada.** Estaban en el modelo, en la
   semilla y en dos endpoints de lectura. Ni el motor, ni un reporte, ni una
   linea de ingreso los leia.
3. **El tab de Pax decia que guardaba y no guardaba.** Leia el `pax_per_night`
   del escenario y su boton escribia el del HOTEL; nada copiaba ninguno de los
   dos a `rate_cards.pax_per_room`, que es lo que el motor multiplica. Se
   cambiaba 1,8 por 2,1, la grilla se recalculaba en pantalla, y el presupuesto
   no se movia. Medido en produccion: el Budget Working 2027 tenia 1,8 en las
   48 tarjetas y los de 2026, 2,0 — valores que nadie pudo escribir desde la
   aplicacion.

## La decision del owner (2026-10-04)

El `pax_per_night` del hotel queda como **semilla**: con eso nace una tarjeta
nueva, y de ahi en adelante manda la grilla.
"""
import pathlib
import re
import shutil
import subprocess

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
FRONT = RAIZ / "frontend"
API = RAIZ / "backend/app/api/revenue_api.py"
PAGINA = FRONT / "app/revenue/pax/page.tsx"
GRILLA = FRONT / "app/revenue/pax/GrillaPax.tsx"
INVENTARIO = FRONT / "app/revenue/inventory/page.tsx"
ARNES = pathlib.Path(__file__).parent / "js/pegar_grilla.js"
ARNES_DOM = pathlib.Path(__file__).parent / "js/pegado_en_la_grilla.js"


def _api() -> str:
    return API.read_text(encoding="utf-8")


def test_la_grilla_escribe_EL_CAMPO_QUE_EL_MOTOR_MULTIPLICA():
    """⚠️ `rate_cards.pax_per_room`, y no un campo nuevo.

    `revenue_calculator` hace `total_guests += rooms_occ * rc.pax_per_room`, y
    de los huespedes salen ademas Food, Activities, Transportation y
    Sustainability. Un campo nuevo al lado daria una pantalla que guarda y un
    presupuesto que no se entera — que es exactamente el defecto que esto
    cierra.
    """
    api = _api()
    assert '@router.put("/scenarios/{scenario_id}/revenue/pax-grid/")' in api
    cuerpo = api[api.index("async def set_pax_grid("):]
    assert "rc.pax_per_room = c.pax" in cuerpo
    motor = (RAIZ / "backend/app/engine/revenue_calculator.py").read_text(encoding="utf-8")
    assert "rooms_occ * rc.pax_per_room" in motor, (
        "el motor dejo de multiplicar por `pax_per_room`: la grilla quedo "
        "escribiendo un campo que ya no se usa")


def test_una_celda_SIN_TARIFA_no_se_inventa():
    """⚠️ Sin tarjeta de tarifa, esa categoria NO esta en el presupuesto de ese
    mes: el motor la saltea entera (`if rt_id not in rates_by_type: continue`).

    Crear una tarjeta para alojar un pax la metaria en el calculo con tarifa
    CERO: sumaria sus noches a `total_rooms_occ` sin sumar ingreso, y la
    ocupacion y el ADR del escenario se moverian sin que nadie lo pidiera.
    """
    api = _api()
    cuerpo = api[api.index("async def set_pax_grid("):]
    assert "sin_tarifa.append(" in cuerpo
    assert "db.add(" not in cuerpo, (
        "el guardado de la grilla volvio a crear tarjetas: una tarjeta con "
        "tarifa cero mueve la ocupacion y el ADR")
    motor = (RAIZ / "backend/app/engine/revenue_calculator.py").read_text(encoding="utf-8")
    assert "if rt_id not in rates_by_type:" in motor


def test_el_pax_del_hotel_es_SEMILLA_no_un_1_8_escrito_a_mano():
    """Decision del owner, 2026-10-04: con el pax de la propiedad nace una
    tarjeta nueva, y de ahi en adelante manda la grilla.

    ⚠️ Antes habia un `Decimal("1.8")` literal en los dos lugares donde se crea
    una tarjeta. Una propiedad que opera con 2,1 nacia en 1,8 y nadie lo notaba,
    porque el numero no se veia en ninguna pantalla.
    """
    api = _api()
    assert "def _pax_semilla(" in api
    assert "async def _semilla_del_escenario(" in api
    assert "pax_per_room=semilla_pax," in api, (
        "el guardado masivo de rack rates volvio a crear tarjetas con un pax "
        "escrito a mano")
    # Y no quedo ningun 1.8 literal creando tarjetas.
    for m in re.finditer(r'pax_per_room\s*=\s*Decimal\("1\.8"\)', api):
        raise AssertionError(f"volvio el 1.8 literal en revenue_api: {m.group(0)}")


def test_guardar_una_TARIFA_no_pisa_el_pax():
    """⚠️ El PUT de la tarjeta suelta tenia `pax_per_room: Decimal = 1.8` como
    default.

    Cualquier pantalla que guardara una tarifa sin mandar el pax —y ninguna lo
    manda— devolvia el pax al default. Se cargaba la grilla, se tocaba una
    tarifa, y el pax se perdia sin que nada avisara.
    """
    api = _api()
    assert "pax_per_room: Decimal | None = None" in api
    cuerpo = api[api.index("async def update_rate_card("):]
    assert "if payload.pax_per_room is not None:" in cuerpo


def test_la_pantalla_acepta_DECIMALES_con_coma():
    """⚠️ `type="text"`, no `type="number"`.

    El owner escribe `2,1`. En un input numerico con configuracion regional
    española el navegador deja ese valor INVALIDO y devuelve cadena vacia: el
    campo nunca cambia y no se guarda nada. Es el defecto por el que el pax no
    se podia cargar en el Inventario, y repetirlo acá lo traeria de vuelta.
    """
    g = GRILLA.read_text(encoding="utf-8")
    assert 'type="text"' in g and 'inputMode="decimal"' in g
    # La coma se interpreta en el parser COMPARTIDO, que es el mismo del pegado.
    pegar = (FRONT / "lib/pegarGrilla.ts").read_text(encoding="utf-8")
    assert "export function numeroDeExcel(" in pegar
    assert 's.replace(",", ".")' in pegar, "la coma dejo de convertirse"
    # ⚠️ Se mira el JSX, no el comentario que explica por que no se usa.
    jsx = g[g.index("export default function GrillaPax("):]
    assert 'type="number"' not in jsx


def test_la_explosion_multiplica_POR_CELDA():
    """Owner, 2026-10-04: *«que tome los datos por mes y por unidad, y despues
    haga la explosion por habitacion»*.

    Una categoria de dos camas y una king no llevan la misma gente, y en
    temporada alta tampoco la misma que en septiembre. El factor unico no podia
    decir eso.
    """
    p = PAGINA.read_text(encoding="utf-8")
    assert "paxCelda[`${r.id}:${mi + 1}`]" in p
    assert "setPaxPerNight" not in p, (
        "la pantalla volvio a guardar el factor unico del hotel, que no llega "
        "a las tarjetas y por lo tanto no mueve el presupuesto")
    assert "<GrillaPax" in p


def test_el_INVENTARIO_ya_no_pide_un_pax_que_no_alimenta_nada():
    """`pax_min` y `pax_max` estaban en la pantalla, eran enteros y no los leia
    nadie. El owner peleo con ellos media hora.

    ⚠️ Y la pantalla DICE a donde se fue el dato. Sacar un campo sin dejar la
    puerta es cambiar «no puedo guardar» por «no lo encuentro».
    """
    bruto = INVENTARIO.read_text(encoding="utf-8")
    # ⚠️ Sin los comentarios: el que explica por que el pax ya no esta ACA
    # nombra las dos columnas, y tiene que poder hacerlo.
    inv = re.sub(r"\{?/\*[\s\S]*?\*/\}?", "", bruto)   # bloques /* … */
    inv = re.sub(r"//.*", "", inv)                         # y los de //
    for muerto in ("Pax min", "Pax max", "pax_min", "pax_max"):
        assert muerto not in inv, f"el inventario sigue pidiendo {muerto}"
    assert "/revenue/pax" in bruto, "no quedo el enlace a donde se carga ahora"


def test_la_grilla_se_pega_desde_EXCEL():
    """Owner, 2026-10-04: *«modifica para que yo pueda hacer un copy paste desde
    excel, rate y todo queda en la primera celda»* · *«es pax»*.

    Sin `onPaste`, los doce meses entran como un texto largo DENTRO de la
    primera celda y hay que teclearlos de nuevo uno por uno.

    ⚠️ Y el pegado usa EL MISMO parser que el tecleo. Con uno para cada camino,
    el mismo `2,1` puede entrar como 2,1 por un lado y como 21 por el otro — y
    la celda se ve igual en los dos casos.
    """
    g = GRILLA.read_text(encoding="utf-8")
    assert "onPaste={e => manejarPegado(" in g
    assert "repartirPegado(" in g
    assert "export const aNumero = numeroDeExcel;" in g, (
        "el tecleo volvio a tener su propio parser, distinto del del pegado")


def test_el_pegado_SALTEA_las_celdas_sin_tarifa():
    """⚠️ No las pisa ni corre el bloque.

    Esa categoria no esta en el presupuesto de ese mes: escribirle un pax no
    serviria —el guardado lo rechaza— y mover el valor a la celda de al lado
    para «no perderlo» correria todo el bloque un mes, que es peor que perderlo.
    Se saltea y se dice cuantas quedaron fuera.
    """
    g = GRILLA.read_text(encoding="utf-8")
    cuerpo = g[g.index("function pegar("):g.index("async function guardar(")]
    assert "if (!conTarifa.has(k)) { saltadas += 1; return; }" in cuerpo
    assert "se saltearon" in cuerpo


@pytest.mark.skipif(shutil.which("node") is None, reason="no hay node")
def test_cada_numero_de_excel_entra_como_EL_QUE_ES():
    """⚠️ Lo unico que no se puede comprobar leyendo el codigo.

    `2,1` tiene que entrar como 2,1 y `1,234` como 1234: la misma coma, dos
    significados, y entre los dos hay un factor de diez en el pax — que
    multiplica los huespedes y cuatro lineas de ingreso. Un error aca no rompe
    nada: escribe un presupuesto equivocado que se ve perfectamente bien.

    Se midio que FALLA: borrando todas las comas —que es lo que hace hoy el
    `num()` de la pantalla de rack rates— se caen 5 de las 31 comprobaciones,
    entre ellas `2,1 → 21`.
    """
    if not (FRONT / "node_modules/typescript").exists():
        pytest.skip("falta node_modules del frontend")
    r = subprocess.run(["node", str(ARNES)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 fallos" in r.stdout, r.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="no hay node")
def test_el_pegado_esta_ENGANCHADO_de_verdad():
    """⚠️ Que el parser este bien no dice que el pegado funcione.

    Owner, 2026-10-04, despues de la primera correccion: *«trate de hacer copy
    paste en pax y sigue igual»*. Era el bundle viejo todavia servido — pero no
    habia forma de SABERLO leyendo el codigo, y el camino para averiguarlo fue
    montar el componente en un DOM y dispararle un paste.

    Este arnes comprueba lo que ningun grep alcanza: que el `onPaste` este en el
    input, que React lo reciba, que cada valor caiga en SU celda —no en la
    primera, que es el defecto—, que la celda sin tarifa se saltee sin correr el
    bloque, y que `2,1` llegue al guardado como 2.1 y no como 21.

    Necesita `jsdom`, que no esta en el repo: sin el se saltea. Es diagnostico,
    no barrera.
    """
    if not (FRONT / "node_modules/react-dom").exists():
        pytest.skip("falta node_modules del frontend")
    r = subprocess.run(["node", str(ARNES_DOM)], capture_output=True, text=True)
    if r.returncode == 77:
        pytest.skip("falta jsdom: `npm i jsdom` en algun lado del NODE_PATH")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 fallos" in r.stdout, r.stdout
