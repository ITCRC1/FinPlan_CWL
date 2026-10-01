# -*- coding: utf-8 -*-
"""Planning Report: los doce meses de una version y el ano de todas.

Owner, 2026-10-01, mirando el cierre y pidiendolo para el Budget 2027: *«por que
no creas un tab llamado Planning Report»* · *«quiero 12 meses, y full year para
comparar con otras versiones»* · *«quizas aca no necesitamos revisar mes, YTD o
Full Year»* · *«ajustado todos los reportes para que se pueda generar reportes
para comparar todos. desde los reportes, hasta los checkbooks»*.

## Que defiende este archivo

1. **La FORMA.** Doce columnas de mes de la version principal, una de ano por
   version, y la variacion. Si alguien le agrega el selector de mes o de corte
   que tiene el cierre, deja de ser este reporte.
2. **Que los CUATRO niveles tengan las MISMAS columnas.** El P&L, las cinco
   aperturas, los cinco checkbooks y las estadisticas salen todos de
   `armarCuadro`. No es economia de lineas: la columna «Full Year» de la
   apertura de opex tiene que ser la misma celda que la del P&L, o el dia que
   alguien agregue una version comparada una de las dos hojas resta las
   versiones cambiadas sin que nada falle.
3. **Que la columna del ano sea una FORMULA.** Es la celda que mas se mira, y la
   unica del cuadro que se puede escribir como `=SUM(B5:M5)` sin inventar nada:
   sus doce sumandos estan en la misma fila.
4. **Que la cascada use la MISMA tabla de componentes que el cierre.** Dos listas
   de que suma cada subtotal se separan en el primer renglon que alguien agregue
   de un lado, y el exportador descarta la formula que no cuadra EN SILENCIO:
   nadie se entera hasta que falta media hoja de formulas.

## Lo que este archivo NO puede comprobar leyendo el codigo

Que los ORDINALES de cada formula apunten a la fila que suman. `suma_de` son
indices sobre un arreglo que el modo compacto acorta, y el checkbook arma dos
pisos —cada departamento suma sus cuentas y el TOTAL suma los departamentos—.
Un corrimiento de uno no rompe nada que se vea.

Eso lo comprueba `tests/js/planning_report.js`, que arma los cuadros de verdad
con datos sinteticos y suma celda por celda; `test_los_ordinales_de_cada_formula`
lo corre. Y los numeros se verificaron aparte contra produccion: el libro abierto
en Excel y recalculado entero, celda con formula contra celda del motor.
"""
import pathlib
import shutil
import subprocess

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
FRONT = RAIZ / "frontend"
LIB = FRONT / "lib/planningReport.ts"
PAGINA = FRONT / "app/planning/report/page.tsx"
TABLA = FRONT / "app/planning/report/Tabla.tsx"
HARNESS = pathlib.Path(__file__).parent / "js/planning_report.js"


def _lib() -> str:
    return LIB.read_text(encoding="utf-8")


def _pagina() -> str:
    return PAGINA.read_text(encoding="utf-8")


def test_la_pantalla_existe_y_esta_en_el_menu():
    """Una pantalla que nadie puede abrir es una pantalla que no existe."""
    assert PAGINA.exists(), "falta app/planning/report/page.tsx"
    nav = (FRONT / "components/TopNav.tsx").read_text(encoding="utf-8")
    assert '{ key: "planningReport", href: "/planning/report" }' in nav
    for idioma in ("es", "en"):
        msgs = (FRONT / f"messages/{idioma}.json").read_text(encoding="utf-8")
        assert '"planningReport"' in msgs, f"falta el rotulo en {idioma}"


def test_son_DOCE_meses_y_el_ano_no_hay_corte():
    """⚠️ Lo que distingue este reporte del cierre.

    El cierre parte el ano en mes, acumulado y ano porque contesta «como vamos».
    Planning contesta «como queda el ano»: el acumulado a octubre no dice nada
    ahi. Si aparece un selector de corte o de mes, el reporte dejo de ser este.
    """
    lib = _lib()
    assert 'const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",' in lib
    assert "DOCE.map" in lib
    pagina = _pagina()
    for prohibido in ('"ytd"', "setMes(", "horizonte", "setHorizonte"):
        assert prohibido not in pagina, (
            f"la pantalla volvio a tener {prohibido}: es el reporte del cierre, "
            "no el de planning")


def test_los_CUATRO_niveles_usan_LAS_MISMAS_columnas():
    """⚠️ El P&L, las aperturas, los checkbooks y las estadisticas, por un solo
    constructor.

    La columna «Full Year» de la apertura de opex tiene que ser la MISMA celda
    —mismo indice, misma formula, misma version— que la del P&L: el libro se baja
    entero y se compara hoja contra hoja. Con dos constructores, el dia que
    alguien agregue una version comparada una de las dos hojas apunta a la
    columna de al lado y resta las versiones cambiadas sin que nada falle.
    """
    lib = _lib()
    # Un solo lugar arma columnas, y los cuatro cuadros pasan por `armarCuadro`.
    assert lib.count("export function columnasPlanning(") == 1
    assert lib.count("columnasPlanning(") == 2, (
        "columnasPlanning se llama desde mas de un lugar: tiene que ser "
        "`armarCuadro` y nadie mas")
    for constructor in ("cuadroPlanning", "cuadroApertura",
                        "cuadroCheckbook", "cuadroEstadisticas"):
        assert f"export function {constructor}(" in lib, f"falta {constructor}"
        cuerpo = lib[lib.index(f"export function {constructor}("):]
        cuerpo = cuerpo.split("export function ")[1]
        assert "return armarCuadro({" in cuerpo, (
            f"{constructor} arma su cuadro a mano en vez de pasar por armarCuadro")


def test_la_columna_del_ANO_baja_como_formula():
    """`=SUM(B5:M5)`: sus doce sumandos estan en la misma fila, asi que es la
    unica columna del cuadro que se puede escribir sin inventar nada.

    ⚠️ **Y es la de la version que puso los meses, no siempre la primera.** Las
    otras columnas de ano NO la llevan, y es correcto: sus doce meses no estan
    en la hoja y la formula no tendria a que apuntar — el exportador la tiraria
    igual, en silencio.
    """
    lib = _lib()
    assert "suma_cols: DOCE.map((_m, i) => 1 + i)" in lib
    assert "...(vi === mv ? { suma_cols:" in lib, (
        "la formula quedo clavada en la primera columna de ano: con los meses "
        "de otra version apunta a sumandos que no estan en la hoja")


def test_los_doce_meses_pueden_ser_de_CUALQUIER_version():
    """Owner, 2026-10-01: *«quiero que metas la opcion de generar un 12 meses de
    Forecast y Budget 2026»*.

    El ano de cada version siempre esta; esto elige de cual se abre la
    estacionalidad. Vale para las SIETE vistas, porque todas pasan por
    `armarCuadro`.
    """
    lib = _lib()
    assert "mesesDe?: number;" in lib
    # Los siete constructores lo usan: ninguno quedo leyendo la version 0 fija.
    for constructor in ("cuadroPlanning", "cuadroApertura", "cuadroCheckbook",
                        "cuadroPosiciones", "cuadroReparto"):
        cuerpo = lib[lib.index(f"export function {constructor}("):]
        cuerpo = cuerpo.split("export function ")[1]
        assert "opciones.mesesDe ?? 0" in cuerpo, (
            f"{constructor} sigue abriendo siempre la primera version")
    pagina = _pagina()
    assert "setMesesDe(" in pagina
    assert "ids[Math.min(mesesDe, ids.length - 1)]" in pagina, (
        "las estadisticas siguen pidiendo los doce meses de la primera version: "
        "abririan un ano distinto que las otras seis hojas")
    assert "if (mesesDe >= ids.length) setMesesDe(0);" in pagina, (
        "sacar una version de la comparacion deja la eleccion colgada")


def test_la_variacion_resta_las_dos_columnas_de_ANO():
    """Y apunta al bloque de anos, no a los meses: `resta` son indices de columna
    y el bloque empieza en la 13."""
    lib = _lib()
    assert "const BASE_ANIO = 13" in lib
    assert "resta: [BASE_ANIO + par[0], BASE_ANIO + par[1]]" in lib


def test_la_cascada_usa_la_MISMA_tabla_que_el_cierre():
    """⚠️ Importada, no copiada.

    `componentesDelPL` dice que suma cada subtotal y `resultadosDelPL` que resta
    cada resultado. Son del P&L del cierre y es la MISMA cascada: una segunda
    copia se desactualiza en el primer renglon que alguien agregue de un lado, y
    el exportador tira la formula que no cuadra sin decir nada.
    """
    lib = _lib()
    assert 'from "@/lib/tresCortes"' in lib
    assert "componentesDelPL(emitidas)" in lib
    assert "resultadosDelPL(emitidas)" in lib
    # Y no se redefinieron aca.
    assert "function componentesDelPL" not in lib
    assert "function resultadosDelPL" not in lib


def test_los_ordinales_se_cuentan_sobre_LO_QUE_SE_EMITE():
    """El modo compacto saca filas. Un indice contado sobre `datos.filas` apunta
    a otra en cuanto una cuenta entra o sale — y degrada en silencio."""
    lib = _lib()
    assert "const emitidas = (datos.filas ?? []).filter(" in lib
    assert "emitidas.map(f =>" in lib


def test_el_checkbook_suma_los_SUBTOTALES_no_las_cuentas():
    """⚠️ El TOTAL del checkbook tiene dos pisos debajo.

    Cada departamento suma sus cuentas y el TOTAL suma los departamentos. Si el
    TOTAL sumara las dos cosas, contaria cada peso dos veces; si sumara las
    cuentas salteandose los subtotales, cuadraria igual pero la hoja tendria dos
    maneras distintas de llegar al mismo numero.
    """
    lib = _lib()
    cuerpo = lib[lib.index("export function cuadroCheckbook("):]
    assert "suma_de: subtotales," in cuerpo
    assert "subtotales.push(filas.length);" in cuerpo


def test_cada_fila_del_checkbook_lleva_SU_departamento():
    """Owner, 2026-09-03: *«los checkbooks deben estar por departamentos, si no
    no se puede saber a que corresponde»*.

    La 7065 de Habitaciones y la 7065 del Club son dos filas. Agrupadas por
    cuenta a secas el resultado no es de nadie.
    """
    lib = _lib()
    cuerpo = lib[lib.index("export function cuadroCheckbook("):]
    assert "f.dept_code" in cuerpo and "f.dept_name" in cuerpo


def test_el_ano_de_una_RAZON_no_se_suma():
    """⚠️ La ocupacion, el ADR, el RevPAR y los socios del ano NO son la suma de
    los doce meses.

    El promedio de doce promedios no es el promedio del ano, y el promedio de
    socios lo calcula el servidor sobre los meses CON socios (owner, 2026-09-02:
    «quiero que me des un promedio de los meses y no que sume»). Por eso el ano
    se le pide con el periodo completo en vez de sumarse en la pantalla.
    """
    lib = _lib()
    assert "razon: true" in lib, "las filas de razon dejaron de estar marcadas"
    pagina = _pagina()
    assert "getEstadisticasCierre(id, d, h)" in pagina
    assert "unoNulo(id, 1, 12)" in pagina, (
        "el ano de las estadisticas se dejo de pedir con el periodo completo")


def test_la_pantalla_dibuja_EL_MISMO_cuadro_que_baja():
    """⚠️ Owner, 2026-08-27: «el excel no baja lo que esta viendo».

    Los cuatro constructores devuelven un `Cuadro` y UN solo renderizador lo
    dibuja. Con una tabla en JSX y otra en el exportador, las dos pueden decir
    cosas distintas — y ya paso una vez.
    """
    pagina = _pagina()
    for constructor in ("cuadroPlanning(", "cuadroApertura(",
                        "cuadroCheckbook(", "cuadroEstadisticas("):
        assert constructor in pagina, f"la pantalla no dibuja {constructor}"
    assert "<Tabla cuadro={cuadro} />" in pagina
    assert "bajarCuadros(" in pagina
    tabla = TABLA.read_text(encoding="utf-8")
    assert "cuadro.columnas.map(" in tabla and "cuadro.filas.map(" in tabla


def test_el_excel_trae_TODO_lo_que_la_vista_abre():
    """En la pantalla se mira un ambito —o una clase— por vez; en un libro que se
    manda, todos juntos son la comparacion que se hace igual, y pedir cinco
    archivos es pedir que uno se olvide.

    Las siete vistas se arman en `hojasDe`, que es lo que usan tanto el boton de
    la vista como el del paquete.
    """
    pagina = _pagina()
    bloque = pagina[pagina.index("const hojasDe = useCallback("):]
    assert "for (const a of AMBITOS)" in bloque, "el P&L dejo de traer los tres ambitos"
    assert bloque.count("for (const a of APERTURAS)") == 2, (
        "los checkbooks —con y sin detalle— y las aperturas bajan las CINCO clases")
    assert "for (const m of METRICAS_POSICION)" in bloque, (
        "la plantilla tiene que bajar el FTE Y el sueldo")
    assert "for (const t of REPARTOS)" in bloque, (
        "el reparto tiene que bajar cafeteria Y lavanderia")


def test_abre_en_un_BUDGET_con_la_regla_COMPARTIDA():
    """Es la pantalla de planificar: abrir en el ACTUAL seria abrir en el ano que
    ya paso.

    ⚠️ Y con `useEscenarioDe`, no con una regla propia. Owner, 2026-08-14:
    «lo dejo en Working 2027 y aparece en Working 2035» — cada pantalla traia su
    «el ano mas nuevo» copiado a mano, y el dia que nacieron los Working
    2028-2035 todos los reportes se fueron a 2035 sin que nada fallara.
    """
    pagina = _pagina()
    assert "useEscenarioDe(" in pagina
    assert '"planning/report:budget", escenarios, "budget"' in pagina


def test_cada_columna_declara_su_version():
    """Tres columnas que dicen «Full Year» no se distinguen. La segunda linea de
    la cabecera lleva el nombre de la version."""
    lib = _lib()
    assert 'label: "Full Year", sub: nombre(vi)' in lib
    cols = lib[lib.index("export function columnasPlanning("):]
    assert "Array.from({ length: cuantas }, (_, vi) =>" in cols, (
        "las columnas de ano se dejaron de armar una por version")


def test_el_checkbook_se_ABRE_en_sub_lineas():
    """Owner, 2026-10-01, con el checkbook de OPEX a la vista: *«por que los
    checkbooks no tienen los detalles. todos deben tener detalle»*.

    La celda decia «7105 Contract Services $1.447,83» y no decia que son Coral,
    Fumigacion Hotel y Reservation Fee. Eso vive un nivel mas abajo, en el
    auxiliar, y el endpoint lo trae con `abrir`.

    ⚠️ **La sub-linea sale del AUXILIAR y de ningun otro lado.** El mayor trae
    la cuenta y se acabo: la version que lee de ahi deja la celda VACIA, que no
    es lo mismo que en cero.
    """
    api = (pathlib.Path(__file__).resolve().parents[1]
           / "app/api/detalle_celda_api.py").read_text(encoding="utf-8")
    assert "async def _subs_del_auxiliar(" in api
    assert "if abrir and not manda_el_mayor:" in api, (
        "las sub-lineas se le estan pidiendo a una version donde manda el mayor")
    assert "for sid in series if sid in subs_de" in api, (
        "la version que no abrio esta yendo en CERO: un blanco no es un cero")
    lib = _lib()
    cuerpo = lib[lib.index("export function cuadroCheckbook("):]
    assert "const deCuenta: number[] = [];" in cuerpo, (
        "el subtotal de departamento volvio a contar `desde + i`, que con "
        "sub-lineas en el medio apunta a una sub-linea")
    assert "suma_de: deCuenta," in cuerpo


def test_la_plantilla_trae_salario_y_FTE():
    """Owner, 2026-10-01: *«quisiera tambien bajar las posiciones por
    departamento con salario y FTE»* · *«este FTE report tambien en el tab»*.

    ⚠️ **El salario contratado va en el ROTULO, no en una columna.** Esta en
    colones o en dolares segun la posicion: sumarlo mezclaria dos monedas y el
    total no seria ninguna cifra. Lo que si se suma es el sueldo del mes en
    dolares, que es la otra metrica — y ese lo CALCULA EL MOTOR (`c6000_sw`),
    no la pantalla: rehacer `salario x FTE / TC` daria una plantilla que no
    cuadra con la 6000 del P&L.
    """
    lib = _lib()
    assert "export function cuadroPosiciones(" in lib
    assert "export const METRICAS_POSICION" in lib
    assert "salarioEnRotulo(p.salary_amount, p.salary_currency)" in lib
    api = (pathlib.Path(__file__).resolve().parents[1]
           / "app/api/payroll_api.py").read_text(encoding="utf-8")
    assert "getattr(e, \"c6000_sw\", 0)" in api, (
        "el sueldo en dolares se esta volviendo a calcular en vez de leerlo")


def test_las_posiciones_se_emparejan_por_NOMBRE_no_por_id():
    """⚠️ Al clonar un escenario las posiciones nacen con `id` nuevo.

    Con el id como llave, la misma plaza aparece en una fila por version y el
    cuadro entero sale en diagonal: cada fila con un solo numero y el resto
    vacio. Se emparejan por departamento + posicion + empleado.
    """
    lib = _lib()
    cuerpo = lib[lib.index("export function cuadroPosiciones("):]
    for campo in ("p.dept_code", "p.position_name", "p.employee_name"):
        assert campo in cuerpo, f"la llave de emparejar dejo de usar {campo}"
    assert "porVersion.find(m => m.has(k))" in cuerpo


def test_el_reparto_muestra_CON_QUE_se_repartio():
    """Owner, 2026-10-01: *«el tab de allocation de laundry y cafeteria, con
    todos los parametros y distribucion, kilos FTE para distribuir»*.

    Con el reparto solo, «Habitaciones $7.023» no se puede discutir; con el peso
    al lado, si.

    ⚠️ **El peso es `basis_value`: el numero que el motor USO.** Volver a sumar
    el FTE de la plantilla o los kilos de la configuracion daria una segunda
    definicion del mismo reparto — coincidiria casi siempre, y el dia que no, el
    cuadro explicaria un reparto que no ocurrio.
    """
    lib = _lib()
    assert "export function cuadroReparto(" in lib
    assert "datos.resumen[vi]?.BASES?.[tipo]?.[k]" in lib
    assert 'formato: "num1"' in lib, (
        "la base se esta mirando como dolares: son FTE y kilos")
    api = (pathlib.Path(__file__).resolve().parents[1]
           / "app/api/allocation_api.py").read_text(encoding="utf-8")
    assert "e.basis_value or 0" in api
    assert 'in ("FTE", "KILOS")' in api, (
        "el credito de la fuente esta entrando como peso: no es un destino")


def test_el_BUDGET_PACKAGE_arma_con_el_MISMO_armador():
    """Owner, 2026-10-01: *«esto debe ser un Budget Package para revision
    rapida»*.

    ⚠️ Un paquete que junte las hojas por su cuenta seria una segunda definicion
    de cada una — y la que se manda a revision es justamente esa. `hojasDe` es
    el armador del boton de cada vista Y del paquete.
    """
    pagina = _pagina()
    assert "async function bajarPaquete()" in pagina
    bloque = pagina[pagina.index("async function bajarPaquete()"):]
    assert "for (const v of VISTAS)" in bloque
    assert "await hojasDe(v.id)" in bloque, (
        "el paquete arma las hojas por su cuenta en vez de usar `hojasDe`")
    # Y el boton de la vista usa el mismo.
    vista = pagina[pagina.index("async function bajar()"):
                   pagina.index("async function bajarPaquete()")]
    assert "await hojasDe(vista)" in vista


def test_donde_NO_hay_sub_lineas_se_DICE():
    """El costo de ventas y el ingreso no tienen un nivel debajo de la cuenta.

    ⚠️ Una hoja vacia se lee como «falta el dato». Se dice que no hay, y por
    que: el costo lo explica su DRIVER y el ingreso ya esta en su nivel mas
    fino. Partirlos en sub-lineas que nadie presupuesto haria que el reporte
    abra mas de lo que se decidio.
    """
    pagina = _pagina()
    assert 'vista === "detalle" && (clase === "cost" || clase === "revenue")' in pagina
    assert "DRIVER" in pagina


@pytest.mark.skipif(shutil.which("node") is None, reason="no hay node")
def test_los_ordinales_de_cada_formula():
    """⚠️ Lo unico que no se puede comprobar leyendo el codigo.

    `suma_de` son indices sobre un arreglo que el modo compacto acorta. Un
    corrimiento de uno no rompe nada que se vea: el exportador comprueba la
    formula contra el numero y, cuando no cuadra, **la descarta en silencio**. El
    reporte baja con media hoja de numeros pegados y nadie se entera.

    El arnes arma los cuadros de verdad y suma celda por celda, columna por
    columna. Se midio que FALLA: corriendo en uno el ordinal del subtotal de
    departamento, 45 de las 193 comprobaciones se caen.
    """
    if not (FRONT / "node_modules/typescript").exists():
        pytest.skip("falta node_modules del frontend")
    r = subprocess.run(["node", str(HARNESS)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 fallos" in r.stdout, r.stdout


def test_el_OPERANDO_de_la_cascada_no_lo_esconde_el_modo_compacto():
    """⚠️ Una linea en cero que ALGUNA resta usa no es detalle: es un termino.

    `resultadosDelPL` solo declara la formula cuando encuentra TODOS los
    operandos. Si el modo compacto escondio uno por estar en cero, no la declara
    y el exportador deja el numero del motor **sin decir nada**.

    Medido el 2026-10-01 en Amarena, donde el impuesto da cero en las tres
    versiones del Budget 2027: `Income Taxes (30%)` se escondia y **NET PROFIT
    bajaba como numero pegado en las tres hojas del P&L** mientras todo el
    detalle de arriba llevaba formula. Es la linea que mas se mira del reporte.

    Este repo hereda la misma cascada, asi que hereda el mismo riesgo.
    """
    tres = (FRONT / "lib/tresCortes.ts").read_text(encoding="utf-8")
    assert "export const OPERANDOS_DE_LA_CASCADA = new Set(" in tres
    assert "Object.values(RESULTADOS).flatMap(r => [...r.mas, ...r.menos])" in tres, (
        "la lista de operandos se escribio a mano: se separa de RESULTADOS en el "
        "primer resultado que alguien agregue")
    for archivo in ("lib/tresCortes.ts", "lib/planningReport.ts"):
        src = (FRONT / archivo).read_text(encoding="utf-8")
        assert "OPERANDOS_DE_LA_CASCADA.has(f.rotulo)" in src, (
            f"{archivo} vuelve a esconder los operandos en cero")


def test_la_cascada_usa_EL_ROTULO_DE_ESTE_REPO():
    """⚠️ La tabla de la cascada se indexa POR ROTULO, y el rotulo es el de la
    plantilla del P&L de ESTA propiedad.

    Amarena escribe «Total Operating expenses» y las otras tres «Total
    Operationg expenses» —con la errata—. Con el rotulo equivocado el subtotal
    no se encuentra, su formula no se declara y el Excel baja ese renglon como
    numero pegado, sin que nada avise. Es el mismo modo de falla que persigue
    todo este archivo, por la via mas tonta.

    Se comprueban SOLO las tres tablas de la cascada —`SUMA_DEL_DETALLE`,
    `SUMA_DE_SUBTOTALES` y `RESULTADOS`—, que son las que se indexan por rotulo.
    El resto del archivo nombra otras cosas (las clases por naturaleza, los
    ambitos) que no tienen por que estar en la plantilla.
    """
    import re
    pl = (pathlib.Path(__file__).resolve().parents[1]
          / "app/api/pl_detail_api.py").read_text(encoding="utf-8")
    # ⚠️ Las DOS plantillas: la del consolidado y la del Club. La cascada cubre
    # las dos —el Club tiene su propio `Total Gastos`— y mirar solo una deja
    # fuera rotulos que si existen.
    plantilla = set(re.findall(r'\("(?:tot|sub|det)",\s*"([^"]+)"', pl))
    assert plantilla, "no se pudo leer la plantilla del P&L"

    tres = (FRONT / "lib/tresCortes.ts").read_text(encoding="utf-8")
    cascada = tres[tres.index("const SUMA_DEL_DETALLE"):
                   tres.index("export function componentesDelPL")]
    citados = set(re.findall(r'"([^"]+)"', cascada))
    huerfanos = sorted(c for c in citados if c not in plantilla)
    assert not huerfanos, (
        f"la cascada cita rotulos que la plantilla de esta propiedad no tiene: "
        f"{huerfanos}")
