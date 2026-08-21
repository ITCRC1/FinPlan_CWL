# -*- coding: utf-8 -*-
"""Ninguna pantalla vuelve a inventar su propia regla de «con cual abrir».

**El defecto (owner, 2026-08-14).** «Lo dejo en Working 2027 y aparece en
Working 2035.» Cuarenta pantallas traian su propia copia de
`sort((a, b) => b.year - a.year)[0]` —«el año mas nuevo»—. El dia que se crearon
los Working 2028 a 2035, el mas nuevo paso a ser 2035 y todos los reportes se
fueron ahi. **Nada fallaba**: cada pantalla mostraba un presupuesto real, solo
que el equivocado. Y ninguna recordaba lo que el usuario elegia.

Y no era una regla: eran TRES conviviendo. `lib/escenarioInicial.ts` y
`escenarioDeArranque` hacian lo mismo con criterios distintos, los dos derivando
el año del RELOJ (`getFullYear() + 1`) — o sea que el 1 de enero de 2027 varias
pantallas se cambiaban solas de escenario. Se borraron las dos.

Esta prueba vigila que la regla siga siendo UNA.
"""
import re

from tests._rutas import FRONT

#: El unico lugar donde vive «con cual abrir».
MODULO = "escenarioPreferido"

#: Lo que una pantalla puede usar para elegir escenario, si viene del modulo
#: compartido. ⚠️ **El nombre solo no alcanza.** `elegir(` es una palabra
#: comun: el 2026-08-20 una pantalla nueva definio su propia `function
#: elegir(...)` local y **paso este control en verde eligiendo por su cuenta**.
#: Un guardian que se conforma con el nombre no vigila nada.
SANCIONADOS_DEL_MODULO = (
    "useEscenarioDe",        # el hook: elige y recuerda
    "elegir(",               # la regla, sin memoria
    "elegirActuales",
    "elegirDelAno",          # eje atado a un calendario fijo
)

#: Estos vienen de otro lado (el contexto de Planning), asi que no se les puede
#: exigir el import del modulo.
SANCIONADOS_AJENOS = (
    "usePlanningScenario",   # el escenario compartido de Planning
    "sharedScenarioOr",
)


def _cumple(texto: str) -> bool:
    """¿Elige con una regla compartida, y no con una copia local?"""
    if any(s in texto for s in SANCIONADOS_AJENOS):
        return True
    # Para los del modulo, el token TIENE que venir acompañado de su import.
    return (any(s in texto for s in SANCIONADOS_DEL_MODULO)
            and MODULO in texto)

#: Pantallas donde el selector NO es «que miro» sino **donde escribo**, y por eso
#: no llevan default recordado. Recordar un destino de escritura es justo el
#: riesgo: se importa una vez sobre el escenario equivocado y la proxima visita
#: la pantalla abre ahi sin que nadie lo note.
#:
#: Si agregas una pantalla aca, escribi el motivo. Una excepcion sin motivo es
#: indistinguible de un olvido.
EXCEPCIONES = {
    "app/admin/import-actuals/page.tsx":
        "el selector es el DESTINO de una importacion de GL real",
    "app/pl/balance-sheet/page.tsx":
        "el selector es el destino de `importBalanceSheet`",
    "app/scenarios/page.tsx":
        "administracion de escenarios; su selector es el ORIGEN de una copia",
    "app/master-data/tipo-cambio/page.tsx":
        "no tiene selector: muestra todas las versiones en filas",
    # El hook `useEscenarioDe` modela UN escenario por pantalla y recuerda cual.
    # Esta compara CUATRO a la vez, y el punto entero es ponerlos lado a lado
    # (un ACTUAL contra un FORECAST contra dos presupuestos). Aplicarle la regla
    # compartida le daria el mismo escenario en las cuatro columnas.
    "app/break-e/comparar/page.tsx":
        "compara CUATRO escenarios a la vez; la regla compartida elige uno solo",
    # ── Costos de Grupos ─────────────────────────────────────────────────────
    #
    # El default de este modulo NO lo elige el frontend: lo decide el backend
    # con `cfg_parametros.escenario_base`, que es una decision del owner («los
    # costos salen del Forecast Working 2026, que es la realidad») y gobierna
    # los Pisos y la Golden Rate con los que se negocia. Aplicarles la regla
    # compartida les daria OTRO escenario, y el piso dejaria de ser el oficial.
    # `getScenarios` aca solo puebla el desplegable.
    "app/cost/page.tsx":
        "el default lo decide el backend (cfg_parametros.escenario_base)",
    "app/cost/descuentos/page.tsx":
        "el default lo decide el backend (cfg_parametros.escenario_base)",
    "app/cost/master-data/page.tsx":
        "compara DOS escenarios a la vez; la regla compartida elige uno solo",
    # El selector no es «que miro»: es SOBRE CUAL muevo el corte. Recordar un
    # destino de escritura es justo el riesgo que esta lista existe para evitar
    # — se cierra un mes en el forecast equivocado y la proxima visita abre ahi.
    # Ademas filtra a FORECAST y arranca en el marcado como Current, que es el
    # unico que avanza solo al importar.
    "app/admin/cierre/page.tsx":
        "el selector es el forecast DONDE se mueve el corte, no que se mira",
}

#: Los modulos que se borraron por duplicar la regla. Que no vuelvan.
BORRADOS = ("escenarioInicial", "escenarioDeArranque")


def _pantallas() -> list:
    return sorted(FRONT.joinpath("app").rglob("*.tsx"))


def test_hay_pantallas_que_revisar():
    """Que la prueba este mirando algo de verdad y no pase en verde vacia."""
    pantallas = _pantallas()
    assert len(pantallas) > 50, f"solo {len(pantallas)}: las rutas no resuelven"
    assert any("getScenarios(" in p.read_text(encoding="utf-8") for p in pantallas)


def test_toda_pantalla_elige_con_la_regla_compartida():
    sin_regla = []
    for p in _pantallas():
        rel = p.relative_to(FRONT).as_posix()
        if rel in EXCEPCIONES:
            continue
        texto = p.read_text(encoding="utf-8")
        if "getScenarios(" not in texto:
            continue
        if not _cumple(texto):
            sin_regla.append(rel)
    assert not sin_regla, (
        "Estas pantallas eligen escenario por su cuenta. Usa `useEscenarioDe` de "
        f"`lib/{MODULO}.ts`, o agregalas a EXCEPCIONES CON EL MOTIVO:\n  "
        + "\n  ".join(sin_regla))


def test_no_vuelven_las_reglas_duplicadas():
    """Tres reglas para la misma pregunta terminan divergiendo sin que nada
    falle: cada pantalla abre en un escenario real, solo que en uno distinto."""
    culpables = []
    for p in list(_pantallas()) + list(FRONT.joinpath("lib").rglob("*.ts")):
        texto = p.read_text(encoding="utf-8")
        for viejo in BORRADOS:
            # El nombre puede quedar mencionado en un comentario que explica por
            # que se borro; lo que no puede volver es el codigo.
            if re.search(rf"\b(import|function|const)\b[^\n]*\b{viejo}\b", texto):
                culpables.append(f"{p.relative_to(FRONT).as_posix()} -> {viejo}")
    assert not culpables, "Volvio una regla duplicada:\n  " + "\n  ".join(culpables)


def test_las_excepciones_dicen_por_que():
    for ruta, motivo in EXCEPCIONES.items():
        assert motivo.strip(), f"{ruta}: excepcion sin motivo"
        assert FRONT.joinpath(ruta).exists(), (
            f"{ruta} ya no existe: sacala de EXCEPCIONES o la lista miente")


def test_la_regla_no_sale_del_reloj():
    """Las dos reglas borradas usaban `getFullYear() + 1`: el corte de un ciclo
    de planificacion lo decide el owner, no la fecha del sistema. Es el mismo
    criterio que rige el rolling forecast, que avanza por dato."""
    fuente = FRONT.joinpath("lib", f"{MODULO}.ts").read_text(encoding="utf-8")
    assert "getFullYear" not in fuente
    for rol in ("budget", "forecast", "actual", "actualAnterior"):
        assert rol in fuente, f"falta el rol {rol}"


# ─── El agujero que dejo pasar los 2034-2035 hasta el 2026-08-17 ──────────────
#
# Owner, 2026-08-17: «siempre que abro andan por 2034-2035». La regla decia
# Working 2027 desde el 14-ago y aun asi pasaba, por DOS motivos que esta prueba
# no miraba:
#
# 1. `sharedScenarioOr` estaba sancionado — con razon, Planning comparte
#    escenario— pero cada pantalla le pasaba un FALLBACK propio, con el año
#    quemado a mano: `all.find(s => s.type === "BUDGET" && s.year === 2026)`.
#    Veintitres pantallas asi. Sancionar el hook y no mirar su argumento es
#    sancionar la mitad de la decision.
# 2. Ese fallback terminaba en `?? all[0]`, y `GET /scenarios/` ordena por **año
#    descendente**: `all[0]` es Working 2035. El «año mas nuevo» que la regla
#    vino a matar seguia vivo, escrito de otra forma.

#: `year === 2026` y compañia, cuando se esta ELIGIENDO un escenario.
ANO_QUEMADO = re.compile(r'type === "(BUDGET|ACTUAL|FORECAST)" && s\.year === 20\d\d')

#: Buscar un escenario CONCRETO por nombre no es «con cual abrir». Igual que en
#: `EXCEPCIONES`, cada una lleva su motivo escrito: una excepcion sin motivo es
#: indistinguible de un olvido.
ANO_QUEMADO_OK = {
    "app/planning/big-picture/page.tsx":
        "no elige default: busca el DESTINO 'Budget 2027 Draft4-BIG' donde "
        "`applyToBig` escribe, y avisa por pantalla si no lo encuentra",
}


def test_ninguna_pantalla_quema_el_ano_para_elegir_escenario():
    """El año del ciclo se cambia en `PREFERENCIA` y en ningun otro lado.

    Quemarlo tiene los dos extremos del mismo defecto: clavado en el ciclo viejo
    (las que decian 2026 cuando ya se planificaba 2027) o cayendo al respaldo
    equivocado cuando el año escrito no aparece."""
    culpables = [rel for r in _pantallas()
                 if ANO_QUEMADO.search(r.read_text(encoding="utf-8", errors="ignore"))
                 and (rel := str(r.relative_to(FRONT)).replace("\\", "/")) not in ANO_QUEMADO_OK]
    assert not culpables, (
        "el año del escenario esta quemado a mano en: " + ", ".join(culpables)
        + " — usa `elegir(all, rol)`")


def test_quien_usa_el_escenario_compartido_elige_con_la_regla():
    """`sharedScenarioOr(x)` decide tanto por `x` como por lo guardado.

    Si `x` no sale de `elegir()`, la pantalla tiene su propia regla escondida en
    el argumento — que es exactamente como sobrevivieron veintitres."""
    culpables = []
    for r in _pantallas():
        txt = r.read_text(encoding="utf-8", errors="ignore")
        if "sharedScenarioOr(" not in txt:
            continue
        # `sharedScenarioOr("")` no propone nada: no es una regla propia.
        if 'sharedScenarioOr("")' in txt and "elegir(" not in txt:
            continue
        if "elegir(" not in txt:
            culpables.append(str(r.relative_to(FRONT)).replace("\\", "/"))
    assert not culpables, (
        "usan el escenario compartido con un respaldo propio: " + ", ".join(culpables))


def test_la_preferencia_es_la_que_pidio_el_owner():
    """Los cuatro escenarios, textuales (owner 2026-08-19).

    Va con nombre y año porque cambiarlos es una decision del owner, no un
    detalle de implementacion: si alguien los mueve, esta prueba lo obliga a
    venir a este archivo y leer de donde salieron.

    **Historial de la decision** —para que el proximo que la cambie sepa que no
    es una constante cualquiera:

    * 2026-08-14: Budget 2027 W, Forecast 2026 W, Actual 2025, Actual 2024.
    * 2026-08-17: los dos ACTUAL avanzan a 2026 y 2025.
    * 2026-08-19: **vuelven a 2025 y 2024.** El Actual 2026 esta a medio subir
      (junio no esta cargado), asi que la app abria comparando contra un año
      incompleto. Un año incompleto no se ve incompleto: se ve malo.

    Que haya ido y vuelto en cinco dias es la razon de que esta prueba exista.
    """
    txt = (FRONT / "lib" / "escenarioPreferido.ts").read_text(encoding="utf-8")
    for esperado in (
        'budget:         { type: "BUDGET",   year: 2027, version: "Working" }',
        'forecast:       { type: "FORECAST", year: 2026, version: "Working" }',
        'actual:         { type: "ACTUAL",   year: 2025 }',
        'actualAnterior: { type: "ACTUAL",   year: 2024 }',
    ):
        assert esperado in txt, f"cambio la preferencia del owner: falta {esperado}"


def test_cambiar_la_preferencia_despega_lo_guardado():
    """⚠️ Cambiar los años SIN subir la generacion no le llega a nadie.

    Lo guardado le gana al default. Si la regla cambia y `GENERACION` no, el
    navegador del owner sigue abriendo con el escenario viejo — y desde afuera
    se ve como si el arreglo no se hubiera hecho. Ya paso una vez (17-ago:
    «siempre que abro andan por 2034-2035»).

    La generacion tiene que nombrar la regla que rige HOY."""
    txt = (FRONT / "lib" / "escenarioPreferido.ts").read_text(encoding="utf-8")
    assert 'export const GENERACION = "2026-08-19-actuales-2025-2024";' in txt, (
        "cambiaron los años de la preferencia y no subieron GENERACION: "
        "el owner va a seguir viendo lo viejo")


def test_lo_guardado_se_puede_despegar():
    """Recordar es lo que hace pegajoso a un valor malo.

    La regla estaba bien y el owner igual abria en 2035, porque **el id viejo ya
    estaba guardado** y lo guardado le gana al default, en silencio y para
    siempre. Sin una forma de invalidar por generacion, arreglar la regla no
    arregla al usuario que ya la sufrio."""
    txt = (FRONT / "lib" / "escenarioPreferido.ts").read_text(encoding="utf-8")
    assert "GENERACION" in txt and "limpiarSiEsDeOtraGeneracion" in txt
    # Y la limpieza tiene que alcanzar a las DOS familias de llaves.
    assert "finplan_planning_scenario" in txt, "la llave compartida de Planning no se limpia"
    compartido = (FRONT / "lib" / "planningScenario.ts").read_text(encoding="utf-8")
    assert "limpiarSiEsDeOtraGeneracion" in compartido


def test_comparar_no_abre_en_los_presupuestos_vacios():
    """La pantalla de comparar esta EXENTA de `useEscenarioDe` —elige cuatro
    escenarios a la vez— pero eso no la exime de la REGLA.

    Sobrevivio ahi el «año mas nuevo»: ordenaba por año descendente y abria en
    **Working 2035 y 2034**, que estan vacios, con el aviso de «no tiene
    estadistica de habitaciones cargada» saliendo siempre. Exento del hook no
    es exento del criterio.

    Sus cuatro casillas son los cuatro escenarios que pidio el owner.
    """
    ruta = FRONT / "app" / "break-e" / "comparar" / "page.tsx"
    txt = ruta.read_text(encoding="utf-8")
    for rol in ("budget", "forecast", "actual", "actualAnterior"):
        assert f'elegir(xs, "{rol}")' in txt, f"comparar no abre con el rol {rol}"
    assert 'sort((a, b) => b.year - a.year)' not in txt, (
        "volvio el «año mas nuevo» en comparar: abre en los Working vacios")
