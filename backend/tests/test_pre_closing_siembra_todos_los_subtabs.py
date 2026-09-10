# -*- coding: utf-8 -*-
"""EN PRE-CLOSING, LOS 19 SUB-TABS ABREN EN EL MISMO MES.

Owner, 2026-09-10: *«revisaste tab por tab que todos tengan sembrado las mismas
versiones»* · *«veo algunos que no lo tienen»*.

No los habia revisado uno por uno, y tenia razon: **Utilidad** abria en un
BUDGET con las tres ranuras de comparacion VACIAS, y cargaba su propia lista de
escenarios con `getScenarios(HOTEL_ID)` — que excluye los espejos, asi que no
podia ni ver el precierre.

## Por que un guard y no una revision

Una revision a mano vale para hoy. Esta pantalla tiene 19 sub-tabs y va a
crecer —el owner ya adelanto que le va a colgar mas—, y el modo de falla no
avisa: el sub-tab abre, muestra numeros correctos, y son de OTRA version. Nadie
lo nota hasta que dos sub-tabs se contradicen en una reunion.

La regla que se fija: **un sub-tab que elige su propio escenario tiene que
recibir `esPre`.** Si no lo recibe, no puede saber que la pantalla esta mirando
el mes en revision, y va a abrir en el Actual cerrado.
"""
import io
import os
import re

RAIZ = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
PL = os.path.join(RAIZ, "app", "month-end", "pl")


def _leer(*partes) -> str:
    return io.open(os.path.join(*partes), encoding="utf-8").read()


def _pantalla() -> str:
    return _leer(PL, "Pantalla.tsx")


#: Los que eligen escenario por su cuenta: usan `sembrarTres` (la regla del
#: owner) o `useEscenarioDe` (el selector con memoria). Se detectan por lo que
#: importan y no por una lista escrita a mano — una lista se olvida de crecer
#: justo cuando aparece el sub-tab nuevo, que es cuando importa.
def _eligen_solos() -> dict[str, str]:
    fuera = {}
    for archivo in sorted(os.listdir(PL)):
        if not archivo.endswith(".tsx") or archivo == "Pantalla.tsx":
            continue
        src = _leer(PL, archivo)
        if "sembrarTres" in src or "useEscenarioDe" in src:
            fuera[archivo[:-4]] = src
    return fuera


def test_hay_sub_tabs_que_eligen_solos():
    """Si esto da cero, el detector se rompio y el resto no prueba nada."""
    assert len(_eligen_solos()) >= 3, _eligen_solos().keys()


def test_el_que_elige_solo_recibe_el_modo_o_la_ranura():
    """Cada sub-tab con seleccion propia tiene que saber en que modo esta.

    Dos formas validas de saberlo, y las dos se aceptan:

    * `esPre` — el sub-tab decide con el modo. Es lo que necesita el que ignora
      `inicial` a proposito (Doce Meses, Resumen 12: «12 meses actual y budget
      working 2026 como estandar»).
    * `inicial={ranuras[0]}` — el sub-tab abre en la primera ranura, que en
      Pre-Closing ES el espejo. Alcanza para el que la honra (Auditoria,
      Formato).
    """
    pantalla = _pantalla()
    for nombre in _eligen_solos():
        # Cómo lo monta la pantalla grande.
        m = re.search(r"<" + nombre + r"\b[^>]*>", pantalla, re.S)
        assert m, f"{nombre} elige escenario solo y la pantalla no lo monta"
        montaje = m.group(0)
        assert ("esPre" in montaje) or ("inicial={ranuras[0]" in montaje), (
            f"{nombre} elige su propio escenario y no recibe ni `esPre` ni "
            f"`inicial={{ranuras[0]}}`: en Pre-Closing va a abrir en el Actual "
            f"cerrado y nadie se va a dar cuenta.\nMontaje: {montaje}")


def test_utilidad_ve_los_espejos():
    """⚠️ El caso que se escapo: cargaba su propia lista SIN los espejos.

    `getScenarios(HOTEL_ID)` los excluye por defecto (migracion 140). Un
    sub-tab que trae su propia lista tiene que pedirlos, o el espejo no existe
    para el aunque la pantalla lo tenga elegido.
    """
    src = _leer(RAIZ, "app", "month-end", "pl-detail", "page.tsx")
    assert "getScenarios(HOTEL_ID, esPre)" in src, (
        "pl-detail carga escenarios sin pedir los espejos: en Pre-Closing no "
        "puede ver el precierre")
    assert "es_precierre" in src, "pl-detail no distingue el espejo"


def test_la_regla_generica_nunca_devuelve_un_espejo():
    """`elegir()` la usan 35 archivos. Un espejo es `type=ACTUAL` del mismo año
    que el de verdad, asi que sin el filtro devolvia uno u otro segun el orden
    en que llegara la lista — y el resultado no se nota: sale un numero, y es
    el de un mes que todavia no esta cerrado."""
    src = _leer(RAIZ, "lib", "escenarioPreferido.ts")
    assert "!e.es_precierre" in src, (
        "`elegir()` no descarta los espejos: puede devolver el precierre "
        "donde se pidio el Actual")
