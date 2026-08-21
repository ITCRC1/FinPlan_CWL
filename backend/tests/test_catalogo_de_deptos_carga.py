# -*- coding: utf-8 -*-
"""El catálogo de departamentos tiene que CARGAR, no caer al respaldo.

«Parece que todavía tiene solo número pero no tiene nombre» (owner, 2026-08-12,
mirando el selector de OPEX con «0115 — 0115», «0130 — 0130»…).

La causa era una llave mal escrita: `cargarDepartamentos()` armaba su propio
header y leía el token de `localStorage["token"]`, mientras toda la app lo guarda
en `localStorage["finplan_token"]`. `/departments/` pide autenticación, así que
devolvía **401 siempre**, y `if (!res.ok) return CATALOGO` se lo tragaba sin
decir nada. La app nunca vio el catálogo real: vivió con la lista de respaldo de
22 entradas, y los seis departamentos que no estaban ahí salían con el código
repetido.

**El daño no era solo el rótulo.** Por el mismo camino viaja lo que el
provisionamiento esconde: con el 401, `APAGADOS` quedaba vacío y la matriz no
filtraba nada. Se llenaba y no hacía efecto — el mismo fallo silencioso de
siempre, en otra pantalla.
"""
import io
import os
import re


def _archivo(ruta: str) -> str:
    p = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ruta)
    return io.open(p, encoding="utf-8").read()


def test_hay_una_sola_forma_de_autenticar():
    """Un fetch que arma su propio header se desincroniza del resto y falla
    callado. Nadie fuera de `lib/api.ts` debería tocar la llave del token."""
    for ruta in ("lib/cwl-depts.ts",):
        src = _archivo(ruta)
        assert 'localStorage.getItem("token")' not in src, (
            f"{ruta} lee una llave de token propia")
        assert "authHeaders()" in src, f"{ruta} debería usar el header compartido"


def test_ningun_otro_archivo_inventa_la_llave_del_token():
    """El centinela: si mañana otro fetch crudo copia el patrón, esto lo caza."""
    raiz = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
    culpables = []
    for base, _dirs, files in os.walk(raiz):
        if "node_modules" in base or ".next" in base:
            continue
        for f in files:
            if not f.endswith((".ts", ".tsx")):
                continue
            p = os.path.join(base, f)
            src = io.open(p, encoding="utf-8", errors="ignore").read()
            if re.search(r'localStorage\.(get|set)Item\(\s*"token"', src):
                culpables.append(os.path.relpath(p, raiz))
    assert not culpables, f"usan la llave «token» en vez de la del sistema: {culpables}"


def test_el_fallo_de_carga_deja_rastro():
    """Un catálogo que no carga se ve como departamentos sin nombre y como un
    provisionamiento que no hace nada. Ninguna de las dos cosas apunta a la
    causa, así que tiene que quedar dicho en la consola."""
    src = _archivo("lib/cwl-depts.ts")
    assert "console.warn" in src
    assert src.count("console.warn") >= 2, "el 4xx y la falta de red son distintos"


def test_el_respaldo_esta_al_dia_con_el_catalogo():
    """El respaldo existe para el primer render. Si le faltan departamentos, esos
    salen como «0115 — 0115» hasta que llegue la respuesta — y si la respuesta
    nunca llega, para siempre."""
    src = _archivo("lib/cwl-depts.ts")
    codigos = re.findall(r'dept_code: "(\d+)"', src)
    assert len(codigos) >= 38, f"el respaldo tiene {len(codigos)} departamentos, la base 38"
    for c in ("0115", "0116", "0130", "0165", "0181", "0184"):
        assert c in codigos, f"falta {c}: saldría como «{c} — {c}»"


def test_ningun_departamento_del_respaldo_se_llama_como_su_codigo():
    src = _archivo("lib/cwl-depts.ts")
    for code, name in re.findall(r'dept_code: "(\d+)",\s*dept_name: "([^"]*)"', src):
        assert name and name != code, f"{code} no tiene nombre de verdad"
