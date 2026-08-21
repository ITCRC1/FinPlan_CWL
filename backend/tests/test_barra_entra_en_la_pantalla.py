# -*- coding: utf-8 -*-
"""La barra no puede crecer antes de que quepa.

«Master Data» convertido en «M» (owner, 2026-08-19, con la captura marcada).

La barra escala en cuatro escalones, y la idea es correcta: si hay pantalla,
que la letra sea legible. El defecto era que **cada escalón entraba 300-400px
antes de que su medida cupiera**, así que el escalón PROVOCABA el desborde que
venía a evitar. Cruzar 1700 en un monitor de 1750 dejaba la barra peor que a
1699.

Medido sobre la fuente real de la app, con los doce tabs y el bloque derecho
completo (`Admin` + fecha + ES/EN + chip + usuario + salir + logo):

    fs13.5 px10 → 1827px     fs15 px14 → 2029px     fs16 px18 → 2171px
    fs13.5 px8  → 1775px     fs15 px9  → 1899px     fs16 px11 → 2017px

Los umbrales de hoy salen de la segunda fila. **Si se agrega un tab, hay que
volver a medir**: no son gustos, son anchos.

RE-MEDIDO 2026-08-19 al agregar el tab **COST** (spec `COSTOS_GRUPOS.md` §5).
Medido sobre la barra REAL en produccion, clonando un tab de grupo con su caret
y sumando el ancho de los hijos:

    fs13.5/px8   12 tabs 1109 -> 13 tabs 1169   (+60)
    fs15/px9     12 tabs 1217 -> 13 tabs 1282   (+65)
    fs16/px11    12 tabs 1322 -> 13 tabs 1393   (+71)

Los tres umbrales viejos (1800/1940/2060) quedaban POR DEBAJO de lo que el tab
trece necesita, asi que la barra habria vuelto al defecto del «Master Data»
convertido en «M». Los nuevos son 1860 / 1990 / 2115.

⚠️ **No se mide con `scrollWidth`.** `.nav-scroll` es `flex: 1 1 auto`, asi que
cuando sobra lugar su `scrollWidth` devuelve el ancho del CONTENEDOR y no el del
contenido: da el mismo numero con doce tabs y con trece. Hay que sumar el
`offsetWidth` de los hijos.
"""
import io
import os
import re


def _css() -> str:
    p = os.path.join(os.path.dirname(__file__), "..", "..", "frontend",
                     "app", "globals.css")
    return io.open(p, encoding="utf-8").read()


def _escalones(css: str):
    """[(min-width, {var: valor})] de los bloques que tocan --nav-fs."""
    fuera = []
    for m in re.finditer(r"@media \(min-width: (\d+)px\)\s*\{(.*?)\n\}", css, re.S):
        cuerpo = m.group(2)
        if "--nav-fs" not in cuerpo:
            continue
        v = dict(re.findall(r"--nav-(fs|px):\s*([\d.]+)px", cuerpo))
        fuera.append((int(m.group(1)), v))
    return sorted(fuera)


# Ancho MEDIDO que necesita cada combinación (fs, px). Ver el docstring.
NECESITA = {
    (13.5, 8.0): 1835,
    (15.0, 9.0): 1964,
    (16.0, 11.0): 2088,
}


def test_cada_escalon_entra_recien_cuando_su_medida_cabe():
    esc = _escalones(_css())
    assert len(esc) == 3, f"cambió la cantidad de escalones: {esc}"
    for ancho, v in esc:
        clave = (float(v["fs"]), float(v["px"]))
        assert clave in NECESITA, (
            f"el escalón de {ancho}px usa fs{clave[0]}/px{clave[1]}, que no está "
            f"medido. Medir antes de cambiarlo — ver el docstring")
        necesita = NECESITA[clave]
        assert ancho >= necesita, (
            f"el escalón de {ancho}px activa fs{clave[0]}/px{clave[1]}, que "
            f"necesita {necesita}px: entre {ancho} y {necesita} la barra se "
            f"corta, y el tab partido no se distingue de uno que no existe")


def test_los_escalones_van_de_menor_a_mayor():
    esc = _escalones(_css())
    anchos = [a for a, _ in esc]
    fs = [float(v["fs"]) for _, v in esc]
    assert anchos == sorted(anchos) and fs == sorted(fs), (
        "un escalón más ancho tiene que traer letra más grande, no al revés")


def test_los_adornos_vuelven_en_el_orden_en_que_se_sacrifican():
    """Fecha, chip y logo también empujan. Cada uno tiene que volver DESPUÉS
    del ancho que su presencia exige (1631 / 1528 / 1460 medidos)."""
    css = _css()
    def umbral(clase):
        m = re.search(r"@media \(min-width: (\d+)px\) \{ \." + clase, css)
        assert m, f"no encontré el umbral de .{clase}"
        return int(m.group(1))
    fecha, chip, logo = umbral("nav-fecha"), umbral("nav-hotel"), umbral("nav-logo")
    assert logo >= 1460, f"el logo vuelve en {logo} y su presencia pide 1460"
    assert chip >= 1528, f"el chip vuelve en {chip} y su presencia pide 1528"
    assert fecha >= 1631, f"la fecha vuelve en {fecha} y su presencia pide 1631"
    assert logo < chip < fecha, (
        "el orden de sacrificio es fecha → chip → logo, así que vuelven al revés")


def test_la_fila_avisa_cuando_sigue():
    """Si igual desborda, tiene que verse. Un corte limpio en el borde es
    indistinguible de que el tab no exista."""
    css = _css()
    bloque = re.findall(r"\.nav-scroll\s*\{[^}]*\}", css)
    assert any("mask-image" in b for b in bloque), (
        "se fue el degradado del borde derecho: sin él, un tab cortado no "
        "avisa que hay más fila")


def test_no_quedan_rotulos_partidos_a_la_mitad():
    """«Break-E» no era una abreviatura: era una palabra cortada, y su versión
    «completa» del tooltip decía exactamente lo mismo."""
    import json
    for idioma in ("es", "en"):
        p = os.path.join(os.path.dirname(__file__), "..", "..", "frontend",
                         "messages", f"{idioma}.json")
        nav = json.load(io.open(p, encoding="utf-8"))["nav"]
        assert nav["groups"]["breakEven"] == "Break-Even", idioma
        assert nav["groupsFull"]["breakEven"] != nav["groups"]["breakEven"], (
            f"{idioma}: el tooltip «completo» repite el rótulo corto, "
            f"así que no aclara nada")
