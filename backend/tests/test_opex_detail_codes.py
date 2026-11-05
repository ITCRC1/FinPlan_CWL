# -*- coding: utf-8 -*-
"""Bajar el OPEX y subirlo no puede reventar ni mover una linea de lugar.

Owner, 2026-11-05, con la pantalla en rojo: *«baje el excel y lo volvi a
subir»* → «Error: Failed to fetch».

Cuatro palabras que no dicen nada, y detras un IntegrityError: la cuenta 7400
de 0230 bajaba con su linea principal (detalle VACIO) y las diez sub-lineas
`001`…`010` que abre «Abrir las cuentas del catalogo». Al subir, el
correlativo le daba `001` a la vacia por ser la primera y chocaba contra la
que ya traia `001` escrito. Once choques, la peticion moria sin respuesta, y
el navegador no tenia como contarlo.

`opex_entries` tiene `UniqueConstraint(scenario, dept, account, detail_code)`,
asi que esto no es cosmetico: es la diferencia entre que la subida entre o se
caiga entera.
"""
import pytest

from app.api.opex_api import asignar_detail_codes


def fila(dep, cta, det=""):
    return {"dept_code": dep, "account_code": cta, "detail_code": det}


# ─────────────────────── el caso que rompio en produccion ───────────────────
def test_la_linea_principal_mas_sus_sublineas_no_chocan():
    """0230/7400: la principal (vacia) y `001`…`010`. Once filas, once codigos."""
    filas = [fila("0230", "7400")] + [fila("0230", "7400", f"{i:03d}") for i in range(1, 11)]
    codigos = asignar_detail_codes(filas)
    assert len(set(codigos)) == len(codigos), f"codigos repetidos: {codigos}"
    assert codigos == ["", "001", "002", "003", "004", "005",
                       "006", "007", "008", "009", "010"]


def test_la_linea_principal_se_queda_VACIA():
    """Si se le pone `001` se va al final del orden `account_code, detail_code`,
    y la proxima bajada la saca en otra ranura: el monto se ve mudado de fila
    sin que nadie lo haya tocado."""
    assert asignar_detail_codes([fila("0230", "7400")])[0] == ""


def test_el_codigo_que_trae_el_archivo_se_respeta():
    filas = [fila("0120", "7065", "007"), fila("0120", "7065", "003")]
    assert asignar_detail_codes(filas) == ["007", "003"]


# ───────────────────────── las filas nuevas sin codigo ──────────────────────
def test_el_segundo_vacio_toma_correlativo():
    """Alguien agrego una fila a mano y no le puso codigo."""
    filas = [fila("0120", "7065"), fila("0120", "7065")]
    assert asignar_detail_codes(filas) == ["", "001"]


def test_el_correlativo_salta_los_codigos_que_el_archivo_ya_ocupo():
    """`001` y `002` estan tomados mas abajo en el archivo: la fila nueva no
    puede quedarse con uno de ellos aunque venga antes."""
    filas = [fila("0120", "7065"), fila("0120", "7065"),
             fila("0120", "7065", "001"), fila("0120", "7065", "002")]
    codigos = asignar_detail_codes(filas)
    assert codigos == ["", "003", "001", "002"]
    assert len(set(codigos)) == 4


def test_varios_vacios_seguidos_no_chocan_entre_si():
    filas = [fila("0150", "7400") for _ in range(5)]
    codigos = asignar_detail_codes(filas)
    assert codigos == ["", "001", "002", "003", "004"]


# ─────────────────────────────── el aislamiento ─────────────────────────────
def test_cada_cuenta_lleva_su_propia_cuenta():
    """`001` de 7065 y `001` de 7400 son filas distintas: la llave incluye la
    cuenta, asi que no hay choque entre ellas."""
    filas = [fila("0120", "7065"), fila("0120", "7400"),
             fila("0120", "7065"), fila("0120", "7400")]
    assert asignar_detail_codes(filas) == ["", "", "001", "001"]


def test_cada_departamento_lleva_su_propia_cuenta():
    filas = [fila("0120", "7065"), fila("0230", "7065")]
    assert asignar_detail_codes(filas) == ["", ""]


def test_los_espacios_alrededor_no_cuentan():
    filas = [fila("0120", "7065", "  "), fila("0120", "7065", " 001 ")]
    assert asignar_detail_codes(filas) == ["", "001"]


def test_un_detail_code_nulo_vale_lo_mismo_que_vacio():
    filas = [{"dept_code": "0120", "account_code": "7065", "detail_code": None},
             fila("0120", "7065", "001")]
    assert asignar_detail_codes(filas) == ["", "001"]


# ───────────────────────── la propiedad que importa ─────────────────────────
@pytest.mark.parametrize("caso", [
    [fila("0230", "7400")] + [fila("0230", "7400", f"{i:03d}") for i in range(1, 11)],
    [fila("0120", "7065") for _ in range(12)],
    [fila("0120", "7065", "005"), fila("0120", "7065"), fila("0120", "7065"),
     fila("0120", "7065", "001")],
    [fila("0110", "7065"), fila("0110", "7250", "010"), fila("0110", "7250"),
     fila("0110", "7065", "002"), fila("0110", "7065")],
    [],
])
def test_NUNCA_se_repite_un_codigo_dentro_de_la_misma_cuenta(caso):
    """La regla entera en una linea: si dos filas de la misma cuenta salen con
    el mismo codigo, la subida se cae y el usuario ve «Failed to fetch»."""
    codigos = asignar_detail_codes(caso)
    assert len(codigos) == len(caso)
    vistos = set()
    for f, c in zip(caso, codigos):
        llave = (f["dept_code"], f["account_code"], c)
        assert llave not in vistos, f"codigo repetido: {llave}"
        vistos.add(llave)
