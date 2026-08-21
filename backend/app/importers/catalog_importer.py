"""
Importador del catálogo de cuentas USALI.

Fuente: 'Catálogo al 19 de Set  V1 (enviado) con stats.xlsx'
Hojas:
  - 'Hoja1':    cuentas operativas (clases 1-8), header en fila 5 (índice 5)
  - 'Hoja1 (2)': cuentas estadísticas (clase 9), mismo formato

Columnas reales: Nivel1, Nivel2, Nivel3, Nivel4, Nivel5, NIvel6, Nivel7, Descripcion
El tipo (I/G/T/S) se infiere de Nivel1.
"""
import pandas as pd
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from app.models.account import Account


CATALOG_FILENAME = "Catálogo al 19 de Set  V1 (enviado) con stats.xlsx"
SHEET_MAIN = "Hoja1"
SHEET_STATS = "Hoja1 (2)"
HEADER_ROW = 5   # índice 0-based de la fila con los nombres de columna


def _infer_tipo(nivel1: str) -> str:
    """Infiere el tipo contable desde el primer nivel de cuenta."""
    if nivel1.startswith("4"):
        return "I"   # Income
    if nivel1.startswith("5"):
        return "T"   # Cost of Sales
    if nivel1.startswith("9"):
        return "S"   # Estadísticas
    return "G"       # Gasto (6xxx, 7xxx, 8xxx, y balance 1-3xxx)


def _read_sheet(filepath: Path, sheet_name: str) -> pd.DataFrame:
    """Lee una hoja del catálogo y retorna un DataFrame normalizado."""
    df = pd.read_excel(filepath, sheet_name=sheet_name, header=HEADER_ROW, dtype=str)
    df = df.dropna(axis=1, how="all")
    # Normalizar nombre de columna NIvel6 → Nivel6
    df.columns = [c.strip().replace("NIvel6", "Nivel6").replace("NIvel7", "Nivel7")
                  for c in df.columns]
    df = df.dropna(subset=["Nivel1"])
    df = df[df["Nivel1"].str.strip().str.match(r"^\d+$", na=False)]
    df = df.reset_index(drop=True)
    return df


def read_catalog_excel(filepath: str | Path) -> pd.DataFrame:
    """
    Lee ambas hojas del catálogo (operativa + estadística) y las combina.
    Retorna un DataFrame unificado con columna 'Cuenta' en formato segmentado.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Catálogo no encontrado: {filepath}")

    df_main = _read_sheet(filepath, SHEET_MAIN)
    df_stats = _read_sheet(filepath, SHEET_STATS)
    df = pd.concat([df_main, df_stats], ignore_index=True)

    # Construir código completo y normalizar columnas para compatibilidad
    def build_code(row):
        segs = [str(row.get(f"Nivel{i}", "")).strip() for i in range(1, 8)]
        return "-".join(segs)

    df["Cuenta"] = df.apply(build_code, axis=1)
    df["Tipo"] = df["Nivel1"].apply(_infer_tipo)
    df["Descripcion"] = df["Descripcion"].fillna("").str.strip()
    df["Estado"] = "A"
    df["AceptaMov"] = True
    df["UsaCC"] = False
    df["AplicaDif"] = False

    return df


def parse_account_row(row: pd.Series) -> Account:
    """Convierte una fila del DataFrame en un objeto Account."""
    code = str(row["Cuenta"]).strip()
    parts = code.split("-")
    if len(parts) != 7:
        raise ValueError(f"Código inválido (esperaba 7 segmentos): '{code}'")

    return Account(
        code_full=code,
        seg1=parts[0].strip(),
        seg2=parts[1].strip(),
        seg3=parts[2].strip(),
        seg4=parts[3].strip(),
        seg5=parts[4].strip(),
        seg6=parts[5].strip(),
        seg7=parts[6].strip(),
        descripcion=str(row["Descripcion"]).strip(),
        tipo=str(row["Tipo"]).strip(),
        estado="A",
        acepta_mov=True,
        usa_cc=False,
        aplica_diferencial=False,
        link_id=None,
    )


async def import_catalog(
    db: AsyncSession,
    data_dir: str | Path,
    truncate: bool = False,
) -> dict:
    """
    Importa el catálogo de cuentas a la DB.

    Args:
        db: sesión async de SQLAlchemy
        data_dir: directorio raíz donde vive el Excel (C:/FinPlan_CWL)
        truncate: si True, borra todas las cuentas antes de importar
    """
    filepath = Path(data_dir) / CATALOG_FILENAME
    df = read_catalog_excel(filepath)

    if truncate:
        await db.execute(delete(Account))
        await db.commit()

    accounts = []
    errors = []
    for idx, row in df.iterrows():
        try:
            acc = parse_account_row(row)
            accounts.append(acc)
        except ValueError as e:
            errors.append({"row": idx, "error": str(e)})

    BATCH = 500
    for i in range(0, len(accounts), BATCH):
        batch = accounts[i : i + BATCH]
        for acc in batch:
            existing = await db.get(Account, acc.code_full)
            if existing:
                existing.descripcion = acc.descripcion
            else:
                db.add(acc)
        await db.commit()

    totals = df.groupby("Tipo").size().to_dict()
    return {
        "imported": len(accounts),
        "errors": len(errors),
        "error_detail": errors[:10],
        "by_type": totals,
    }
