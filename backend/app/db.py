from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session as SyncSession
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv
import os

load_dotenv()


def normalize_database_url(url: str) -> str:
    """
    Ensure the URL uses the asyncpg driver. Managed providers (Railway, Heroku,
    etc.) expose DATABASE_URL as 'postgresql://' (or 'postgres://'); both the app
    engine and Alembic here need 'postgresql+asyncpg://'.
    """
    if not url:
        return url
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://"):]
    return url


DATABASE_URL = normalize_database_url(
    os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost/finplan_cwl")
)

# El pool por defecto de SQLAlchemy es 5 + 10 de reserva = 15 conexiones, y se
# quedaba corto: cada P&L recalcula 12 meses con ~99 consultas y retiene su
# conexión varios segundos. Con el tablero abierto (compare de 5 escenarios, un
# /monthly/ por escenario) el pool se vaciaba y todo lo demás moría con
# «QueuePool limit of size 5 overflow 10 reached» — un 500 que el navegador
# muestra como «Failed to fetch», sin pista de que el problema son conexiones.
# Postgres acepta 100 (menos 3 reservadas): 50 deja holgura de sobra y sigue
# lejos del techo aunque Railway levante una segunda réplica.
# pre_ping porque Railway corta conexiones ociosas y una muerta reventaría la
# primera consulta que la agarre; recycle para no llegar nunca a ese punto.
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=30,
    pool_timeout=30,
    pool_pre_ping=True,
    pool_recycle=1800,
)
# ⚠️ **Una clase de sesión propia, y no el `Session` de SQLAlchemy.** Los
# candados que se enganchan a eventos de sesión (`app/candado_meses.py`) tienen
# que aplicar a las sesiones DE LA APP y a ninguna otra: registrados en el
# `Session` global disparaban también en sesiones sueltas —una prueba que arma
# un SQLite en memoria con dos tablas— y ahí la consulta del candado revienta
# porque `scenarios` no existe. El evento se registra sobre esta clase.
class SesionFinPlan(SyncSession):
    pass


SessionLocal = async_sessionmaker(engine, expire_on_commit=False,
                                  sync_session_class=SesionFinPlan)


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI dependency — yields a session."""
    async with SessionLocal() as session:
        yield session


@asynccontextmanager
async def get_session():
    """Async context manager — `async with get_session() as session:`."""
    async with SessionLocal() as session:
        yield session
