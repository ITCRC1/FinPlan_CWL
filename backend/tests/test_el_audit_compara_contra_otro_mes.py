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
    assert "pre-cierre/integral:base" in txt          # la ranura de base
    assert "mesesCol" in txt                          # el mes por columna
    assert "mismo mes" in txt                         # el default de siempre
    # El sufijo solo se manda cuando el mes es OTRO.
    assert "m && m !== mes ? `${id}@${m}` : id" in txt
    # Y la base arranca en el mes anterior, que es para lo que se pidio.
    assert "mes > 1 ? [m[0], m[1], mes - 1] : m" in txt
