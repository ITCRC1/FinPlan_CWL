# -*- coding: utf-8 -*-
"""La auditoria del detalle del mayor: que senala y, sobre todo, que NO senala.

Owner, 2026-10-05: *«necesito una herramienta de revision… que genere un reporte
de discrepancias para yo poder empezar a revisar»*.

La mitad de estas pruebas son de SILENCIO. Una herramienta de revision que
avisa de mas no se usa: la primera version saco 1.047 hallazgos sobre 8.852
lineas y era inservible. Lo que la hace util es que calla cuando el reparto es
deliberado.
"""
import pytest

from app.engine import auditoria_gl as A


class L:
    """Una linea de asiento, lo minimo que las reglas miran."""

    def __init__(self, cuenta, ref="", num_doc="", monto=1000.0, desc="", origen="CXP"):
        p = cuenta.split("-")
        self.cuenta, self.seg1, self.seg2, self.seg3 = cuenta, p[0], p[1], p[2]
        self.referencia, self.num_doc = ref, num_doc
        self.descripcion, self.origen = desc, origen
        self.asiento, self.linea, self.fecha = "1", "1", "01/09/26"
        self._m = monto

    clase = property(lambda s: s.seg1[0])
    monto_crc = property(lambda s: s._m)
    monto_usd = property(lambda s: s._m / 500)


def reglas(hallazgos):
    return {h.regla for h in hallazgos}


def por_cuenta(hallazgos):
    return {h.cuenta: h for h in hallazgos}


# ───────────────────── el articulo contra la cuenta ─────────────────────
def test_un_articulo_que_cruza_de_clase_se_senala():
    """Jabon en polvo: 12 lineas de gasto y 6 de costo de comida."""
    ls = ([L("7400-0161-800-000-000-00-00", "Jabon En Polvo") for _ in range(12)]
          + [L("5420-0220-000-000-000-00-00", "Jabon En Polvo") for _ in range(6)])
    r = A.revisar(ls)
    assert reglas(r.hallazgos) == {"ARTICULO_CRUZA_CLASE"}
    h, = r.hallazgos
    assert h.cuenta.startswith("5420"), "se senala la MINORIA, no la mayoria"
    assert h.severidad == A.ALTA
    assert h.sugerencia == "7400-0161"
    assert h.n_lineas == 6


def test_la_dominancia_se_mide_por_clase_y_no_por_cuenta():
    """⚠️ Regresion. «White C Comercial» —un producto de limpieza— tenia 6 lineas
    en 5420 (costo de comida) y 21 repartidas en siete cuentas 7xxx de
    suministros. Midiendo por CUENTA ganaba 5420 con 6 contra 3, y la
    herramienta recomendaba mandar la limpieza al costo de comida: siete avisos,
    todos al reves. Por CLASE gana el gasto 21 a 6, que es lo correcto."""
    ls = [L("5420-0220-000-000-000-00-00", "White C") for _ in range(6)]
    for d in ("0110", "0120", "0140", "0161", "0200", "0230", "0152"):
        ls += [L("7400-{}-800-000-000-00-00".format(d), "White C") for _ in range(3)]
    r = A.revisar(ls)
    assert len(r.hallazgos) == 1, "un aviso sobre la minoria, no uno por cuenta"
    h, = r.hallazgos
    assert h.cuenta.startswith("5420")
    assert not h.sugerencia.startswith("5420")


def test_un_reparto_parejo_dentro_de_la_misma_clase_no_se_senala():
    """Huevos al restaurante (5101) y al comedor de empleados (5420) es a
    proposito. Avisarlo convierte el reporte en ruido."""
    ls = ([L("5101-0120-000-000-000-00-00", "Huevos") for _ in range(24)]
          + [L("5420-0220-000-000-000-00-00", "Huevos") for _ in range(21)])
    assert A.revisar(ls).hallazgos == []


def test_un_reparto_desparejo_dentro_de_la_misma_clase_si_se_senala():
    ls = ([L("5101-0120-000-000-000-00-00", "Tomate") for _ in range(30)]
          + [L("5150-0120-000-000-000-00-00", "Tomate") for _ in range(2)])
    r = A.revisar(ls)
    assert reglas(r.hallazgos) == {"ARTICULO_EN_VARIAS_CUENTAS"}
    h, = r.hallazgos
    assert h.cuenta.startswith("5150") and h.severidad == A.MEDIA


def test_partido_al_medio_entre_clases_senala_los_dos_lados_sin_sugerencia():
    """Lavaplatos liquido: 9 y 9, por el mismo monto. Inventar un ganador seria
    mandar al owner a mover la mitad correcta."""
    ls = ([L("7140-0120-800-000-000-00-00", "Lavaplatos", monto=100.0) for _ in range(9)]
          + [L("5420-0220-000-000-000-00-00", "Lavaplatos", monto=100.0) for _ in range(9)])
    r = A.revisar(ls)
    assert len(r.hallazgos) == 2
    assert all(h.severidad == A.ALTA and not h.sugerencia for h in r.hallazgos)
    assert all("decidir" in h.porque for h in r.hallazgos)


def test_un_articulo_en_una_sola_cuenta_no_dice_nada():
    assert A.revisar([L("5101-0120-000-000-000-00-00", "Aguacate")
                      for _ in range(9)]).hallazgos == []


# ───────────────────── la cuenta contra el departamento ─────────────────────
def test_costo_de_ventas_en_un_departamento_que_no_vende():
    r = A.revisar([L("5101-0110-000-000-000-00-00", "Lo que sea")])
    assert reglas(r.hallazgos) == {"COSTO_EN_DEPTO_SIN_COSTO"}
    assert r.hallazgos[0].severidad == A.ALTA


@pytest.mark.parametrize("dept", sorted(A.SIN_COSTO_DE_VENTAS))
def test_ningun_departamento_de_overhead_puede_tener_clase_5(dept):
    ls = [L("5101-{}-000-000-000-00-00".format(dept), "x")]
    assert "COSTO_EN_DEPTO_SIN_COSTO" in reglas(A.revisar(ls).hallazgos)


def test_costo_de_ventas_donde_si_corresponde_no_dice_nada():
    assert A.revisar([L("5101-0120-000-000-000-00-00", "Aguacate")]).hallazgos == []


# ───────────────────────────── planilla ─────────────────────────────
def test_el_rotulo_del_departamento_que_no_coincide_con_la_cuenta():
    """El caso que el owner cazo a mano en agosto: planilla del comedor de
    empleados (0220) rotulada FRONT DESK."""
    ls = ([L("6000-0220-500-013-015-00-00", "COCINERO", "EMPLOYEE DINING")
           for _ in range(20)]
          + [L("6000-0220-500-013-015-00-00", "COCINERO", "FRONT DESK")])
    r = A.revisar(ls)
    assert reglas(r.hallazgos) == {"PLANILLA_DEPTO_NO_COINCIDE"}
    h, = r.hallazgos
    assert h.severidad == A.ALTA and h.sugerencia == "EMPLOYEE DINING"


def test_un_puesto_con_dos_nombres():
    ls = ([L("6000-0111-501-013-015-00-00", "AGENTE DE RECEPCION", "FRONT DESK")
           for _ in range(10)]
          + [L("6000-0111-501-013-015-00-00", "RECEPCIONISTA", "FRONT DESK")])
    assert "PLANILLA_PUESTO_NO_COINCIDE" in reglas(A.revisar(ls).hallazgos)


def test_planilla_coherente_no_dice_nada():
    ls = [L("6000-0111-501-013-015-00-00", "AGENTE DE RECEPCION", "FRONT DESK")
          for _ in range(10)]
    assert A.revisar(ls).hallazgos == []


# ───────────────────────── reglas del P&L ─────────────────────────
def test_la_4999_tiene_que_netear_a_cero():
    ls = [L("4999-0220-000-000-000-00-00", monto=100.0),
          L("4999-0110-000-000-000-00-00", monto=-60.0)]
    assert "ALLOCATION_NO_NETEA" in reglas(A.revisar(ls).hallazgos)


def test_la_4999_cuadrada_no_dice_nada():
    ls = [L("4999-0220-000-000-000-00-00", monto=100.0),
          L("4999-0110-000-000-000-00-00", monto=-100.0)]
    assert "ALLOCATION_NO_NETEA" not in reglas(A.revisar(ls).hallazgos)


def test_la_cuenta_de_cajon_se_reporta_agrupada_por_departamento():
    ls = [L("7380-0180-800-000-000-00-00", "varios") for _ in range(84)]
    r = A.revisar(ls)
    assert reglas(r.hallazgos) == {"CUENTA_GENERICA"}
    h, = r.hallazgos
    assert h.n_lineas == 84 and h.severidad == A.BAJA, "84 lineas, UN renglon"


# ───────────────────────────── el alcance ─────────────────────────────
def test_el_balance_queda_fuera():
    """«Las cuentas que empiezan con 4 en adelante»: caja y bancos no se revisan."""
    ls = [L("1000-0001-001-024-001-00-00", "PAYMENT CASH") for _ in range(5)]
    r = A.revisar(ls)
    assert r.lineas_revisadas == 0 and r.hallazgos == []


def test_el_resumen_cuenta_casos_y_lineas_por_separado():
    """Un caso puede traer muchas lineas: el owner necesita los dos numeros."""
    ls = ([L("7400-0161-800-000-000-00-00", "Jabon") for _ in range(12)]
          + [L("5420-0220-000-000-000-00-00", "Jabon") for _ in range(6)])
    r = A.revisar(ls)
    assert len(r.hallazgos) == 1
    assert r.lineas_senaladas == 6
    assert r.por_severidad == {A.ALTA: 1}


def test_los_hallazgos_salen_ordenados_por_severidad_y_monto():
    ls = ([L("7380-0180-800-000-000-00-00", "cajon", monto=5.0)]
          + [L("5101-0110-000-000-000-00-00", "costo raro", monto=900.0)]
          + [L("5101-0110-000-000-000-00-00", "costo raro2", monto=100.0)])
    r = A.revisar(ls)
    sev = [h.severidad for h in r.hallazgos]
    assert sev == sorted(sev, key=lambda s: A._ORDEN[s])
    altas = [h.monto_crc for h in r.hallazgos if h.severidad == A.ALTA]
    assert altas == sorted(altas, key=lambda m: -abs(m))


def test_cada_hallazgo_trae_la_evidencia_para_ir_a_buscarla():
    """Sin numero de asiento el reporte no se puede usar contra Integrity."""
    ls = ([L("7400-0161-800-000-000-00-00", "Jabon") for _ in range(12)]
          + [L("5420-0220-000-000-000-00-00", "Jabon") for _ in range(6)])
    h, = A.revisar(ls).hallazgos
    assert len(h.lineas) == 6
    assert set(h.lineas[0]) >= {"asiento", "linea", "fecha", "cuenta", "referencia",
                                "monto_crc", "monto_usd"}
