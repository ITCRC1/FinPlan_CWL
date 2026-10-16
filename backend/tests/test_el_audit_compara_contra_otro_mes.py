# -*- coding: utf-8 -*-
"""Una columna del Audit Integral puede apuntar a OTRO mes del mismo escenario.

Owner, 2026-10-16: *«aca en precierre me gustaria tener la oportunidad de poder
revisar contra el mes anterior para usarlo como base de validacion... jalo
precierre agosto y precierre Setiembre y despues compara contra forecast y
budget..solo ocupo poder jalar mes anterior y escoger mes anterior»*.

## Lo que faltaba no era el dato: era poder pedirlo

El espejo de Pre-Cierre ya tiene agosto Y setiembre —medido el 2026-10-16: 198
cuentas en agosto, 202 en setiembre—. Lo que no se podia era apuntarle una
columna: el mes salia de la PANTALLA, asi que las tres columnas miraban
siempre el mismo mes y el espejo solo podia repetir lo que ya estaba en la
columna del actual.

Ahora cada entrada de `scenarios` es `id` o `id@mes`.

⚠️ Sin `@mes` se comporta EXACTAMENTE como antes: los enlaces guardados y
cualquier cliente viejo siguen funcionando.
"""
import inspect

from app.api import auditoria_gl_api as api


def test_la_entrada_acepta_id_arroba_mes():
    fuente = inspect.getsource(api.audit_integral)
    assert 'sid, _, m_txt = crudo.partition("@")' in fuente
    # Y el mes viaja al lector, que es el que ya sabia recibirlo.
    assert "_por_cuenta_del_escenario(db, esc, m)" in fuente


def test_sin_arroba_el_mes_es_el_de_la_pantalla():
    """La compatibilidad hacia atras, explicita."""
    fuente = inspect.getsource(api.audit_integral)
    assert "m = int(m_txt) if m_txt else mes" in fuente


def test_un_mes_invalido_NO_revienta_la_pantalla():
    """⚠️ El `@mes` llega de la URL y puede venir con cualquier cosa.

    Reventar la pantalla entera por un sufijo mal escrito seria peor que
    ignorarlo: el resto del cuadro es correcto y util.
    """
    fuente = inspect.getsource(api.audit_integral)
    assert "except ValueError:" in fuente
    assert "if not 1 <= m <= 12:" in fuente


def test_el_MISMO_escenario_en_dos_meses_da_DOS_columnas():
    """⚠️ La trampa de este cambio, y es silenciosa.

    «Pre-Cierre agosto» y «Pre-Cierre setiembre» son el MISMO `scenario_id`. Si
    la llave de columna fuera el id pelado, la segunda pisaria a la primera: el
    cuadro se veria perfecto mostrando un solo mes dos veces, y las variaciones
    contra la base darian cero —que se lee como «cuadra»—.

    Por eso la llave lleva el mes.
    """
    fuente = inspect.getsource(api.audit_integral)
    assert '"clave": f"{esc.id}@{m}" if m != mes else esc.id' in fuente
    assert 'montos = {v["clave"]:' in fuente
    # Y la columna se ROTULA con el mes, o no habria como saber cual es cual.
    assert 'f"{rotulo} · {MESES_ES[m - 1]}"' in fuente


def test_el_nombre_del_detalle_sigue_usando_el_id_DE_VERDAD():
    """`_nombres_del_detalle` busca en las tablas del escenario: si le llegara
    la llave con `@mes` no encontraria nada y los detalles saldrian sin nombre."""
    fuente = inspect.getsource(api.audit_integral)
    assert '_nombres_del_detalle(db, [v["scenario_id"] for v in versiones])' in fuente


def test_la_pantalla_ofrece_la_tercera_ranura_y_el_mes():
    import pathlib

    p = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "app"
         / "pre-cierre" / "AuditIntegral.tsx")
    txt = p.read_text(encoding="utf-8", errors="replace")
    assert 'useState<string>("MAYOR")' in txt        # la ranura de base
    assert "mesesCol" in txt                          # el mes por columna
    assert "mismo mes" in txt                         # el default de siempre
    # El sufijo solo se manda cuando el mes es OTRO.
    assert "m && m !== mes ? `${id}@${m}` : id" in txt
    # Y la base arranca en el mes anterior, que es para lo que se pidio.
    assert "mes > 1 ? [m[0], m[1], mes - 1] : m" in txt


def test_cada_ranura_dice_CUAL_es():
    """Owner, 2026-10-16: *«estoy enredado»*.

    La primera version puso tres selectores IDENTICOS en fila, sin rotulo. Los
    dejo armados al reves —la base en «ACTUAL actual 2025» y el Budget en
    agosto— y la pantalla no daba ninguna pista de que eso estuviera mal.

    Tres controles que se ven iguales y hacen cosas distintas necesitan decir
    cual es cual: el rotulo no es decoracion.
    """
    import pathlib

    p = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "app"
         / "pre-cierre" / "AuditIntegral.tsx")
    txt = p.read_text(encoding="utf-8", errors="replace")
    for rotulo in ("Base de validacion", "Budget", "Forecast"):
        assert f'"{rotulo}"' in txt, rotulo
    # Y cuando una columna mira OTRO mes, el rotulo lo dice y se resalta: es la
    # unica senal de que el cuadro no esta comparando mes contra mes.
    assert "otroMes && ` · ${MESES[mesesCol[iMes] - 1]}`" in txt
    assert '"1px solid var(--brand)"' in txt


def test_la_base_arranca_en_el_MAYOR_del_mes_anterior():
    """⚠️ Esta prueba exigia el espejo de Pre-Cierre hasta el 2026-10-16, y el
    criterio cambio por una razon medida, no por gusto.

    El owner aclaro: *«quiero mismo detalle de agosto y de setiembre»*. El
    espejo de Pre-Cierre NO puede darlo —el modelo `ActualEntry` dice
    literalmente *«Totals only, no detail»*— asi que una base sacada de ahi se
    queda en la cuenta y no sirve para lo que se pidio. El MAYOR si tiene el
    tercer segmento, el asiento y el proveedor.

    Y hay una segunda razon, mas importante: la columna del Actual tambien sale
    del mayor. Con las dos del mismo origen, una diferencia entre agosto y
    setiembre es de la OPERACION. Con origenes distintos podria ser del camino,
    y no habria como distinguirlo.
    """
    import pathlib

    p = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "app"
         / "pre-cierre" / "AuditIntegral.tsx")
    txt = p.read_text(encoding="utf-8", errors="replace")
    assert 'useState<string>("MAYOR")' in txt
    assert 'value="MAYOR"' in txt          # y se puede elegir otra cosa
    assert "Totals only, no detail" not in txt   # la razon vive en el backend


# ── La base a MAXIMO DETALLE ───────────────────────────────────────────────

def test_la_base_puede_ser_el_MAYOR_de_otro_mes():
    """Owner, 2026-10-16: *«quiero mismo detalle de agosto y de setiembre y que
    me sirva de primera base comparativa»*.

    El Pre-Cierre no puede darlo: llega a la cuenta y se acaba —el modelo dice
    *«Totals only, no detail»*—. El detalle vive en el MAYOR, que es de donde
    sale la columna del Actual. Por eso la base es `MAYOR@mes`.
    """
    fuente = inspect.getsource(api.audit_integral)
    assert 'if sid.strip().upper() == "MAYOR":' in fuente
    assert "_mayor_de(db, anio, m, puente)" in fuente
    assert '"por_detalle"' in fuente


def test_el_actual_y_la_base_se_depuran_con_la_MISMA_funcion():
    """⚠️ Si cada columna depurara por su cuenta, agosto y setiembre podrian
    diferir por el CODIGO y no por la operacion — y el cuadro se veria perfecto
    mintiendo. Las dos reglas que importan son el signo y el puente de
    departamentos."""
    fuente = inspect.getsource(api.audit_integral)
    assert "real, por_cta = _depurar_el_mayor(filas, puente)" in fuente
    dep = inspect.getsource(api._depurar_el_mayor)
    assert "signo_de(f.seg1)" in dep
    assert "puente.get(f.seg2, f.seg2)" in dep
    # Y `_mayor_de` usa la misma, no una copia.
    assert "_depurar_el_mayor(filas, puente)" in inspect.getsource(api._mayor_de)


def test_el_detalle_es_la_UNION_de_los_dos_meses():
    """⚠️ El error de lectura mas caro que puede tener una base comparativa.

    Si solo se recorriera el mes actual, una partida que DEJO de gastarse
    desapareceria del cuadro — y «no esta» se lee como «no cambio». Medido
    contra produccion el 2026-10-16: 96 detalles existian en agosto y no en
    setiembre, y 54 nacieron en setiembre.
    """
    fuente = inspect.getsource(api.audit_integral)
    assert 'd3s = {d3 for (dd, cc, d3) in real if dd == dep and cc == cta}' in fuente
    assert 'd3s |= {d3 for (dd, cc, d3) in v["por_detalle"]' in fuente


def test_el_mayor_que_falta_se_AVISA_y_el_resto_del_cuadro_sirve():
    """Un mes sin mayor subido no puede tumbar la pantalla entera: el resto de
    las columnas es correcto y util."""
    fuente = inspect.getsource(api.audit_integral)
    assert "no esta subido: la " in fuente
    assert '"avisos": avisos,' in fuente


def test_el_mayor_del_MISMO_mes_no_se_duplica():
    """Seria la columna del Actual otra vez, con variaciones de cero que se leen
    como «cuadra». Pasa en enero, donde el mes anterior es de otro ano."""
    fuente = inspect.getsource(api.audit_integral)
    assert "if m == mes:" in fuente


def test_la_base_sale_PRIMERO_en_la_pantalla():
    """Owner: *«quiero que salga primero Agosto, como base comparativa y
    precierre Setiembre contra forecast o budget»*. Se lee de izquierda a
    derecha: de donde venia, donde esta, contra que se compara."""
    import pathlib

    p = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "app"
         / "pre-cierre" / "AuditIntegral.tsx")
    txt = p.read_text(encoding="utf-8", errors="replace")
    assert "const colsMonto = useMemo" in txt
    assert "return [...base, undefined, ...resto];" in txt
    # Y el detalle solo compara contra las columnas que TIENEN detalle.
    assert "v?.con_detalle" in txt
