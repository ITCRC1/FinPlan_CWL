# -*- coding: utf-8 -*-
"""Los doce meses del mix en una sola grilla, y lo que no puede salir mal ahi.

Owner, 2026-10-05, con la captura del mix de un mes: *«me gustaria que esto este
lineal por mes para hacer un copy paste desde el Excel»* · *«que sea mas
sencillo de lo que hoy es»* · *«haz todo mas sencillo»*.

## Que se vigila, y por que ESTO y no otra cosa

Las tres reglas de abajo comparten una propiedad: si se rompen, **nada falla**.
La pantalla dibuja, el guardado responde 200 y el presupuesto queda con un
numero distinto del que la persona escribio. Son las unicas tres de esta
pantalla con esa forma, y por eso son las que llevan guarda.
"""
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[2]
GRILLA = RAIZ / "frontend" / "components" / "GrillaMixDoce.tsx"
MIXER = RAIZ / "frontend" / "components" / "MixerCanales.tsx"
API = RAIZ / "backend" / "app" / "api" / "mixer_api.py"


def _grilla() -> str:
    return GRILLA.read_text(encoding="utf-8")


def test_el_pegado_entra_como_NUMERO_del_porcentaje():
    """`52%` tiene que entrar como 52, no como 0,52.

    ⚠️ Las dos funciones existen y hacen cosas distintas: `numeroDeExcel`
    DIVIDE entre cien lo que trae `%` —correcto donde la celda guarda la
    fraccion— y `numeroDePorcentaje` deja el numero. Acá la celda guarda el
    numero, asi que usar la otra meteria un 0,52 donde va un 52: el mix dejaria
    de cerrar en 100 y el Net Factor saldria sobre una base que no es el total.
    """
    s = _grilla()
    assert "numeroDePorcentaje" in s
    # Se mira lo que IMPORTA, no el archivo entero: el comentario de arriba
    # nombra a la otra funcion justamente para explicar por que no se usa.
    importa = [l for l in s.splitlines() if "pegarGrilla" in l and l.startswith("import")]
    assert importa, "la grilla no importa el parser compartido"
    assert "numeroDeExcel" not in importa[0], (
        "la grilla parsea con `numeroDeExcel`: un `52%` pegado entraria como "
        "0,52 y el mix no cerraria")


def test_lo_pegado_cae_en_SU_celda():
    """Un bloque de Excel se reparte por fila y por mes, no todo en la primera.

    Es el mismo defecto que ya se corrigio en la grilla de pax (2026-10-04): sin
    `repartirPegado`, el navegador escribe el bloque entero —tabulaciones
    incluidas— dentro de la celda donde se solto.
    """
    s = _grilla()
    assert "repartirPegado(bloque, fila, mesIdx, subs.length, 12" in s, (
        "el pegado no se reparte por fila y mes: todo caeria en una celda")
    assert "manejarPegado" in s


def test_lo_que_se_guarda_vuelve_a_FRACCION():
    """La celda muestra 55 y la base guarda 0,55.

    ⚠️ Guardar el 55 sin dividir deja un mix de 5500%: el Net Factor sale
    negativo y el ingreso neto del presupuesto se da vuelta. No es un error que
    se note leyendo la grilla, porque la grilla seguiria mostrando 55.
    """
    s = _grilla()
    assert re.search(r"mix_pct: \(mix\[s\.code\]\?\.\[i\] \?\? 0\) / 100", s), (
        "el mix se guarda sin volver a fraccion")
    assert re.search(r"comision_pct: \(com\[s\.code\]\?\.\[i\] \?\? 0\) / 100", s), (
        "la comision se guarda sin volver a fraccion")


def test_la_comision_del_cubo_es_PONDERADA():
    """El promedio simple y el ponderado se separan, y manda el ponderado.

    Lo que se paga depende de cuanto volumen pasa por cada sub-canal. Con cinco
    sub-canales colgando de Direct —y tres de ellos en 0%— el simple y el
    ponderado dan numeros muy distintos, y el que llega al P&L es el ponderado.
    """
    s = _grilla()
    assert "(mix[s.code]?.[i] ?? 0) * (com[s.code]?.[i] ?? 0)" in s, (
        "el resumen no pondera por mix")
    assert "mixes[i] ? pond[i] / mixes[i] : 0" in s, (
        "el resumen no divide el ponderado entre el mix: seria un promedio simple")


def test_el_endpoint_resuelve_con_LA_MISMA_cascada():
    """Los doce meses salen de `mixer.resolver`, no de una lectura cruda.

    Un segundo camino para los mismos numeros es como la grilla y el Net Factor
    terminan discrepando sin que nada falle: la grilla mostraria el dato
    guardado y el motor seguiria aplicando la cascada (mes → escenario → base).
    """
    s = API.read_text(encoding="utf-8")
    i = s.index('@router.get("/canales/mixer/{scenario_id}/doce/")')
    cuerpo = s[i:s.index("@router.", i + 10)]
    assert "mixer.resolver(base, overs, m)" in cuerpo, (
        "el endpoint no resuelve con la cascada: un mes sin excepcion propia "
        "mostraria cero en vez de lo que hereda")
    assert "mixer.derivar(res, codes)" in cuerpo
    assert "for m in range(1, 13)" in cuerpo


def test_lo_avanzado_se_PLEGO_y_no_se_borro():
    """Crear canales, el «rueda a», guardar como base y aplicar siguen estando.

    Owner, 2026-10-05: *«haz todo mas sencillo»*. Simplificar era dejar de
    competir por la atencion con la tarea semanal, no perder funciones: un
    sub-canal nuevo sin `rueda a` no se puede crear desde ningun otro lado.
    """
    s = MIXER.read_text(encoding="utf-8")
    for pieza in ("crearSubCanal", "guardarBase", "aplicarMixer", "rueda_a"):
        assert pieza in s, f"se perdio `{pieza}` al simplificar la pantalla"
    assert "{avanzado && (<>" in s, "lo avanzado no quedo plegado"
    assert "useState(false)" in s.split("const [avanzado")[1][:40], (
        "el acordeon nace abierto: la pantalla no se simplifico")
