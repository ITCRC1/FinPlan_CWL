

# ── Reparto de Rooms a sus hijos (Villas / Residencias) ──────────────────────
from decimal import Decimal as D  # noqa: E402
from app.engine.allocation_calculator import calculate_rooms_distribution  # noqa: E402


def test_rooms_reparte_por_noches_y_netea_cero():
    filas = calculate_rooms_distribution(
        cost_by_account={"7065": D("10000"), "7250": D("5000")},
        nights_by_dept={"0115": D("300"), "0116": D("100")},
    )
    assert sum(f["amount_usd"] for f in filas) == 0, "el asiento tiene que netear cero"
    # 300/400 y 100/400 sobre cada cuenta
    v = {f["account"]: f["amount_usd"] for f in filas if f["target_dept"] == "0115"}
    r = {f["account"]: f["amount_usd"] for f in filas if f["target_dept"] == "0116"}
    assert v["7065"] == D("7500.0000") and r["7065"] == D("2500.0000")
    assert v["7250"] == D("3750.0000") and r["7250"] == D("1250.0000")


def test_rooms_conserva_la_cuenta_del_gasto():
    """El débito al hijo va en la MISMA cuenta; solo el crédito usa la 4999."""
    filas = calculate_rooms_distribution({"7065": D("1000")}, {"0115": D("1")})
    debitos = [f for f in filas if f["amount_usd"] > 0]
    creditos = [f for f in filas if f["amount_usd"] < 0]
    assert all(f["account"] == "7065" for f in debitos)
    assert len(creditos) == 1 and creditos[0]["account"] == "4999"
    assert creditos[0]["target_dept"] == "0110"


def test_rooms_ignora_al_depto_fuente_como_destino():
    """Si Rooms se repartiera a sí mismo el asiento no querría decir nada."""
    filas = calculate_rooms_distribution(
        {"7065": D("1000")}, {"0110": D("900"), "0115": D("100")})
    destinos = {f["target_dept"] for f in filas if f["amount_usd"] > 0}
    assert destinos == {"0115"}


def test_rooms_sin_noches_no_reparte_nada():
    assert calculate_rooms_distribution({"7065": D("1000")}, {}) == []
    assert calculate_rooms_distribution({"7065": D("1000")}, {"0115": D("0")}) == []


def test_rooms_manual_netea_cero_y_credita_a_rooms():
    from app.engine.allocation_calculator import calculate_rooms_manual
    filas = calculate_rooms_manual({"0115": D("8000"), "0116": D("2000")}, "7065")
    assert sum(f["amount_usd"] for f in filas) == 0
    credito = [f for f in filas if f["amount_usd"] < 0]
    assert len(credito) == 1
    assert credito[0]["target_dept"] == "0110" and credito[0]["account"] == "4999"
    assert credito[0]["amount_usd"] == D("-10000.0000")


def test_rooms_manual_ignora_ceros_y_al_propio_rooms():
    from app.engine.allocation_calculator import calculate_rooms_manual
    filas = calculate_rooms_manual(
        {"0110": D("5000"), "0115": D("0"), "0116": D("300")}, "7065")
    destinos = {f["target_dept"] for f in filas if f["amount_usd"] > 0}
    assert destinos == {"0116"}


def test_rooms_manual_sin_montos_no_arma_asiento():
    from app.engine.allocation_calculator import calculate_rooms_manual
    assert calculate_rooms_manual({}, "7065") == []
    assert calculate_rooms_manual({"0115": D("0")}, "7065") == []


def test_rooms_por_posicion_lleva_todo_el_gasto_y_netea_cero():
    """La posición se lleva sus 17 conceptos, cada uno en su cuenta."""
    from app.engine.allocation_calculator import calculate_rooms_by_position
    filas = calculate_rooms_by_position({
        "0115": {"6000": D("3000"), "6020": D("805"), "6021": D("250")},
        "0116": {"6000": D("1000"), "6020": D("268")},
    })
    assert sum(f["amount_usd"] for f in filas) == 0
    # cada concepto conserva su cuenta en el destino
    v = {f["account"] for f in filas if f["target_dept"] == "0115"}
    assert v == {"6000", "6020", "6021"}
    credito = [f for f in filas if f["amount_usd"] < 0][0]
    assert credito["target_dept"] == "0110" and credito["account"] == "4999"
    assert credito["amount_usd"] == D("-5323.0000")


def test_rooms_por_posicion_no_se_reparte_a_si_mismo():
    from app.engine.allocation_calculator import calculate_rooms_by_position
    filas = calculate_rooms_by_position({"0110": {"6000": D("999")}, "0115": {"6000": D("100")}})
    assert {f["target_dept"] for f in filas if f["amount_usd"] > 0} == {"0115"}


def test_rooms_por_posicion_sin_posiciones_no_arma_asiento():
    from app.engine.allocation_calculator import calculate_rooms_by_position
    assert calculate_rooms_by_position({}) == []
    assert calculate_rooms_by_position({"0115": {"6000": D("0")}}) == []


def test_rooms_pct_por_set_arrastra_todo_el_gasto():
    """El % se aplica a TODAS las cuentas que llegaron a Rooms."""
    from app.engine.allocation_calculator import calculate_rooms_by_pct
    cargado = {"6000": D("3000"), "6020": D("805"), "6021": D("250")}
    filas, fte, avisos = calculate_rooms_by_pct(
        cargado, {"0115": D("0.30"), "0116": D("0.10")})
    assert avisos == []
    assert sum(f["amount_usd"] for f in filas) == 0
    v = {f["account"]: f["amount_usd"] for f in filas if f["target_dept"] == "0115"}
    assert v["6000"] == D("900.0000")     # 30% del salario
    assert v["6020"] == D("241.5000")     # 30% de la CCSS — el % arrastra todo
    r = {f["account"]: f["amount_usd"] for f in filas if f["target_dept"] == "0116"}
    assert r["6000"] == D("300.0000")


def test_rooms_pct_lo_no_asignado_se_queda_en_rooms():
    """Rooms es el residuo: con 40% asignado, el 60% no se mueve."""
    from app.engine.allocation_calculator import calculate_rooms_by_pct
    filas, _f, _a = calculate_rooms_by_pct(
        {"6000": D("1000")}, {"0115": D("0.30"), "0116": D("0.10")})
    credito = [f for f in filas if f["amount_usd"] < 0][0]
    assert credito["amount_usd"] == D("-400.0000")


def test_rooms_pct_no_deja_repartir_mas_del_cien():
    from app.engine.allocation_calculator import calculate_rooms_by_pct
    filas, _f, avisos = calculate_rooms_by_pct(
        {"6000": D("1000")}, {"0115": D("0.7"), "0116": D("0.5")})
    assert filas == []
    assert avisos and "100%" in avisos[0]


def test_el_fte_viaja_con_el_costo():
    """Si Villas se lleva 30% del costo, se lleva 30% del FTE.

    Como el reparto corre AL FINAL, esto no alimenta a la cafetería —esa ya se
    repartió y viene incluida en lo que llegó a Rooms—. El FTE viaja para poder
    leer costo por FTE en Villas.
    """
    from app.engine.allocation_calculator import calculate_rooms_by_pct
    _filas, fte, _avisos = calculate_rooms_by_pct(
        {"6000": D("1000")}, {"0115": D("0.30"), "0116": D("0.10")}, fte=D("1"))
    assert fte["0115"] == D("0.30")
    assert fte["0116"] == D("0.10")
    # el 60% restante se queda en Rooms: no aparece como destino
    assert "0110" not in fte
