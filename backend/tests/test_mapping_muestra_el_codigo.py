# -*- coding: utf-8 -*-
"""El Account Mapping muestra el código del departamento, no solo el nombre.

«¿Por qué en el master data no pones el código de departamento, al igual que
está la cuenta?» (owner, 2026-08-12).

No es simetría cosmética: **el código es lo que RUTEA el P&L**. `_ensure_dept_code`
lo deriva del nombre cuando falta, y si el nombre no es de los que sabe leer, la
regla queda sin código y la cuenta cae en la línea del primer departamento. Ese
dato decisivo estaba en la respuesta del API y la tabla no lo pintaba.

Y buscándolo apareció uno peor: el botón «crear regla» del tab «Sin mapear»
precargaba el CÓDIGO dentro del campo del NOMBRE. En ese momento
`dept_code_from_name("0120")` devolvía `None`, así que toda regla creada por ese
camino nacía sin código.

(Desde el 2026-08-14 el derivador SÍ entiende un código, así que ese camino ya no
perdería el dato. El arreglo del frontend se mantiene igual: un código pertenece
al campo del código.)
"""
import inspect
import io
import os


def _archivo(ruta: str) -> str:
    p = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ruta)
    return io.open(p, encoding="utf-8").read()


def test_la_tabla_muestra_el_codigo_del_departamento():
    src = _archivo("app/admin/mapping/page.tsx")
    assert "{row.dept_code" in src, "la columna no pinta el código"


def test_una_regla_sin_codigo_se_ve_a_simple_vista():
    """Es el caso que rutea mal. Si sale igual que las demás, no se encuentra."""
    src = _archivo("app/admin/mapping/page.tsx")
    assert "var(--negative)" in src, "la regla sin código tiene que resaltarse"
    assert 't("noCode")' in src, "el rótulo sale del catálogo"
    assert _catalogo("es")["mapping.noCode"] and _catalogo("en")["mapping.noCode"]


def test_el_buscador_encuentra_por_codigo():
    """El código de departamento tiene que ser buscable, no solo visible.

    Se comprueba que el campo entre en los que se buscan — no la forma exacta
    de escribirlo. La versión vieja comparaba la expresión literal y se rompió
    al ampliar el buscador (2026-08-18), aunque el comportamiento mejoró:
    ahora busca por palabras y sobre más campos.
    """
    src = _archivo("app/admin/mapping/page.tsx")
    i = src.index("const filtered = useMemo")
    bloque = src[i:i + 1800]
    for campo in ("m.dept_code", "m.account_code", "m.source_department"):
        assert campo in bloque, f"el buscador no mira {campo}"


def test_el_buscador_encuentra_por_LINEA_del_pl():
    """Owner (2026-08-18): «la búsqueda actual no es tan buena». Escribir
    «OPEX_ROOMS» —lo que la tabla muestra en la columna Línea P&L— no
    encontraba nada: se buscaba el nombre de la línea, nunca su código."""
    src = _archivo("app/admin/mapping/page.tsx")
    i = src.index("const filtered = useMemo")
    assert "m.report_line_code" in src[i:i + 1800]


def test_se_puede_filtrar_por_departamento_y_por_linea():
    """Dos desplegables, para no depender de acertar el texto."""
    src = _archivo("app/admin/mapping/page.tsx")
    assert "filterDept" in src and "filterLine" in src
    assert 't("allDepts")' in src and 't("allLines")' in src
    assert _catalogo("es")["mapping.allDepts"] == "Todos los departamentos"
    assert _catalogo("en")["mapping.allDepts"] == "All departments"


def test_el_codigo_se_puede_escribir_a_mano():
    """Cuando el nombre no es de los que el derivador sabe leer, tiene que haber
    forma de poner el código sin entrar a la base."""
    src = _archivo("app/admin/mapping/page.tsx")
    assert 'set("dept_code", e.target.value)' in src


def test_sin_mapear_precarga_el_codigo_en_el_campo_del_codigo():
    """El bug: `prefillDept` es un CÓDIGO («0120») y entraba al campo del NOMBRE.
    `dept_code_from_name("0120")` es None, así que la regla nacía sin código."""
    src = _archivo("app/admin/mapping/page.tsx")
    assert "dept_code: initial?.dept_code ?? prefillDept" in src
    assert "source_department: initial?.source_department ?? prefillDept" not in src


def test_el_derivador_ahora_SI_entiende_un_codigo():
    """Antes no, y esa era la prueba de que el bug de arriba perdía el código.

    Desde el 2026-08-14 sí lo entiende: la plantilla del Detalle escribe el
    departamento como «0165 · Gift Shop», y el parser lee el código del inicio
    sin adivinar. Un archivo bajado y vuelto a subir resuelve exacto — y un
    departamento SIN nombre en el catálogo (el 0240) ya no se queda sin
    departamento al re-subirlo, que era como se perdía la fila.

    **El arreglo del frontend sigue haciendo falta igual** y su prueba sigue
    arriba: un código pertenece al campo del código, entienda o no el derivador.
    Que las dos cosas estén bien es lo que hace que esto no vuelva.
    """
    from app.importers.gl_detail_importer import dept_code_from_name
    assert dept_code_from_name("0120") == "0120"
    assert dept_code_from_name("260") == "260"
    assert dept_code_from_name("0165 · Gift Shop") == "0165"
    # Y el fuzzy de siempre, para los archivos que el owner arma a mano.
    assert dept_code_from_name("Departamento de A&B") == "0120"


def test_el_api_devuelve_el_codigo():
    """La tabla no puede pintar lo que no le llega."""
    from app.api.mapping_api import AccountMappingOut
    assert "dept_code" in AccountMappingOut.model_fields


def test_el_codigo_se_sigue_derivando_cuando_no_lo_mandan():
    """Poder escribirlo no puede haber roto el automático: la mayoría de las
    reglas se crean sin tocarlo."""
    from app.api import mapping_api
    src = inspect.getsource(mapping_api._ensure_dept_code)
    assert "dept_code_from_name" in src
    assert 'if not (obj.dept_code or "").strip()' in src, (
        "solo deriva cuando falta: un código escrito a mano manda")


def _catalogo(idioma: str) -> dict:
    """El catálogo de idiomas, aplanado.

    ⚠️ Varias pruebas de este archivo comprobaban un CRITERIO buscando su texto
    dentro del `.tsx`. Al extraer los textos al catálogo (2026-08-19) ese texto
    dejó de estar ahí — el criterio no cambió, cambió de archivo. Y ahora se
    comprueba en LOS DOS idiomas: si solo se mirara el español, la pantalla en
    inglés podría perder la garantía sin que nadie se entere.
    """
    import json

    from tests._rutas import FRONT

    def plano(o, p=""):
        for k, v in o.items():
            if isinstance(v, dict):
                yield from plano(v, f"{p}{k}.")
            else:
                yield f"{p}{k}", v

    return dict(plano(json.loads(
        (FRONT / "messages" / f"{idioma}.json").read_text(encoding="utf-8"))))
