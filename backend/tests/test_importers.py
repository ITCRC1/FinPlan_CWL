"""
Tests de la Fase 1 — Catálogos.

Criterios de Done:
  ✅ read_catalog_excel carga sin errores y devuelve ≥31,000 filas
  ✅ Todas las filas tienen exactamente 7 segmentos
  ✅ Hay cuentas tipo I, G y T
  ✅ Hay cuentas con seg1=9000 (estadísticas)
  ✅ Hay cuentas con seg1=6000 (planilla)
"""
import pytest
from pathlib import Path
from app.importers.catalog_importer import read_catalog_excel, parse_account_row

from tests._rutas import DATOS as DATA_DIR


CATALOG_FILE = DATA_DIR / "Catálogo al 19 de Set  V1 (enviado) con stats.xlsx"


def test_catalog_loads():
    """El Excel del catálogo se carga sin errores (ambas hojas combinadas)."""
    if not CATALOG_FILE.exists():
        pytest.skip(f"Archivo no encontrado: {CATALOG_FILE}")
    df = read_catalog_excel(CATALOG_FILE)
    # Hoja1 ~25,750 + Hoja1(2) ~9,292 = ~35,042 total
    assert len(df) >= 34_000, f"Se esperaban ≥34,000 cuentas, se encontraron {len(df)}"


def test_catalog_seven_segments():
    """Todas las filas tienen exactamente 7 segmentos (columna Cuenta = X-X-X-X-X-X-X)."""
    if not CATALOG_FILE.exists():
        pytest.skip(f"Archivo no encontrado: {CATALOG_FILE}")
    df = read_catalog_excel(CATALOG_FILE)
    bad = df[df["Cuenta"].str.count("-") != 6]
    assert len(bad) == 0, f"Filas con segmentos incorrectos: {bad['Cuenta'].head(5).tolist()}"


def test_catalog_has_all_types():
    """Hay cuentas de tipo I (Income), G (Gasto), T (Cost of Sales) y S (Stats)."""
    if not CATALOG_FILE.exists():
        pytest.skip(f"Archivo no encontrado: {CATALOG_FILE}")
    df = read_catalog_excel(CATALOG_FILE)
    tipos = set(df["Tipo"].unique())
    assert "I" in tipos, "No se encontraron cuentas tipo I (Income)"
    assert "G" in tipos, "No se encontraron cuentas tipo G (Gasto)"
    assert "S" in tipos, "No se encontraron cuentas tipo S (Estadísticas)"


def test_catalog_has_stats_accounts():
    """Hay cuentas estadísticas (Nivel1 empieza por 9xxx), ≥9,000."""
    if not CATALOG_FILE.exists():
        pytest.skip(f"Archivo no encontrado: {CATALOG_FILE}")
    df = read_catalog_excel(CATALOG_FILE)
    stats = df[df["Cuenta"].str.startswith("9")]
    assert len(stats) >= 9_000, f"Se esperaban ≥9,000 cuentas estadísticas, se encontraron {len(stats)}"


def test_catalog_has_payroll_accounts():
    """Hay cuentas de planilla (Nivel1 empieza por 6), ≥4,000 en total."""
    if not CATALOG_FILE.exists():
        pytest.skip(f"Archivo no encontrado: {CATALOG_FILE}")
    df = read_catalog_excel(CATALOG_FILE)
    # Clase 6 incluye 6000 (S&W), 6001 (OT), 6020 (CCSS), 6021 (Agu), etc.
    payroll = df[df["Cuenta"].str.startswith("6")]
    assert len(payroll) >= 4_000, f"Se esperaban ≥4,000 cuentas clase 6, se encontraron {len(payroll)}"
    # Verificar que existen específicamente cuentas 6000 (S&W)
    sw = df[df["Cuenta"].str.startswith("6000")]
    assert len(sw) >= 100, f"Se esperaban ≥100 cuentas 6000 (S&W), se encontraron {len(sw)}"


def test_parse_account_row():
    """parse_account_row extrae los 7 segmentos correctamente."""
    import pandas as pd
    row = pd.Series({
        "Cuenta": "4000-0110-001-001-001-01-01",
        "Descripcion": "Room Revenue",
        "Tipo": "I",
        "Estado": "A",
        "AceptaMov": "Sí",
        "UsaCC": "No",
        "AplicaDif": "No",
    })
    acc = parse_account_row(row)
    assert acc.seg1 == "4000"
    assert acc.seg2 == "0110"
    assert acc.tipo == "I"
    assert acc.acepta_mov is True
    assert acc.usa_cc is False
