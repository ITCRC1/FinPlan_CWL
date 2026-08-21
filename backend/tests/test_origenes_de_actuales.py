# -*- coding: utf-8 -*-
"""La tubería que iguala orígenes distintos: traducir, ver y aterrizar.

**El pedido (owner, 2026-08-14).** Oxígen y Ojochal llevan la contabilidad en
QuickBooks; Corcovado va a traer la suya de un backoffice por API. «Quiero dejar
toda esa infraestructura lista, pero sin desplegar nada.»

**El criterio que se persigue:** conectar un hotel nuevo = cargar sus variables y
su mapeo. **Cero código.** Por eso el puente cuenta-de-allá → cuenta-de-acá es
una tabla y no un `if`.

Estas pruebas cubren la parte que se puede verificar HOY, sin credenciales: todo
de `FilaDeOrigen` para abajo. Los adaptadores —QuickBooks, backoffice— entran
después, cada uno cuando haya con qué probarlo.
"""
from decimal import Decimal

import pytest

from app.origenes import FilaDeOrigen
from app.origenes.traductor import traducir


class ReglaFalsa:
    """Una fila de `mapeo_origen` sin necesitar base."""

    def __init__(self, cuenta, account_code, dept_code="", dept_origen="",
                 outlet="", nombre="", activo=True):
        self.cuenta_origen = cuenta
        self.account_code = account_code
        self.dept_code = dept_code
        self.dept_origen = dept_origen
        self.outlet = outlet
        self.nombre_origen = nombre
        self.activo = activo


# ── La forma de entrada ────────────────────────────────────────────────────

def test_un_mes_invalido_se_rechaza_al_construir():
    """Mejor reventar en la puerta que escribir en la columna equivocada."""
    with pytest.raises(ValueError):
        FilaDeOrigen(cuenta="4000", mes=0, monto=Decimal("1"))
    with pytest.raises(ValueError):
        FilaDeOrigen(cuenta="4000", mes=13, monto=Decimal("1"))


# ── Traducción ─────────────────────────────────────────────────────────────

def test_lo_que_no_tiene_equivalencia_no_entra_pero_se_reporta():
    """La regla que ordena todo el módulo.

    Un import que se traga una cuenta deja un P&L que cuadra consigo mismo y no
    cuadra con la realidad. Es la lección de los 21 departamentos: el total
    seguía dando bien.
    """
    r = traducir(
        [FilaDeOrigen("4000", 1, Decimal("100")),
         FilaDeOrigen("9999", 1, Decimal("40"), nombre="Cuenta nueva de contabilidad")],
        [ReglaFalsa("4000", "4000", "0110")],
    )
    assert len(r["filas"]) == 1
    assert len(r["sin_mapeo"]) == 1
    assert r["sin_mapeo"][0]["cuenta_origen"] == "9999"
    assert r["sin_mapeo"][0]["monto"] == 40.0
    assert r["sin_mapeo"][0]["nombre"] == "Cuenta nueva de contabilidad"


def test_las_faltantes_salen_de_mayor_a_menor():
    """Una cuenta suelta de doce dólares no es lo mismo que una de sesenta mil,
    y fila por fila no se distingue."""
    r = traducir(
        [FilaDeOrigen("A", 1, Decimal("12")),
         FilaDeOrigen("B", 1, Decimal("60000")),
         FilaDeOrigen("C", 1, Decimal("-900"))],
        [],
    )
    assert [x["cuenta_origen"] for x in r["sin_mapeo"]] == ["B", "C", "A"]


def test_una_regla_con_departamento_le_gana_a_la_general():
    """Permite «la 5010 va a Food Cost» y, aparte, «la 5010 del BAR va a
    Beverage», sin duplicar el catálogo entero."""
    r = traducir(
        [FilaDeOrigen("5010", 3, Decimal("50")),
         FilaDeOrigen("5010", 3, Decimal("30"), dept="BAR")],
        [ReglaFalsa("5010", "5010", "0120"),
         ReglaFalsa("5010", "5020", "0120", dept_origen="BAR")],
    )
    destinos = {f["account_code"]: f["mar"] for f in r["filas"]}
    assert destinos["5010"] == Decimal("50")
    assert destinos["5020"] == Decimal("30")


def test_dos_cuentas_del_origen_en_la_misma_de_aca_se_SUMAN():
    """Asignar en vez de acumular perdería una de las dos, en silencio."""
    r = traducir(
        [FilaDeOrigen("5010", 1, Decimal("50")),
         FilaDeOrigen("5011", 1, Decimal("25"))],
        [ReglaFalsa("5010", "5010", "0120"), ReglaFalsa("5011", "5010", "0120")],
    )
    assert len(r["filas"]) == 1
    assert r["filas"][0]["jan"] == Decimal("75")


def test_el_outlet_separa_la_misma_cuenta():
    """El GL de A&B trae la MISMA cuenta una vez por punto de venta. Sin el
    outlet en la llave, se pierde la plata de todos menos uno."""
    r = traducir(
        [FilaDeOrigen("5010", 1, Decimal("50"), outlet="REST"),
         FilaDeOrigen("5010", 1, Decimal("30"), outlet="BAR")],
        [ReglaFalsa("5010", "5010", "0120")],
    )
    assert len(r["filas"]) == 2
    assert sum(f["jan"] for f in r["filas"]) == Decimal("80")


def test_una_regla_apagada_no_mapea():
    """Apagar una regla sin borrarla conserva el historial de por qué se mapeó
    así. Pero apagada tiene que comportarse como si no estuviera."""
    r = traducir([FilaDeOrigen("4000", 1, Decimal("100"))],
                 [ReglaFalsa("4000", "4000", "0110", activo=False)])
    assert r["filas"] == []
    assert r["sin_mapeo"][0]["cuenta_origen"] == "4000"


def test_solo_se_reportan_los_meses_que_llegaron():
    """Es lo que decide qué se reemplaza. Si dijera 1..12 siempre, traer enero
    borraría el resto del año."""
    r = traducir([FilaDeOrigen("4000", 2, Decimal("1")),
                  FilaDeOrigen("4000", 5, Decimal("1"))],
                 [ReglaFalsa("4000", "4000", "0110")])
    assert r["meses"] == [2, 5]


def test_los_montos_no_se_vuelven_float_en_el_camino():
    """Un float acá se arrastra hasta el P&L."""
    r = traducir([FilaDeOrigen("4000", 1, Decimal("0.1")),
                  FilaDeOrigen("4000", 1, Decimal("0.2"))],
                 [ReglaFalsa("4000", "4000", "0110")])
    assert r["filas"][0]["jan"] == Decimal("0.3")
    assert isinstance(r["filas"][0]["jan"], Decimal)


# ── Lo que el módulo promete de sí mismo ───────────────────────────────────

def test_el_mapeo_es_dato_y_no_codigo():
    """Si el puente fuera código, abrir Oxígen sería un desarrollo. Siendo dato,
    es cargar su mapeo. Es el criterio que puso el owner."""
    import io
    import pathlib
    back = pathlib.Path(__file__).resolve().parents[1] / "app"
    src = io.open(back / "origenes" / "traductor.py", encoding="utf-8").read()
    for pista in ("QUICKBOOKS", "quickbooks", "Oxigen", "Ojochal", "OXI", "OJO"):
        assert pista not in src, (
            f"el traductor nombra «{pista}»: el mapeo dejó de ser genérico"
        )


def test_aplicar_se_niega_si_hay_cuentas_sin_mapeo():
    """Y el mensaje tiene que decir qué hacer, no solo que falló."""
    import inspect
    from app.origenes import aterrizaje
    src = inspect.getsource(aterrizaje.aplicar)
    assert "permitir_sin_mapeo" in src
    assert "raise ValueError" in src


def test_solo_se_reemplazan_los_meses_traidos():
    """Traer enero no puede borrar febrero. Se verifica en el código porque el
    daño de equivocarse acá es silencioso: el mes queda en cero y parece dato."""
    import inspect
    from app.origenes import aterrizaje
    src = inspect.getsource(aterrizaje.aplicar)
    assert "cols = [MESES[m - 1] for m in meses]" in src
    assert "for c in cols:" in src
    assert "for m in MESES" not in src, "está tocando los doce meses"
