# -*- coding: utf-8 -*-
"""El consolidado se puede jalar, y las integraciones no mienten.

**El consolidado (owner, 2026-08-14).** «Esto me abre una opción tipo API para
poder jalar esa información desde algún consolidador.» Cada propiedad expone lo
suyo y quien suma es el de afuera — nadie guarda las llaves de nadie, que era el
defecto de la primera idea (un backend recolector con las credenciales de los
otros tres).

**La prevista.** Está la puerta, no el camino. Y el código no puede fingir lo
contrario: una conexión sin credenciales tiene que verse APAGADA, nunca verde.
"""
import asyncio
import io
import os
import pathlib

BACK = pathlib.Path(__file__).resolve().parents[1] / "app"


# ── La llave de solo lectura ────────────────────────────────────────────────

def test_sin_variable_no_existe_ninguna_llave_valida():
    """Nace apagada: se despliega sin riesgo y el owner decide cuándo encenderla."""
    from app.auth import llave_de_consolidado_valida
    previo = os.environ.pop("CONSOLIDADO_API_KEY", None)
    try:
        assert llave_de_consolidado_valida("lo-que-sea") is False
        assert llave_de_consolidado_valida("") is False
    finally:
        if previo is not None:
            os.environ["CONSOLIDADO_API_KEY"] = previo


def test_la_llave_correcta_abre_y_la_parecida_no():
    from app.auth import llave_de_consolidado_valida
    previo = os.environ.get("CONSOLIDADO_API_KEY")
    os.environ["CONSOLIDADO_API_KEY"] = "llave-de-prueba-larga-123"
    try:
        assert llave_de_consolidado_valida("llave-de-prueba-larga-123") is True
        assert llave_de_consolidado_valida("llave-de-prueba-larga-12") is False
        assert llave_de_consolidado_valida("LLAVE-DE-PRUEBA-LARGA-123") is False
    finally:
        if previo is None:
            os.environ.pop("CONSOLIDADO_API_KEY", None)
        else:
            os.environ["CONSOLIDADO_API_KEY"] = previo


def test_la_llave_se_compara_en_tiempo_constante():
    """Con `==` se puede adivinar la llave midiendo cuánto tarda en responder."""
    src = io.open(BACK / "auth.py", encoding="utf-8").read()
    trozo = src.split("def llave_de_consolidado_valida")[1].split("async def")[0]
    assert "compare_digest" in trozo, "la llave no puede compararse con =="


def test_el_consolidado_no_lleva_el_guard_global():
    """Con `_guard` encima, la llave nunca llegaría a usarse: el guard exige JWT
    y corta antes. Es un detalle que se rompe solo al reordenar main.py."""
    src = io.open(BACK / "main.py", encoding="utf-8").read()
    linea = [l for l in src.splitlines() if "consolidado_router" in l and "include_router" in l]
    assert linea, "el router del consolidado no está registrado"
    assert "_guard" not in linea[0], (
        "el consolidado trae su propia puerta; con el guard global la llave "
        "de solo lectura queda muerta"
    )


# ── El contrato entre propiedades ──────────────────────────────────────────

def test_el_contrato_esta_versionado():
    """Si cambia la forma de la respuesta, un consolidador viejo tiene que poder
    darse cuenta en vez de leer campos que ya no están."""
    from app.api.consolidado_api import CONTRATO
    assert isinstance(CONTRATO, int) and CONTRATO >= 1


def test_las_lineas_se_cruzan_por_codigo_y_no_por_posicion():
    """Dos propiedades pueden tener líneas distintas —una sin Spa, otra sin
    Club— y la suma del que consolida tiene que cuadrar igual."""
    src = io.open(BACK / "api" / "consolidado_api.py", encoding="utf-8").read()
    assert '"line_code"' in src
    assert "por_mes.setdefault(ln.line_code" in src


def test_un_ano_sin_escenario_da_404_y_no_ceros():
    """Un consolidador que recibe ceros los suma como ceros de verdad, y el grupo
    queda mal sin que nada lo delate."""
    src = io.open(BACK / "api" / "consolidado_api.py", encoding="utf-8").read()
    assert 'raise ErrorApi(404, "consolidado.sin_escenario' in src


def test_el_consolidado_no_expone_detalle():
    """Totales por línea y nada más: ni planilla, ni cuentas, ni nombres."""
    src = io.open(BACK / "api" / "consolidado_api.py", encoding="utf-8").read()
    for prohibido in ("PayrollConceptEntry", "OpexEntry", "ActualEntry", "User"):
        assert prohibido not in src, f"el consolidado toca {prohibido}"


# ── La prevista ────────────────────────────────────────────────────────────

def test_ninguna_integracion_se_ve_conectada_sin_credenciales():
    """La regla de oro: sin configurar se ve APAGADA, nunca verde."""
    from app.integraciones import registro
    for clave, inte in registro().items():
        estado = inte.estado()
        if estado["configurada"]:
            continue          # alguien cargó credenciales de verdad
        assert estado["faltan"], f"{clave} dice que le falta nada pero no está configurada"
        r = asyncio.run(inte.probar())
        assert r["conecta"] is False, f"{clave} dice que conecta sin credenciales"
        assert r.get("faltan"), f"{clave} no dice QUÉ le falta"


def test_el_estado_no_devuelve_el_valor_de_ninguna_credencial():
    """Ni truncado: los primeros caracteres de un client_secret ya son media pista."""
    from app.integraciones import registro
    previo = os.environ.get("QBO_CLIENT_SECRET")
    os.environ["QBO_CLIENT_SECRET"] = "secreto-que-no-debe-salir-jamas"
    try:
        texto = str([i.estado() for i in registro().values()])
        assert "secreto-que-no-debe-salir" not in texto
        assert "secreto-que-no" not in texto
    finally:
        if previo is None:
            os.environ.pop("QBO_CLIENT_SECRET", None)
        else:
            os.environ["QBO_CLIENT_SECRET"] = previo


def test_cada_variable_dice_donde_se_saca():
    """Una lista de nombres de variables sin decir de dónde salen no le sirve a
    nadie seis meses después."""
    from app.integraciones import registro
    for clave, inte in registro().items():
        for v in inte.variables:
            assert v.para_que.strip(), f"{clave}.{v.nombre} no dice para qué es"
            assert v.donde_se_saca.strip(), f"{clave}.{v.nombre} no dice dónde se saca"


def test_las_integraciones_son_solo_de_admin():
    src = io.open(BACK / "api" / "integraciones_api.py", encoding="utf-8").read()
    assert src.count("get_current_admin") >= 2, (
        "listar credenciales faltantes ya es información útil para alguien de afuera"
    )


def test_el_host_de_opera_no_esta_escrito_en_el_codigo():
    """El host de OHIP cambia por cadena. Uno inventado sería peor que ninguno."""
    src = io.open(BACK / "integraciones" / "opera_cloud.py", encoding="utf-8").read()
    assert "oraclecloud.com" not in src, "hay un host de Oracle escrito a mano"
    assert "OPERA_BASE_URL" in src


def test_hay_documentacion_de_como_conectar():
    doc = pathlib.Path(__file__).resolve().parents[2] / "docs" / "INTEGRACIONES.md"
    assert doc.exists(), "falta docs/INTEGRACIONES.md"
    txt = doc.read_text(encoding="utf-8")
    for clave in ("CONSOLIDADO_API_KEY", "QBO_REFRESH_TOKEN", "OPERA_BASE_URL"):
        assert clave in txt, f"la documentación no explica {clave}"
