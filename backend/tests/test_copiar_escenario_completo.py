# -*- coding: utf-8 -*-
"""
«CREAR COPIANDO» COPIA EL ESCENARIO ENTERO — O NO HEREDA SU MODO.

## El defecto que estas pruebas cierran

Habia DOS mecanismos de copia con DOS listas distintas:

  · la foto mensual (`snapshot-month/`) clonaba los 16 datasets;
  · «crear copiando» (`copy-from/`) copiaba 7 y dejaba fuera el mayor
    (`actuals`), el snapshot del P&L (`pl_snapshot`) y el capital.

Pero «crear copiando» SI heredaba `source_mode`. Con un origen `imported` —que
lee el P&L del mayor— la copia nacia diciendo «leo del mayor» y sin mayor: el
reporte se iba por el otro camino (los checkbooks) y daba OTROS numeros, sin un
solo error en pantalla.

Medido en produccion, copiando cada escenario con la lista vieja de 7:

    ACTUAL actual 2024       -1,050,380 -> 0            (77 lineas movidas)
    ACTUAL actual 2025       -1,125,963 -> 0            (75 lineas)
    ACTUAL actual 2026          546,132 -> 0            (70 lineas)
    BUDGET Final 2026            13,229 -> 417,840      (88 lineas)
    FORECAST April 2026         -40,190 -> -2,009,142   (86 lineas)
    FORECAST Working 2026        98,628 -> -1,499,169   (84 lineas)

El peor caso no es el que queda vacio: es `BUDGET Final 2026`, que queda LLENO
de numeros plausibles y equivocados por $404,611.
"""
import inspect

from app.api import scenarios_api as SA


def test_copiar_y_fotografiar_llevan_LO_MISMO():
    """Las dos copias tienen que llevarse el mismo escenario.

    `_clone_scenario_data` (la foto mensual) recorre `COPY_DATASETS` entero. Si
    el default de `copy-from` fuera mas corto, volvemos a tener dos mecanismos
    que dicen copiar y copian cosas distintas.
    """
    assert set(SA.DEFAULT_COPY_DATASETS) == set(SA.COPY_DATASETS), (
        "«crear copiando» y la foto mensual ya no copian lo mismo: faltan "
        f"{sorted(set(SA.COPY_DATASETS) - set(SA.DEFAULT_COPY_DATASETS))}")


def test_el_mayor_viaja_por_defecto():
    """Sin estos dos, un origen `imported` produce una copia que miente sobre si
    misma: dice leer del mayor y no tiene mayor."""
    for llave in SA.LLAVES_DEL_MAYOR:
        assert llave in SA.DEFAULT_COPY_DATASETS, (
            f"'{llave}' no viaja por defecto y `source_mode` si: la copia nace "
            f"marcada como historico y sin historico")
    assert SA.COPY_DATASETS["actuals"], "el dataset del mayor quedo vacio"
    assert SA.COPY_DATASETS["pl_snapshot"], "el dataset del snapshot quedo vacio"


def test_el_modo_no_se_hereda_sin_su_mayor():
    """Regla: o viajan `source_mode` Y el mayor, o no viaja ninguno.

    Alguien puede pedir una lista de datasets recortada a mano. En ese caso el
    destino NO debe heredar un `imported` huerfano — tiene que conservar el modo
    que ya traia y decirlo.
    """
    src = inspect.getsource(SA.copy_scenario_data)
    assert "hereda_modo" in src, "no quedo la decision de heredar o no el modo"
    assert "LLAVES_DEL_MAYOR" in src, "el modo se hereda sin mirar si viajo el mayor"
    assert "avisos" in src, "si no hereda el modo, tiene que decirlo"


def test_el_corte_del_forecast_viaja():
    """`actuals_through` es parte de la version: una copia de un forecast con
    actuales hasta junio tiene que nacer con actuales hasta junio, no con doce
    meses de plan donde el original mostraba seis reales."""
    src = inspect.getsource(SA.copy_scenario_data)
    assert "actuals_through" in src, (
        "el corte del rolling forecast no viaja: la copia muestra plan donde el "
        "original mostraba real")


def test_avisa_antes_de_copiar_de_un_origen_vacio():
    """El aviso llegaba tarde: un «copiadas 0 filas» al final, con la copia ya
    creada. Y el origen que la pantalla preseleccionaba era justamente uno
    vacio (Budget Working 2035)."""
    campos = SA.CopyRequest.model_fields
    assert "permitir_origen_vacio" in campos
    assert campos["permitir_origen_vacio"].default is False, (
        "copiar de un escenario vacio no puede ser lo que pasa por defecto")
    src = inspect.getsource(SA.copy_scenario_data)
    assert "permitir_origen_vacio" in src, "la puerta no se usa"
    assert "409" in src, "un origen vacio tiene que frenar, no avisar despues"


def test_la_pantalla_puede_saber_que_hay_adentro_antes_de_elegir():
    """Para no volver a preseleccionar un escenario vacio, la pantalla necesita
    saber cuantas filas tiene cada origen ANTES de que el usuario elija."""
    assert hasattr(SA, "inventario_para_copiar")
    src = inspect.getsource(SA.inventario_para_copiar)
    for clave in ("vacio", "filas_utiles", "tiene_mayor", "etiqueta"):
        assert clave in src, f"el inventario no expone '{clave}'"


def test_vacio_no_es_cero_filas():
    """El andamiaje NO cuenta como datos.

    Medido: los ocho `BUDGET Working 2028..2035` tienen 50 filas cada uno —36 de
    mix de canales, 2 de config de Villas y los 12 TC de `ensure-working`— y las
    110 lineas de su P&L EN CERO. Contar filas a secas los daba por «con datos»,
    y la pantalla los seguia preseleccionando: el defecto entero volvia.
    """
    from app.models.sales_channel_config import SalesChannelConfig
    from app.models.rooms_allocation_config import RoomsAllocationConfig
    from app.models.exchange_rate import ExchangeRate

    for Model in (SalesChannelConfig, RoomsAllocationConfig, ExchangeRate):
        assert Model in SA.TABLAS_DE_ANDAMIAJE, (
            f"{Model.__name__} se crea solo: si cuenta como dato, un escenario "
            f"recien nacido pasa por «con datos»")
    # Un escenario que SOLO tiene andamiaje esta vacio.
    assert SA._utiles({"revenue": 36, "allocations": 2, "rates": 12}) == 0
    # Y uno con datos, no.
    assert SA._utiles({"opex": 549, "_utiles": 549}) == 549


def test_el_inventario_va_en_una_sola_consulta():
    """~45 tablas x una consulta cada una contra la base remota tardaba 15 s al
    abrir la pantalla de Escenarios. Va en un solo UNION ALL."""
    src = inspect.getsource(SA._filas_por_escenario)
    assert "union_all" in src, "el inventario vuelve a hacer una consulta por tabla"
    assert "group_by" in src
