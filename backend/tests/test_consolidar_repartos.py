"""
Regresión: el recálculo reventaba cuando dos reglas de Salary Allocation caían
en el mismo departamento / mes / cuenta.

Desde que Salary Allocation es 1 regla = 1 destino (migración 080) eso pasa
todo el tiempo: el guía y el capitán apoyan los dos a Transportation, y un
departamento puede entregar y recibir a la vez. Cada regla emitía su fila, la
unique `uq_allocation_entry` rechazaba la segunda y la transacción se revertía
ENTERA — el usuario apretaba Aplicar, veía "Failed to fetch" y los repartos
viejos seguían en pie sin ningún aviso.

Run: pytest tests/test_consolidar_repartos.py -v
"""
from decimal import Decimal

from app.engine.recalculate import _consolidar_repartos
from app.models.allocation_entry import AllocationEntry


def fila(destino, monto, base=Decimal("0"), base_tipo="FTE", origen="0150",
         cuenta="6000", mes=1):
    return AllocationEntry(
        scenario_id="s1", allocation_type="SALARY", month=mes, year=2027,
        source_dept=origen, target_dept=destino, amount_usd=Decimal(str(monto)),
        basis_value=base, basis_type=base_tipo, account=cuenta,
    )


def llave(e):
    """La unique de la tabla (sin scenario_id, constante en cada recálculo)."""
    return (e.allocation_type, e.month, e.target_dept, e.account, e.basis_type)


def test_dos_reglas_al_mismo_destino_se_suman():
    """Guía y capitán apoyan los dos a Transportation: una sola fila, monto sumado."""
    juntas = _consolidar_repartos([
        fila("0152", "14713.49", base=Decimal("2")),
        fila("0152", "12143.24", base=Decimal("2")),
    ])
    assert len(juntas) == 1
    assert juntas[0].amount_usd == Decimal("26856.73")


def test_no_quedan_llaves_repetidas():
    """Ninguna fila puede chocar contra uq_allocation_entry."""
    juntas = _consolidar_repartos([
        fila("0152", "100"), fila("0152", "200"), fila("0183", "300"),
        fila("0183", "50", origen="0200"), fila("0150", "-650", base_tipo="CREDIT"),
    ])
    claves = [llave(e) for e in juntas]
    assert len(claves) == len(set(claves))


def test_cargo_y_credito_del_mismo_depto_no_se_mezclan():
    """0150 entrega el salario de sus guías y recibe parte de Property Support.
    Son dos hechos distintos: se guardan separados (por eso basis_type entró a
    la unique en la migración 081)."""
    juntas = _consolidar_repartos([
        fila("0150", "5917.78", base=Decimal("13"), origen="0200"),
        fila("0150", "-53713.45", base_tipo="CREDIT"),
    ])
    assert len(juntas) == 2
    por_base = {e.basis_type: e.amount_usd for e in juntas}
    assert por_base["FTE"] == Decimal("5917.78")
    assert por_base["CREDIT"] == Decimal("-53713.45")


def test_la_base_no_se_suma():
    """basis_value es el FTE del departamento destino: el mismo para todas las
    filas que comparten llave. Sumarlo lo duplicaría."""
    juntas = _consolidar_repartos([
        fila("0152", "100", base=Decimal("2")),
        fila("0152", "200", base=Decimal("2")),
    ])
    assert juntas[0].basis_value == Decimal("2")


def test_origen_de_varias_fuentes_queda_marcado():
    """El P&L rutea por el destino; el origen es informativo, y mentir sobre él
    sería peor que decir que vino de varios lados."""
    juntas = _consolidar_repartos([
        fila("0183", "100", origen="0150"),
        fila("0183", "200", origen="0200"),
    ])
    assert juntas[0].source_dept == "VARIOS"


def test_una_sola_fuente_conserva_su_origen():
    juntas = _consolidar_repartos([
        fila("0183", "100", origen="0150"),
        fila("0183", "200", origen="0150"),
    ])
    assert juntas[0].source_dept == "0150"


def test_el_total_no_cambia_y_sigue_neteando_cero():
    """Consolidar mueve filas, no plata."""
    filas = [
        fila("0183", "50005.68", base=Decimal("3")),
        fila("0152", "32600.45", base=Decimal("2")),
        fila("0220", "15138.48", base=Decimal("5"), origen="0113"),
        fila("0150", "5917.78", base=Decimal("13"), origen="0200"),
        fila("0150", "-53713.45", base_tipo="CREDIT"),
        fila("0152", "-17405.23", base_tipo="CREDIT", origen="0152"),
        fila("0200", "-17405.23", base_tipo="CREDIT", origen="0200"),
        fila("0113", "-15138.48", base_tipo="CREDIT", origen="0113"),
    ]
    antes = sum(e.amount_usd for e in filas)
    juntas = _consolidar_repartos(filas)
    assert sum(e.amount_usd for e in juntas) == antes == Decimal("0.00")


def test_meses_y_cuentas_distintas_no_se_mezclan():
    """Cafetería (6025) y lavandería (7310) del mismo depto son cargos distintos,
    y enero no se mezcla con febrero."""
    juntas = _consolidar_repartos([
        fila("0110", "100", cuenta="6025", mes=1),
        fila("0110", "100", cuenta="7310", mes=1),
        fila("0110", "100", cuenta="6025", mes=2),
    ])
    assert len(juntas) == 3
