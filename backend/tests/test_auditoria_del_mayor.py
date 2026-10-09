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


# ──────────────── producto de carta en la comida del personal ────────────────
def test_un_producto_premium_en_el_comedor_de_empleados_se_senala():
    """Owner, 2026-10-05: «errores que metan productos premium en employees food
    y que deberian ser food cost de restaurantes». En setiembre eran filete de
    congrio, filete de pargo y bistec de res: CRC 2.887.278."""
    ls = [L("5420-0220-000-000-000-00-00", "FILET DE CONGRIO", monto=85_750.0)
          for _ in range(9)]
    r = A.revisar(ls)
    assert reglas(r.hallazgos) == {"PREMIUM_EN_COMIDA_DE_EMPLEADOS"}
    h, = r.hallazgos
    assert h.severidad == A.ALTA and h.sugerencia.startswith("5101")
    assert h.n_lineas == 9 and h.grupo == "Costos"


def test_la_comida_normal_del_personal_no_se_senala():
    """Arroz, huevos y repollo son exactamente lo que va ahi."""
    ls = ([L("5420-0220-000-000-000-00-00", "ARROZ 95 GRANEL", monto=79_308.0)
           for _ in range(9)]
          + [L("5420-0220-000-000-000-00-00", "REPOLLO VERDE") for _ in range(24)])
    assert A.revisar(ls).hallazgos == []


def test_el_mismo_producto_premium_en_el_restaurante_no_dice_nada():
    """Un filete en 5101 esta en su lugar: la regla mira SOLO el comedor."""
    ls = [L("5101-0120-000-000-000-00-00", "FILET DE CONGRIO") for _ in range(9)]
    assert "PREMIUM_EN_COMIDA_DE_EMPLEADOS" not in reglas(A.revisar(ls).hallazgos)


@pytest.mark.parametrize("articulo", ["Filete pargo", "FILET DE CONGRIO",
                                      "RES BISTEC EL ARREO", "Lomito", "Camaron jumbo"])
def test_las_palabras_premium_que_aparecieron_en_setiembre(articulo):
    ls = [L("5420-0220-000-000-000-00-00", articulo)]
    assert "PREMIUM_EN_COMIDA_DE_EMPLEADOS" in reglas(A.revisar(ls).hallazgos)


# ──────────────── un puesto en un departamento que no es el suyo ────────────────
def test_un_puesto_cargado_a_dos_departamentos():
    """Owner, 2026-10-05: «en las cuentas de payroll 6, posiciones que no
    corresponden al departamento». En setiembre «COCINERO B» tenia 42 lineas en
    Kitchen (CRC 16,2 M) y 42 en Employee Dining (CRC 6,4 M)."""
    ls = ([L("6000-0122-500-013-015-00-00", "COCINERO B", "KITCHEN", monto=387_690.0)
           for _ in range(42)]
          + [L("6000-0220-500-013-015-00-00", "COCINERO B", "EMPLOYEE DINING",
               monto=152_206.0) for _ in range(42)])
    r = A.revisar(ls)
    assert "PUESTO_EN_VARIOS_DEPARTAMENTOS" in reglas(r.hallazgos)
    h = [x for x in r.hallazgos if x.regla == "PUESTO_EN_VARIOS_DEPARTAMENTOS"][0]
    assert h.dept == "0220", "a igual cantidad de lineas se senala el de MENOS plata"
    assert h.sugerencia == "0122" and h.grupo == "Planilla"


def test_un_puesto_en_un_solo_departamento_no_dice_nada():
    ls = [L("6000-0122-500-013-015-00-00", "COCINERO B", "KITCHEN") for _ in range(42)]
    assert "PUESTO_EN_VARIOS_DEPARTAMENTOS" not in reglas(A.revisar(ls).hallazgos)


# ─────────────────────── el corte por tipo de cuenta ───────────────────────
def test_cada_hallazgo_sabe_a_que_tipo_de_cuenta_pertenece():
    """Owner, 2026-10-05: «me gustaria tener las discrepancias por tipo de
    cuenta. Costos empieza con 5, payroll 6, Opex 7 y property expenses 8»."""
    assert A.grupo_de("5101-0120-000-000-000-00-00") == "Costos"
    assert A.grupo_de("6000-0111-501-013-015-00-00") == "Planilla"
    assert A.grupo_de("7380-0180-800-000-000-00-00") == "Opex"
    assert A.grupo_de("8000-0250-000-000-000-00-00") == "Gastos de propiedad"
    assert A.grupo_de("4999-0220-000-000-000-00-00") == "Ingresos"


def test_el_resumen_por_tipo_cuenta_casos_lineas_y_plata():
    ls = ([L("5420-0220-000-000-000-00-00", "FILETE PARGO", monto=100.0)
           for _ in range(3)]
          + [L("7380-0180-800-000-000-00-00", "varios", monto=50.0) for _ in range(4)])
    r = A.revisar(ls)
    assert r.por_grupo["Costos"] == {"casos": 1, "lineas": 3, "monto_crc": 300.0,
                                     "alta": 1}
    assert r.por_grupo["Opex"]["casos"] == 1 and r.por_grupo["Opex"]["lineas"] == 4


def test_un_tipo_sin_hallazgos_no_aparece_en_el_resumen():
    """Una pestana vacia se lee como «no revise esto», cuando dice «salio limpio»."""
    r = A.revisar([L("5420-0220-000-000-000-00-00", "FILETE PARGO")])
    assert list(r.por_grupo) == ["Costos"]


def test_los_hallazgos_salen_agrupados_por_tipo():
    """El Excel y la pantalla leen la misma lista: tiene que venir ordenada."""
    ls = ([L("7380-0180-800-000-000-00-00", "varios") for _ in range(4)]
          + [L("5420-0220-000-000-000-00-00", "FILETE PARGO") for _ in range(3)])
    grupos = [h.grupo for h in A.revisar(ls).hallazgos]
    assert grupos == sorted(grupos, key=lambda g: A.ORDEN_GRUPOS.index(g))


# ───────────────── el PROVEEDOR contra la cuenta ─────────────────
#
# Es la otra mitad de «el articulo contra la cuenta», y hacia falta porque son
# campos distintos: `referencia` es el ARTICULO —«DIESEL», «CAMBIO DE LLANTA»—
# y `descripcion` es el PROVEEDOR. Un gasto mal clasificado suele traer un
# articulo que aparece una sola vez en el mes, asi que no agrupa con nada y
# solo se ve mirando quien cobro.

def test_el_proveedor_con_cuenta_habitual_y_una_rama_chica_se_senala():
    """Medido en produccion: SERVICENTRO LA PALMA, 20 lineas en combustible y 2
    en reparacion de vehiculos. Los articulos de esas 2 —«CAMBIO DE LLANTA»,
    «NEUMATICO UNIVERSAL»— aparecen una sola vez en el mes, asi que ninguna otra
    regla los ve."""
    ls = ([L("7395-0210-800-000-000-00-00", "Diesel",
             desc="SERVICENTRO LA PALMA S A") for _ in range(20)]
          + [L("7700-0200-800-000-000-00-00", "Cambio De Llanta",
               desc="SERVICENTRO LA PALMA S A"),
             L("7700-0200-800-000-000-00-00", "Neumatico Universal",
               desc="SERVICENTRO LA PALMA S A")])
    h = A._proveedor_en_cuenta_inusual(ls)
    assert len(h) == 1
    assert h[0].cuenta.startswith("7700-0200")
    assert h[0].sugerencia == "7395-0210"
    assert "20 de 22" in h[0].porque


def test_un_proveedor_repartido_PAREJO_no_se_avisa():
    """⚠️ El silencio que hace que la regla se use.

    Un proveedor de comida que vende al restaurante y al comedor de empleados
    esta en las dos cuentas a proposito. Sin cuenta habitual clara no hay nada
    que sospechar."""
    ls = ([L("5101-0120-000-000-000-00-00", desc="VERDULERIA EL SOL")
           for _ in range(12)]
          + [L("5420-0220-000-000-000-00-00", desc="VERDULERIA EL SOL")
             for _ in range(8)])
    assert A._proveedor_en_cuenta_inusual(ls) == []


def test_la_planilla_NO_entra_en_la_regla_del_proveedor():
    """⚠️ Sin esto la regla se ahoga y tapa todo lo demas.

    «ORDINARIO» y «C C S S» caen en los 17 departamentos a proposito, y son los
    montos mas grandes del mes: en setiembre 2026 el salario ordinario suma
    decenas de millones repartidos. Incluirlos daba los casos mas grandes del
    mes y todos falsos."""
    ls = ([L("6000-0150-000-000-000-00-00", desc="ORDINARIO", monto=5_752_220)
           for _ in range(8)]
          + [L("6000-0220-000-000-000-00-00", desc="ORDINARIO", monto=1_455_153)])
    assert A._proveedor_en_cuenta_inusual(ls) == []
    # Y tampoco si alguien escribiera un concepto de planilla en clase 7.
    ls2 = ([L("7400-0150-800-000-000-00-00", desc="DISTRIBUCION GASTO CAFETERIA")
            for _ in range(8)]
           + [L("7400-0220-800-000-000-00-00", desc="DISTRIBUCION GASTO CAFETERIA")])
    assert A._proveedor_en_cuenta_inusual(ls2) == []


def test_el_numero_de_factura_no_parte_al_proveedor_en_pedazos():
    """Sin quitar los digitos, cada factura seria un proveedor distinto y la
    regla no veria nada."""
    assert (A._proveedor("FERRETERIA EL COLONO FACT 44821")
            == A._proveedor("Ferreteria El Colono  fact-9930"))
    assert A._proveedor("ICE Telecomunicaciones") == "ICE TELECOMUNICACIONES"
    # Un texto que solo trae numeros no es un proveedor.
    assert A._proveedor("12345-678") == ""


def test_la_regla_del_proveedor_esta_registrada_y_explicada():
    """Una regla sin explicacion en el cuadro se lee como un reproche sin causa:
    el owner tiene que poder decirle al gerente por que se le pregunta."""
    from app.export.auditoria_gl_xlsx import QUE_MIRA

    assert A._proveedor_en_cuenta_inusual in A.REGLAS
    assert "PROVEEDOR_EN_CUENTA_INUSUAL" in QUE_MIRA
    # Y la explicacion dice en que se diferencia de la del articulo, que es la
    # pregunta que va a hacer quien vea las dos juntas.
    texto = QUE_MIRA["PROVEEDOR_EN_CUENTA_INUSUAL"]
    assert "ARTICULO_EN_VARIAS_CUENTAS" in texto
