"""
Importador del catálogo de planilla.

Fuente: 'PLANNING CATALOGO.xlsx'
Hoja 'DATA PAYROLL': cuentas clase 6000-6030 con jerarquía de 7 niveles
Hoja 'Planning': diccionario de niveles (depts, posiciones, categorías)
"""
import pandas as pd
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from app.models.payroll_catalog import PayrollAccount


PAYROLL_CATALOG_FILENAME = "PLANNING CATALOGO.xlsx"
PAYROLL_SHEET = "DATA PAYROLL"
PLANNING_SHEET = "Planning"


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("sí", "si", "yes", "true", "1")


def read_payroll_catalog_excel(filepath: str | Path) -> pd.DataFrame:
    """Lee el Excel del catálogo de planilla y retorna un DataFrame limpio."""
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Catálogo planilla no encontrado: {filepath}")

    # Intentar leer con header en fila 4 (índice 3) como el catálogo general
    df = pd.read_excel(filepath, sheet_name=PAYROLL_SHEET, header=3, dtype=str)

    # Buscar columna de código (debería contener guiones)
    code_col = None
    for col in df.columns:
        sample = df[col].dropna().head(5)
        if any("-" in str(v) for v in sample):
            code_col = col
            break

    if code_col is None:
        # Fallback: releer sin header y buscar manualmente
        df_raw = pd.read_excel(filepath, sheet_name=PAYROLL_SHEET, header=None, dtype=str)
        for i, row in df_raw.iterrows():
            if any(str(v).count("-") >= 4 for v in row.values if pd.notna(v)):
                df = pd.read_excel(filepath, sheet_name=PAYROLL_SHEET, header=i, dtype=str)
                break

    df = df.dropna(how="all")
    # Asegurarnos de que la primera columna tenga los códigos
    df.columns = [str(c).strip() for c in df.columns]
    return df, code_col


def _build_lookup(filepath: Path) -> dict:
    """Lee la hoja Planning y construye un diccionario de descripciones."""
    try:
        df = pd.read_excel(filepath, sheet_name=PLANNING_SHEET, dtype=str)
        # La hoja tiene columnas como: Nivel, Código, Descripción
        lookup = {}
        for _, row in df.iterrows():
            vals = [v for v in row.values if pd.notna(v) and str(v).strip()]
            if len(vals) >= 2:
                code = str(vals[0]).strip()
                desc = str(vals[1]).strip()
                lookup[code] = desc
        return lookup
    except Exception:
        return {}


# Mapeo de código nivel1 → nombre concepto nómina
CONCEPTO_NOMBRES = {
    "6000": "SALARIES AND WAGES",
    "6001": "OVERTIME",
    "6002": "DAYS OFF LAB",
    "6003": "WORKED HOLIDAYS",
    "6004": "DISABILITIES",
    "6010": "COMMISSIONS",
    "6020": "CCSS (26.83%)",
    "6021": "13TH SALARY (AGUINALDO)",
    "6022": "OCCUPATIONAL HAZARDS (INS 1.5%)",
    "6023": "PROVISION VACATIONS",
    "6024": "VACATION TAKEN",
    "6025": "CAFETERIA",
    "6026": "NOTICE AND SEVERANCE",
    "6027": "INCENTIVE BONUS",
    "6028": "HOUSING BENEFIT",
    "6029": "TRANSPORTATION",
    "6030": "OTHER BENEFITS",
}


async def import_payroll_catalog(
    db: AsyncSession,
    data_dir: str | Path,
    truncate: bool = False,
) -> dict:
    """
    Importa el catálogo de planilla a la DB.
    """
    filepath = Path(data_dir) / PAYROLL_CATALOG_FILENAME
    df, code_col = read_payroll_catalog_excel(filepath)

    if truncate:
        await db.execute(delete(PayrollAccount))
        await db.commit()

    accounts = []
    errors = []

    for idx, row in df.iterrows():
        try:
            # Buscar el código de 7 segmentos en la fila
            code_val = None
            for col in df.columns:
                val = str(row.get(col, "")).strip()
                if val.count("-") == 6:
                    code_val = val
                    break

            if not code_val:
                continue

            parts = code_val.split("-")
            if len(parts) != 7:
                continue

            # Descripción: primera columna de texto que no sea el código
            desc = ""
            for col in df.columns:
                val = str(row.get(col, "")).strip()
                if val and val != code_val and not val.replace("-", "").isdigit():
                    desc = val
                    break

            nivel1 = parts[0].strip()
            nivel2 = parts[1].strip()

            acc = PayrollAccount(
                code_full=code_val,
                nivel1=nivel1,
                nivel2=nivel2,
                nivel3=parts[2].strip(),
                nivel4=parts[3].strip(),
                nivel5=parts[4].strip(),
                nivel6=parts[5].strip(),
                nivel7=parts[6].strip(),
                descripcion=desc or code_val,
                tipo="G",
                acepta_mov=True,
                concepto_nombre=CONCEPTO_NOMBRES.get(nivel1),
                dept_nombre=None,
                posicion_nombre=None,
            )
            accounts.append(acc)
        except Exception as e:
            errors.append({"row": idx, "error": str(e)})

    BATCH = 500
    for i in range(0, len(accounts), BATCH):
        batch = accounts[i : i + BATCH]
        for acc in batch:
            existing = await db.get(PayrollAccount, acc.code_full)
            if not existing:
                db.add(acc)
        await db.commit()

    return {
        "imported": len(accounts),
        "errors": len(errors),
        "error_detail": errors[:10],
    }
