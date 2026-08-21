"""
One-time script: rename dept_code 0191 → 0190 in opex_entries.
Run: python -m scripts.fix_dept_codes
"""
import asyncio
from sqlalchemy import text
from app.db import SessionLocal


async def main() -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM opex_entries WHERE dept_code = '0191'")
        )
        count = result.scalar()
        print(f"Rows with dept_code='0191': {count}")

        if count == 0:
            print("Nothing to fix.")
            return

        await session.execute(
            text("UPDATE opex_entries SET dept_code = '0190' WHERE dept_code = '0191'")
        )
        await session.commit()
        print(f"✓ Updated {count} rows: 0191 → 0190")


if __name__ == "__main__":
    asyncio.run(main())
