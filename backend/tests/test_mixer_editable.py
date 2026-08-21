# -*- coding: utf-8 -*-
"""EL MIXER SE PUEDE EDITAR, Y LO NUEVO RUEDA DONDE CORRESPONDE.

Owner, 2026-08-17: *«tenés que dejarme crear más mix y borrar también, y que el
derivado lo tome… inclusive se pueden crear más canales y sub-canales, pero
deben estar sincronizados para que ruede donde corresponde»*.

**El defecto que esto cierra.** El destino de un sub-canal no era un dato: se
deducía de `entrada` con un diccionario de seis entradas y **`DIRECT` de
default**. Un sub-canal nuevo cuya `entrada` no estuviera en la lista rodaba a
DIRECT en silencio — 9,27% de comisión en vez del 30% de TA, o sea **ingreso de
MÁS**. No fallaba: facturaba mal.
"""
from dataclasses import dataclass
from decimal import Decimal

from app.engine import mixer_canales as mx

D = Decimal


@dataclass
class Canal:
    code: str
    mix_pct: Decimal
    comision_pct: Decimal
    entrada: str = ""
    rueda_a: str = ""


def test_el_destino_sale_del_DATO_no_de_la_entrada():
    """Un sub-canal con `entrada` desconocida pero `rueda_a` puesto va a donde
    dice. Antes iba a DIRECT porque la entrada no estaba en el diccionario."""
    c = Canal("NUEVO", D("0.10"), D("0.25"), entrada="Metabuscador", rueda_a="TA")
    assert mx.destino_de(c) == "TA"


def test_sin_rueda_a_todavia_cae_al_diccionario():
    """El respaldo existe solo para objetos viejos en memoria; la columna es NOT
    NULL. Que siga funcionando evita que un test o un script viejo explote."""
    assert mx.destino_de(Canal("X", D("0.1"), D("0"), entrada="Travel Agent")) == "TA"
    assert mx.destino_de(Canal("Y", D("0.1"), D("0"))) == "DIRECT"


def test_un_canal_NUEVO_aparece_en_el_derivado():
    """El pedido textual: «que el derivado lo tome».

    ⚠️ Antes `derivar()` iteraba una constante de tres, así que lo que rodara a
    un canal nuevo **desaparecía del derivado**: la suma del mix bajaba de 100%
    y el Net Factor salía sobre una base que no era el total. Sin fallar.
    """
    canales = [
        Canal("B2B", D("0.50"), D("0.30"), rueda_a="TA"),
        Canal("WHOLESALE", D("0.50"), D("0.40"), rueda_a="MAYORISTA"),
    ]
    d = mx.derivar(canales, ["TA", "OTA", "DIRECT", "MAYORISTA"])
    codes = [x.channel for x in d]
    assert "MAYORISTA" in codes
    may = next(x for x in d if x.channel == "MAYORISTA")
    assert may.mix_pct == D("0.50") and may.commission_pct == D("0.40")
    # Y el mix derivado sigue sumando el total, que es lo que hace confiable al
    # Net Factor.
    assert sum((x.mix_pct for x in d), D("0")) == D("1.00")


def test_un_destino_fuera_de_la_lista_NO_se_pierde():
    """Aunque nadie haya dado de alta el canal, su mix tiene que verse — si se
    descartara, la suma bajaría de 100% sin que nada avisara."""
    canales = [Canal("A", D("0.7"), D("0.1"), rueda_a="TA"),
               Canal("B", D("0.3"), D("0.2"), rueda_a="INVENTADO")]
    d = mx.derivar(canales, ["TA", "OTA", "DIRECT"])
    assert "INVENTADO" in [x.channel for x in d]
    assert sum((x.mix_pct for x in d), D("0")) == D("1.0")


def test_el_net_factor_toma_los_canales_nuevos():
    """La comprobación de punta a punta: el factor que multiplica el ingreso."""
    canales = [Canal("A", D("0.5"), D("0.30"), rueda_a="TA"),
               Canal("B", D("0.5"), D("0.10"), rueda_a="MAYORISTA")]
    nf = mx.net_factor(mx.derivar(canales, ["TA", "MAYORISTA"]))
    # 0,5×0,70 + 0,5×0,90 = 0,80
    assert nf == D("0.80")


def test_la_semilla_obliga_a_declarar_el_destino():
    """El agujero por la puerta del seed: un canal nuevo en el JSON sin
    `rueda_a` entraría con el default del modelo y facturaría de más."""
    import json
    from app import seed_canales_comerciales as seed
    # ⚠️ Bajo `<HOTEL_ID>/`: en la raíz se sembraba en TODA propiedad nueva.
    datos = json.loads(seed.ARCHIVO.read_text(encoding="utf-8"))["canales"]
    faltan = [c["code"] for c in datos if not str(c.get("rueda_a", "")).strip()]
    assert not faltan, f"sin `rueda_a` en la semilla: {faltan}"
    # Y el mapeo tiene que ser el mismo que resolvía el diccionario, para que la
    # migración no haya movido un número.
    for c in datos:
        esperado = mx.ENTRADA_A_COMISION.get(c.get("entrada", "") or "", "DIRECT")
        assert c["rueda_a"] == esperado, (
            f"{c['code']} cambió de destino: {esperado} -> {c['rueda_a']}")


# ─── Antes de clonar: las dos guardas que salieron de la auditoria ──────────

def test_no_se_escriben_tarifas_sin_mix():
    """El default de «no pago comision» ya no esta.

    Un escenario sin canales escribia la tarifa neta IGUAL a la rack. Despues el
    motor lee net/rack = 1,0, decide que «mandan las tarifas», y el mixer ya
    nunca lo corrige. Sobre el volumen del Working 2027 son **+$1.494.916,87
    (+23,45%)** de ingreso y +$973.190,88 de utilidad, con los gastos
    moviendose $0,00.

    Hoy ningun escenario esta asi: es el camino que abre el CLONADO, que nace
    sin canales. Por eso la guarda va antes de que exista el clonado.
    """
    import inspect
    from app.api import revenue_api
    # Se mira el CODIGO EJECUTABLE, no el archivo entero: el docstring de la
    # propia guarda cita la linea vieja para explicar de que se trata.
    lineas = [l for l in inspect.getsource(revenue_api).splitlines()
              if "=" in l and not l.lstrip().startswith("#")]
    codigo = chr(10).join(lineas)
    assert "nf_mes[m] = nf if nf else" not in codigo, (
        "volvio el default de «sin comision»: la tarifa neta se escribe a rack")
    # Y las DOS puertas que escriben tarifa neta tienen que pedir el mix.
    entero = inspect.getsource(revenue_api)
    assert entero.count("_exigir_mix(nf_mes, scenario_id)") == 2


def test_la_semilla_de_canales_es_POR_PROPIEDAD():
    """Estaba en la raiz de `seed_data/` y corria en CADA arranque sin filtro de
    hotel: una propiedad nueva heredaba los siete canales de Corcovado y su Net
    Factor. Con el mix de CWL (0,797) sobre una propiedad que venda distinto, el
    error medido va de −$346.109 a +$552.314 al año.

    ⚠️ El ORDEN importo: gatear esto SIN la guarda de arriba habria sido peor
    —la propiedad quedaria sin mix y facturaria +25%—. Heredar un mix ajeno es
    conservador; caer a «sin comision» es inflador.
    """
    import pathlib
    from app import seed_canales_comerciales as seed
    assert seed.ARCHIVO.parent.name != "seed_data", (
        "la semilla volvio a la raiz: la hereda cualquier propiedad nueva")
    assert seed.ARCHIVO.exists(), "CWL perdio su semilla de canales"
    raiz = pathlib.Path(seed.__file__).parent / "seed_data" / "canales_comerciales.json"
    assert not raiz.exists(), "quedo una copia en la raiz, que se siembra igual"


def test_una_propiedad_sin_semilla_no_hereda_la_de_otra():
    """Sin archivo propio, `leer()` devuelve vacio y no se siembra nada. La
    propiedad arranca sin mix —y la guarda le impide escribir tarifas— en vez de
    facturar con el Net Factor de Corcovado sin que nadie se entere."""
    from app import seed_canales_comerciales as seed
    assert seed._archivo("HOTEL_QUE_NO_EXISTE").exists() is False
    original = seed.ARCHIVO
    try:
        seed.ARCHIVO = seed._archivo("HOTEL_QUE_NO_EXISTE")
        assert seed.leer() == []
    finally:
        seed.ARCHIVO = original


def test_la_grilla_derivada_NO_edita():
    """Owner, 2026-08-17: *«todo en mixer… y que viaje aca»*.

    Antes las dos pantallas EDITABAN el mismo numero con una sola direccion de
    sincronizacion: el mixer aplicaba sobre `sales_channel_configs` con
    `DELETE` + `INSERT`, y lo que se editaba en Planning **no volvia nunca** —
    el proximo «Aplicar» lo pisaba sin avisar.

    Y la vuelta no era un olvido: **no tiene solucion unica.** Ahi hay 3 canales
    y en el mixer 7 sub-canales; repartir un DIRECT al 12% entre sus cinco no se
    puede deducir. Por eso se planifica en uno solo y el otro muestra.
    """
    from tests._rutas import FRONT
    txt = (FRONT / "app" / "revenue" / "channels" / "page.tsx").read_text(
        encoding="utf-8")
    assert "saveChannels" not in txt, (
        "la grilla derivada volvio a guardar: dos pantallas escribiendo el "
        "mismo numero, y el «Aplicar» del mixer pisa una de las dos")
    for muerto in ("function setCell", "function addChannel",
                   "function removeChannel", "function handleSave"):
        assert muerto not in txt, f"volvio la edicion: {muerto}"
    # Y el mixer tiene que estar montado ahi, que es el pedido.
    assert "MixerCanales" in txt


def test_el_mixer_es_UN_componente_montado_en_dos_rutas():
    """No una copia. Duplicarlo era garantizar que las dos se separen."""
    from tests._rutas import FRONT
    comp = FRONT / "components" / "MixerCanales.tsx"
    assert comp.exists()
    vieja = (FRONT / "app" / "master-data" / "canales" / "page.tsx").read_text(
        encoding="utf-8")
    assert "MixerCanales" in vieja and len(vieja) < 1500, (
        "la ruta vieja dejo de montar el componente y volvio a tener cuerpo propio")
