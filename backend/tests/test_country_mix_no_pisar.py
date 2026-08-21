# -*- coding: utf-8 -*-
"""Volver a subir el XML no puede borrar lo que se corrigió a mano.

**La regla (owner, 2026-08-18).** «Este archivo se sube una única vez para el
mes, y después se baja y se edita. Entonces un mismo mes no debería subirse más
de 2 veces.»

O sea: el XML de Opera escribe el mes UNA vez; la plantilla corregida lo escribe
una segunda. **Un tercer paso del importador sobre ese mes borra la
corrección** — `import_country_xml` hace `delete` de los meses del archivo y
vuelve a insertar— y hasta este cambio lo hacía en silencio.

El defecto no es teórico: el flujo que el owner describe TERMINA en una
corrección a mano. Cualquier re-subida posterior del XML —por equivocación, por
querer agregar un mes nuevo, por probar— la borraba sin decir nada, y el número
volvía a ser el de Opera sin que nada lo indicara.

La defensa tiene dos partes y las dos hacen falta:

1. Saber **de dónde vino** cada mes (`origen`: `'xml'` o `'manual'`).
2. Que el importador **se frene** —409— cuando el mes ya se corrigió, y solo
   siga si alguien lo pide explícito con `sobrescribir=true`.

Marcar el origen sin frenar no sirve de nada, y frenar sin saber el origen
frenaría también la primera carga legítima.
"""
import inspect

from app.api import revenue_api
from app.models.country_mix import CountryMixEntry


def test_la_tabla_sabe_de_donde_vino_cada_mes():
    cols = CountryMixEntry.__table__.columns
    assert "origen" in cols, (
        "sin `origen` no hay forma de distinguir «primera carga» de «estás por "
        "pisar lo que corregiste»")
    assert "actualizado_en" in cols


def test_el_importador_SE_FRENA_si_el_mes_se_corrigio_a_mano():
    src = inspect.getsource(revenue_api.import_country_xml)
    assert 'o == "manual"' in src, "tiene que mirar el origen de lo que ya está"
    assert "ErrorApi(409" in src
    assert "sobrescribir" in src


def test_el_freno_esta_ANTES_del_borrado():
    """Si el 409 saliera después del `delete`, el dato ya estaría perdido."""
    src = inspect.getsource(revenue_api.import_country_xml)
    assert src.index("ErrorApi(409") < src.index("delete(CountryMixEntry)"), (
        "el freno tiene que cortar antes de borrar nada")


def test_se_puede_sobrescribir_a_proposito():
    """El freno avisa, no prohíbe. Rehacer un mes desde el XML es legítimo —
    solo tiene que ser una decisión, no un accidente."""
    src = inspect.getsource(revenue_api.import_country_xml)
    assert "sobrescribir: bool = Query(False)" in src, "y por defecto NO sobrescribe"
    assert "if corregidos and not sobrescribir:" in src


def test_el_importador_marca_lo_suyo_como_xml():
    src = inspect.getsource(revenue_api.import_country_xml)
    assert 'origen="xml"' in src


def test_la_plantilla_marca_su_edicion_como_MANUAL():
    """Es lo que el freno protege. Sin esto, el freno nunca se dispara."""
    src = inspect.getsource(revenue_api.country_mix_subir_plantilla)
    assert 'origen="manual"' in src


def test_la_grilla_de_pantalla_tambien_marca_manual():
    """«Load countries» edita a mano igual que la plantilla."""
    src = inspect.getsource(revenue_api.put_country_mix_entry)
    assert 'origen="manual"' in src


def test_el_import_dice_que_meses_ya_estaban():
    """Para que una re-subida se vea, aunque sea legítima."""
    src = inspect.getsource(revenue_api.import_country_xml)
    assert '"meses_ya_cargados"' in src


def test_el_mensaje_nombra_los_meses_y_no_los_numera():
    """«Los meses 3, 7» no le dice nada a nadie; «Mar, Jul» sí."""
    src = inspect.getsource(revenue_api.import_country_xml)
    assert "_MES_CORTO[m - 1]" in src


def test_la_migracion_127_deja_lo_viejo_como_xml():
    """Las filas que ya estaban vinieron del importador: ese es su origen. Si
    quedaran como `manual`, el freno se dispararía en la próxima subida
    legítima y sería un estorbo desde el día uno."""
    src = open("alembic/versions/127_country_mix_origen.py", encoding="utf-8").read()
    assert 'server_default="xml"' in src


# ── Un mes por subida ────────────────────────────────────────────────────────
#
# «No se puede subir 2 meses a la vez, es mes por mes» (owner, 18-ago-2026).
#
# El archivo de Opera trae el rango entero —el del owner, siete meses de una— y
# antes se cargaban todos juntos. Eso choca de frente con la otra regla suya: el
# mes se sube UNA vez y después se corrige a mano. Cargando siete de un saque,
# subir el mes nuevo obligaba a pasar por encima de los seis anteriores, ya
# corregidos — justo lo que el freño de `origen` viene a evitar.

def test_el_import_pide_elegir_el_mes_si_el_archivo_trae_varios():
    src = inspect.getsource(revenue_api.import_country_xml)
    assert '"motivo": "elegir_mes"' in src
    assert '"meses_disponibles"' in src
    assert "len(disponibles) > 1" in src


def test_un_archivo_de_UN_solo_mes_no_pregunta_nada():
    """Si no hay ambigüedad, preguntar es un estorbo."""
    src = inspect.getsource(revenue_api.import_country_xml)
    assert "month = disponibles[0]" in src


def test_solo_se_escribe_el_mes_elegido():
    """El filtro tiene que aplicarse ANTES de plegar y escribir: si no, se
    guardarían los doce igual y la regla sería solo un cartel."""
    src = inspect.getsource(revenue_api.import_country_xml)
    filtro = src.index("if k[1] == month")
    # La LLAMADA, no el `import` de la función —que está más arriba y haría
    # pasar esta prueba por el motivo equivocado.
    assert filtro < src.index("plegar_a_lista(del_anio")
    assert filtro < src.index("delete(CountryMixEntry)")


def test_pedir_un_mes_que_el_archivo_no_trae_se_avisa():
    src = inspect.getsource(revenue_api.import_country_xml)
    assert "if month not in disponibles:" in src
