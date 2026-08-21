# -*- coding: utf-8 -*-
"""Los tipos de habitación salen de la base. Ni a mano, ni por posición.

De la auditoría previa al clonado: había TRES fuentes de verdad del inventario
—la tabla `room_type_configs`, la constante `CWL_ROOM_TYPES` y una lista escrita
a mano en la pantalla de tarifas— y las tres podían decir cosas distintas sin
que nada avisara.

Las dos del backend se cerraron el 2026-08-13 (`_canonical_room_types` y
`_otb_units` leen la tabla). Quedaba la del frontend, y era la peor de las tres:

    const ROOM_TYPES = [{ short: "Deluxe King", sort: 1 }, ...]   // a mano
    const roomTypeIds = [...new Set(rateCards.map(r => r.room_type_id))].sort()
    ROOM_TYPES.map((rt, ri) => ({ rt, rtId: roomTypeIds[ri] }))   // por POSICIÓN

`roomTypeIds` es la lista de UUID de las tarifas cargadas, ordenada **como
texto**. El orden alfabético de un número aleatorio no tiene ninguna relación
con `sort_order`, así que el nombre del renglón no era el del tipo que se estaba
editando — y no es un problema de clones: en Corcovado también, desde siempre.
Con seis tipos hay 720 apareos posibles y uno solo correcto.

De paso: un tipo de habitación SIN tarifa cargada no llegaba a `roomTypeIds`, así
que no aparecía en la pantalla. En una propiedad nueva —donde todavía no hay
tarifas— la pantalla salía vacía y no había dónde digitar la primera.

Esta prueba vigila la PROPIEDAD sobre todo el frontend, no el archivo que falló.
"""
import io
import os
import pathlib
import re

FRONT = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "app"
BACK = pathlib.Path(__file__).resolve().parents[1] / "app"

# Los seis de Corcovado. Escribir cualquiera de estos en el frontend es volver a
# clavar el inventario de UNA propiedad en el código que comparten las cuatro.
NOMBRES_DE_CORCOVADO = [
    "Deluxe King", "Carate Double", "Agujas Queen",
    "Sirena Suites", "Treehouse", "5 Elements",
]


def _fuentes():
    for p in sorted(FRONT.rglob("*.tsx")):
        yield p, io.open(p, encoding="utf-8").read()
    for p in sorted(FRONT.rglob("*.ts")):
        yield p, io.open(p, encoding="utf-8").read()


def test_ninguna_pantalla_nombra_a_mano_un_tipo_de_habitacion():
    culpables = []
    for p, src in _fuentes():
        for nombre in NOMBRES_DE_CORCOVADO:
            if nombre in src:
                culpables.append(f"{p.name}: «{nombre}»")
    assert not culpables, (
        "El inventario de Corcovado quedó escrito en el frontend compartido:\n  "
        + "\n  ".join(culpables)
        + "\nSale de `/hotels/{HOTEL_ID}/room-types/`, que ya viene ordenado."
    )


def test_los_tipos_no_se_aparean_por_posicion():
    """El apareo tiene que ser por `id`, nunca por índice.

    Se busca el patrón, no el nombre de la variable: quien lo reescriba con otro
    nombre cae igual.
    """
    posicional = re.compile(r"roomTypeIds\s*\[|room_type_ids\s*\[\s*(ri|i|idx)\s*\]")
    culpables = [p.name for p, src in _fuentes() if posicional.search(src)]
    assert not culpables, (
        "Se aparea el tipo de habitación por posición en: " + ", ".join(culpables)
        + "\nEl UUID ordenado como texto no tiene relación con `sort_order`."
    )


def test_la_pantalla_de_tarifas_lee_los_tipos_de_la_base():
    src = io.open(FRONT / "revenue" / "rates" / "page.tsx", encoding="utf-8").read()
    assert "/room-types/" in src, "la pantalla de tarifas no pide los tipos al API"
    assert "roomTypes.map(rt =>" in src, "no recorre los tipos que trajo la base"
    assert "rtLabel(rt.code" in src, (
        "el rótulo tiene que ser `code · nombre` como en el resto de la app: el "
        "código es lo canónico entre propiedades, el nombre es solo etiqueta"
    )


def test_el_backend_no_arma_el_inventario_desde_la_constante():
    """Lo que ya se cerró, para que no vuelva por la puerta de atrás."""
    src = io.open(BACK / "api" / "revenue_api.py", encoding="utf-8").read()
    assert "CWL_ROOM_TYPES" not in src.replace("`CWL_ROOM_TYPES`", ""), (
        "revenue_api volvió a leer los tipos de habitación de la constante de "
        "Corcovado en vez de `room_type_configs`"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Agregar un tipo de habitación no puede romper nada (owner, 2026-08-14):
# «en los otros hoteles serán más habitaciones, no quiero tener problemas con
# agregar más».
#
# Corcovado ya pasó de 6 a 8 (SH07 Villas Deluxe, SH08 Residencia, 33 unidades).
# El único punto del backend que tenía el número clavado era el importador del
# Excel de revenue: exigía EXACTAMENTE seis y con ocho se negaba entero, con un
# mensaje que sonaba a falla del sistema en vez de a lo que era — que ese
# archivo trae seis filas.
# ─────────────────────────────────────────────────────────────────────────────

def test_ningun_modulo_exige_un_numero_exacto_de_tipos():
    """Se busca la FORMA del error, no el número 6.

    Comparar el largo de una colección de tipos de habitación contra una
    constante es la firma de esta clase de bug, valga 6, 8 o 30.
    """
    patron = re.compile(
        r"len\(\s*room_types?\s*\)\s*[!=<>]=\s*\d+"
        r"|len\(\s*room_type_ids\s*\)\s*[!=<>]=\s*\d+"
    )
    culpables = []
    for p in sorted(BACK.rglob("*.py")):
        for n, linea in enumerate(io.open(p, encoding="utf-8"), start=1):
            if patron.search(linea):
                culpables.append(f"{p.relative_to(BACK).as_posix()}:{n}: {linea.strip()}")
    assert not culpables, (
        "Alguien volvió a fijar cuántos tipos de habitación puede tener un hotel:\n  "
        + "\n  ".join(culpables)
    )


def test_un_hotel_con_mas_tipos_que_el_excel_igual_importa():
    """8 tipos contra un archivo de 6: importa los 6 y avisa de los otros 2."""
    from app.importers.revenue_importer import repartir_tipos_para_el_excel
    cubiertos, sin_tocar, faltan = repartir_tipos_para_el_excel([1, 2, 3, 4, 5, 6, 7, 8])
    assert cubiertos == [1, 2, 3, 4, 5, 6]
    assert sin_tocar == [7, 8], "los tipos nuevos tienen que salir informados"
    assert faltan == [], "tener MÁS tipos que el archivo no es un error"


def test_el_caso_de_siempre_sigue_igual():
    from app.importers.revenue_importer import repartir_tipos_para_el_excel
    assert repartir_tipos_para_el_excel([1, 2, 3, 4, 5, 6]) == ([1, 2, 3, 4, 5, 6], [], [])


def test_si_faltan_tipos_si_se_niega():
    """Al revés sí es un problema: el archivo trae tarifas que no tienen dónde ir."""
    from app.importers.revenue_importer import repartir_tipos_para_el_excel
    cubiertos, sin_tocar, faltan = repartir_tipos_para_el_excel([1, 2, 3])
    assert faltan == [4, 5, 6]


def test_el_importador_no_recorre_mas_alla_de_sus_filas():
    """La otra mitad: aunque le pasen 8 ids, no puede indexar una fila que no existe."""
    from app.importers import revenue_importer as ri
    assert set(ri.KI_RACK_ROWS) == set(ri.KI_OCC_ROWS) == set(ri.RATES_NET_ROWS), (
        "los tres mapas de filas del Excel tienen que cubrir los mismos tipos"
    )
    src = io.open(BACK / "importers" / "revenue_importer.py", encoding="utf-8").read()
    assert "if sort_order not in SORT_ORDERS_DEL_EXCEL" in src, (
        "los bucles tienen que saltarse los tipos sin fila en el archivo"
    )
    assert "range(1, 7)" not in src, "quedó un recorrido con el 6 clavado"


# ─────────────────────────────────────────────────────────────────────────────
# «Que los códigos no se muevan nunca, y los que se vayan agregando queden
# esclavos en sus posiciones de creación» (owner, 2026-08-14).
#
# El código es lo que liga la categoría entre escenarios, entre reportes y entre
# propiedades: el reporte de Junta cruza por CÓDIGO, porque el `id` cambia de un
# escenario a otro y el nombre se puede editar. Moverlo no da error — reapunta
# historia en silencio, que es la peor forma de fallar.
#
# Había tres agujeros y ninguno avisaba:
#   1. el PUT dejaba cambiar el `code`;
#   2. el PUT dejaba cambiar el `sort_order`, y el importador del Excel mapea
#      sus filas por posición;
#   3. el DELETE borraba la fila de verdad, así que el correlativo volvía a
#      entregar ese número y un `SH08` nuevo podía apuntar a otra categoría.
# ─────────────────────────────────────────────────────────────────────────────

def _revenue_api() -> str:
    return io.open(BACK / "api" / "revenue_api.py", encoding="utf-8").read()


def test_el_codigo_no_se_puede_cambiar():
    import inspect
    from app.api.revenue_api import update_room_type
    src = inspect.getsource(update_room_type)
    assert "if actual and newc != actual:" in src, (
        "el PUT volvió a dejar cambiar el código de una categoría existente"
    )
    # Rellenar un código VACÍO sí se permite: las filas viejas nacieron sin él.
    assert "not actual and await _code_taken" in src, (
        "una categoría sin código todavía tiene que poder recibir el suyo"
    )


def test_la_posicion_de_creacion_no_se_puede_mover():
    import inspect
    from app.api.revenue_api import update_room_type
    src = inspect.getsource(update_room_type)
    assert "payload.sort_order is not None and payload.sort_order != rt.sort_order" in src
    assert '"sort_order"' not in src.split("for field in (")[1].split(")")[0], (
        "sort_order no puede seguir en la lista de campos que se asignan solos"
    )


def test_el_codigo_tampoco_se_mueve_por_la_puerta_de_atras():
    """Asignar `code` en el bucle de campos es la forma silenciosa de moverlo."""
    import inspect
    from app.api.revenue_api import update_room_type
    src = inspect.getsource(update_room_type)
    # `code` sigue en el bucle, pero solo se llega ahí si NO cambió o si estaba
    # vacío. Lo que no puede pasar es que el bucle corra antes de la validación.
    pos_val = src.index("if actual and newc != actual:")
    pos_bucle = src.index("for field in (")
    assert pos_val < pos_bucle, "la validación tiene que correr ANTES de asignar"


def test_borrar_una_categoria_la_oculta_no_la_elimina():
    import inspect
    from app.api.revenue_api import delete_room_type
    src = inspect.getsource(delete_room_type)
    assert "rt.active = False" in src, "el DELETE tiene que ocultar"
    assert "db.delete" not in src, (
        "volvió el borrado físico: eso libera el número y el correlativo lo "
        "vuelve a entregar"
    )


def test_el_correlativo_cuenta_tambien_las_ocultas():
    """Si el auto-código mirara solo las activas, ocultar SH08 haría que la
    siguiente categoría naciera SH08 otra vez."""
    import inspect
    from app.api.revenue_api import create_room_type
    src = inspect.getsource(create_room_type)
    cabecera = src.split("sort_order = payload.sort_order")[0]
    assert "active" not in cabecera, (
        "la consulta que alimenta el correlativo no puede filtrar por `active`"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Semillas por propiedad y etiquetas editables (owner, 2026-08-14):
# «varias cosas no van a aplicar en otros hoteles […] dejame esta parte con el
# nombre editable para poder personalizar estos componentes.»
# ─────────────────────────────────────────────────────────────────────────────

def test_una_propiedad_sin_semilla_no_hereda_la_de_corcovado():
    from app.seed_data import semilla, tiene_semillas
    assert tiene_semillas("CWL"), "Corcovado tiene que conservar sus semillas"
    assert not tiene_semillas("AMA"), "una propiedad nueva no trae nada"
    for nombre in ("paquete", "experiencias", "canales"):
        assert semilla(nombre, "AMA") is None, (
            f"«{nombre}» le llegaría a Amarena la semilla de Corcovado"
        )


def test_la_semilla_de_corcovado_no_cambio_de_valor():
    """Los archivos salieron de las constantes: si un valor se movió, el
    presupuesto de Corcovado cambiaría sin que nadie lo pidiera."""
    from decimal import Decimal
    from app.seed_data import semilla
    paquete = semilla("paquete", "CWL")
    assert paquete["FOOD"]["rate_per_pax_night"] == Decimal("108.0000")
    assert paquete["FOOD"]["bev_food_ratio"] == Decimal("0.3400")
    assert paquete["ACTIVITIES"]["rate_per_pax_night"] == Decimal("101.0000")
    assert paquete["SUSTAINABILITY"]["is_commissionable"] is False
    canales = {c["channel"]: c for c in semilla("canales", "CWL")}
    assert canales["TA"]["mix_pct"] == Decimal("0.600000")
    assert canales["TA"]["commission_pct"] == Decimal("0.280000")


def test_los_numeros_de_la_semilla_no_son_float():
    """Un float acá se arrastra hasta el P&L. El JSON los guarda como texto."""
    from decimal import Decimal
    from app.seed_data import semilla
    p = semilla("paquete", "CWL")
    for comp, d in p.items():
        assert isinstance(d["rate_per_pax_night"], Decimal), comp


def test_el_codigo_del_componente_no_se_puede_inventar():
    """El PUT solo acepta los códigos que el motor sabe calcular."""
    from app.models.component_label import ETIQUETAS_POR_DEFECTO, KIND_PACKAGE
    from app.engine import revenue_calculator as rc
    src = io.open(BACK / "engine" / "revenue_calculator.py", encoding="utf-8").read()
    for code in ("FOOD", "ACTIVITIES", "TRANSPORT", "SUSTAINABILITY"):
        assert code in ETIQUETAS_POR_DEFECTO[KIND_PACKAGE], code
        assert f'"{code}"' in src or f"COMPONENT_" in src
    assert rc is not None


def test_la_etiqueta_se_edita_y_el_codigo_no():
    import inspect
    from app.api.revenue_api import put_component_label
    src = inspect.getsource(put_component_label)
    assert "ETIQUETAS_POR_DEFECTO.get(kind, {})" in src, (
        "tiene que rechazar un código que el motor no conoce"
    )
    assert "fila.label = nuevo" in src
    assert "fila.code =" not in src, "el código no se toca"


def test_ninguna_pantalla_escribe_los_rotulos_del_paquete():
    """Si el rótulo vuelve al frontend, deja de ser editable por propiedad."""
    culpables = []
    for p, src in _fuentes():
        if "COMPONENT_LABELS" in src:
            culpables.append(p.name)
    assert not culpables, (
        "volvió una tabla de rótulos escrita en el frontend: " + ", ".join(culpables)
    )


# ─────────────────────────────────────────────────────────────────────────────
# El Rack & Net no depende del NOMBRE del paquete (owner, 2026-08-14: «los
# paquetes deberían ser editables y borrables; acá lo más importante es el
# package component rack and net rate»).
#
# El tab buscaba la experiencia cuyo nombre contuviera «classic». Renombrarla
# —justo lo que el owner quiere poder hacer— o borrarla hacía que el tab pasara
# a otra experiencia EN SILENCIO, y lo que se digitara ahí quedaba guardado
# contra la que quedara primera. Mismo error que ligar por nombre en vez de por
# llave.
# ─────────────────────────────────────────────────────────────────────────────

def test_ninguna_pantalla_busca_el_paquete_por_su_nombre():
    patron = re.compile(r"/classic/i|classic/i\.test|\.name\s*\)\s*\.\s*includes\(\s*[\"']classic", re.I)
    culpables = [p.name for p, src in _fuentes() if patron.search(src)]
    assert not culpables, (
        "Se volvió a elegir la experiencia por su nombre en: " + ", ".join(culpables)
        + "\nEl owner puede renombrarla; la base es una marca (`es_base`)."
    )


def test_la_experiencia_base_es_una_marca_explicita():
    src = io.open(FRONT / "revenue" / "package-components" / "page.tsx", encoding="utf-8").read()
    assert "exps.find(e => e.esBase)" in src, "el Rack & Net tiene que leer la marca"
    assert "es_base: e.esBase" in src, "la marca tiene que viajar en el guardado"
    assert "marcarBase" in src, "tiene que poder elegirse cuál es la base"


def test_borrar_la_base_no_deja_al_rack_sin_fuente():
    src = io.open(FRONT / "revenue" / "package-components" / "page.tsx", encoding="utf-8").read()
    assert "!quedan.some(e => e.esBase)" in src, (
        "al borrar la experiencia base, la primera que quede tiene que tomar el relevo"
    )


def test_el_backend_garantiza_exactamente_una_base():
    import inspect
    from app.api.revenue_api import bulk_package_components
    src = inspect.getsource(bulk_package_components)
    assert "base_idx = marcadas[0] if marcadas else 0" in src, (
        "si no llega ninguna marcada tiene que valer la primera — el tab no puede "
        "quedarse sin fuente"
    )
    assert "es_base=(i == base_idx)" in src, "solo UNA puede quedar marcada"
