# -*- coding: utf-8 -*-
"""La tarifa neta puesta a mano no la pisa ninguna resincronizacion.

Owner, 2026-10-27, sobre el Net Rate de las villas: *«dame para yo poner esto
manual por ahora.. editable»*.

## Que protege

Las villas se venden a **$1,700 netos**. El modelo del sistema es
`net = rack x net factor`, asi que cargarlos como rack les aplicaba el 20,30%
del mes y presupuestaba $1,354.90 — $345 menos por noche, ~$73.000 menos en el
ano sobre 212 noches. Sin error y sin aviso.

La bandera `rate_cards.net_rate_manual` (mig 159) dice «esta celda la puso una
persona». Habia TRES rutas que reescribian la neta desde el rack:

1. el guardado masivo de Rack Rates,
2. el Mixer de canales cuando regenera tarifas,
3. el resync previo al «Push to the checkbook».

Cualquiera de las tres, sin la guarda, devuelve la formula encima del valor
negociado y el presupuesto sale mal **cuadrando consigo mismo**.

## Por que el test mira el CODIGO y no corre el motor

Lo que hay que impedir no es un calculo equivocado: es que aparezca una CUARTA
ruta que escriba `net_rate` sin preguntar. Eso no se ve ejecutando las tres que
ya existen — se ve recorriendo el modulo. Por eso la prueba enumera cada
asignacion de `net_rate` del backend y exige que su funcion consulte la bandera,
salvo las que estan explicitamente permitidas abajo.
"""
import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

#: Funciones que SI pueden escribir la neta sin mirar la bandera, y por que.
PERMITIDAS = {
    # Es la puerta que PONE el valor manual — preguntar por la bandera que ella
    # misma escribe no tendria sentido.
    "set_net_rate_manual",
    # Importa un escenario entero desde Excel: nacen tarjetas nuevas, no se
    # resincroniza ninguna existente.
    "import_revenue",
    "_importar_tarifas",
}


def _funciones_que_escriben_net_rate():
    """(archivo, funcion, ¿consulta la bandera?) por cada escritura de `net_rate`."""
    salida = []
    for py in sorted(APP.rglob("*.py")):
        if "__pycache__" in str(py):
            continue
        src = py.read_text(encoding="utf-8")
        if ".net_rate" not in src and "net_rate=" not in src:
            continue
        try:
            arbol = ast.parse(src)
        except SyntaxError:                      # pragma: no cover
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            cuerpo = ast.get_source_segment(src, nodo) or ""
            escribe = any(
                isinstance(h, ast.Attribute) and h.attr == "net_rate"
                for a in ast.walk(nodo) if isinstance(a, ast.Assign)
                for h in a.targets
            )
            if escribe:
                salida.append((py.name, nodo.name, "net_rate_manual" in cuerpo))
    return salida


def test_toda_escritura_de_la_neta_mira_la_bandera():
    """Una ruta nueva que reescriba la neta tiene que preguntar primero.

    ⚠️ Si esta prueba falla con un nombre que no conocias, NO lo agregues a
    `PERMITIDAS` sin leer que hace: lo normal es que sea una resincronizacion
    nueva y lo que corresponda sea saltarse las celdas manuales.
    """
    sin_guarda = [
        (arch, fn) for arch, fn, mira in _funciones_que_escriben_net_rate()
        if not mira and fn not in PERMITIDAS
    ]
    assert not sin_guarda, (
        "Estas funciones reescriben `net_rate` sin consultar `net_rate_manual`: "
        f"{sin_guarda}. Una neta negociada (villas a $1,700) vuelve a "
        "`rack x factor` y el presupuesto queda mal cuadrando consigo mismo."
    )


def test_las_tres_rutas_conocidas_siguen_protegidas():
    """Las tres que motivaron la bandera, nombradas una por una.

    El test de arriba es general y podria pasar en verde si alguien BORRA una
    ruta entera. Estas tres existen y tienen que seguir preguntando.
    """
    por_archivo = {}
    for arch, fn, mira in _funciones_que_escriben_net_rate():
        por_archivo.setdefault(arch, {})[fn] = mira

    assert any(mira for fn, mira in por_archivo.get("mixer_api.py", {}).items()), \
        "El Mixer de canales regenera tarifas sin mirar la bandera"

    revenue = por_archivo.get("revenue_api.py", {})
    guardadas = [fn for fn, mira in revenue.items() if mira]
    assert len(guardadas) >= 2, (
        "En revenue_api.py tienen que quedar protegidas al menos el guardado "
        f"masivo de rack y el resync del push; protegidas hoy: {guardadas}"
    )


def test_el_modelo_tiene_la_bandera_y_nace_apagada():
    """Default `false`: ninguna tarifa existente se congela por la migracion."""
    from app.models.rate_card import RateCard
    col = RateCard.__table__.columns["net_rate_manual"]
    assert not col.nullable
    assert str(col.server_default.arg).lower() in ("false", "'false'", "0")
