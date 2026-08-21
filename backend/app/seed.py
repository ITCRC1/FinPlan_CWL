"""
Seed de una instalación: hotel, tipos de habitación, equipo, catálogo de
departamentos y el motor de mapeo del P&L.

Corre en cada arranque y es idempotente. Cada hotel es un PROYECTO APARTE
—base propia, app propia— así que este script es lo que hace que una
instalación nueva nazca funcionando en vez de nacer vacía.

Identidad del hotel, por entorno (default = Corcovado, para no moverlo):

    HOTEL_ID=AMA HOTEL_NAME="Amarena Canvas Beach Hotel"     HOTEL_SHORT_NAME=Amarena HOTEL_ROOMS=24 HOTEL_TC_USD=530.0000

    cd backend && python -m app.seed
"""
import asyncio
import os
from decimal import Decimal
from sqlalchemy import select
from app.db import engine, SessionLocal, Base
from app.models.hotel import Hotel
from app.models.room_type_config import RoomTypeConfig, CWL_ROOM_TYPES
from app.models.user import User
from app.auth import hash_password
# Importar todos los modelos para que Base.metadata los registre
from app.models import Account, PayrollAccount, Scenario, ExchangeRate  # noqa

# Equipo de Corcovado, con contraseña temporal.
#
# NO se siembran fuera de Corcovado. Cada hotel va a ser un proyecto aparte y
# estas son nueve personas reales, con su correo, que no tienen nada que ver con
# Amarena, Oxígen ni Ojochal — sembrarlas ahí sería filtrar datos personales a
# terceros, y encima con una contraseña conocida. El hotel nuevo arranca solo
# con su admin y agrega a su gente.
#
# Misma razón por la que una entrega de base de datos va con
# `--exclude-table=users`.
SEMBRAR_EQUIPO_CWL = os.getenv("SEED_TEAM_CWL", "").lower() in ("1", "true", "yes")
TEAM_TEMP_PASSWORD = "CWLintegrity2026"
TEAM_USERS = [
    ("ronald@thecostaricacollection.com", "Ronald", "collaborator"),
    ("gmunoz@programarcr.com", "Gustavo Muñoz", "collaborator"),
    ("auditor1@seedcostarica.com", "Auditor 1", "collaborator"),
    ("auditor2@thecostaricacollection.com", "Francela Flores", "collaborator"),
    ("berny@consultantscr.com", "Berny Fallas Mora", "collaborator"),
    ("aperez@consultantscr.com", "Alex Perez", "collaborator"),
    ("iromero@consultantscr.com", "Iván Romero Arias", "collaborator"),
    ("damianconsultantscr@gmail.com", "Damian (consultants)", "collaborator"),
    ("auxiliarconsultants@gmail.com", "Auxiliar Consultants", "collaborator"),
]


# Identidad del hotel de ESTA instalación. Estaba quemada en CWL, así que un
# proyecto nuevo para Amarena nacía llamándose Corcovado Wilderness Lodge, con
# las 30 habitaciones y los 6 tipos de Corcovado. Ahora sale del entorno y el
# default sigue siendo CWL, para que Corcovado no cambie.
HOTEL_ID = os.getenv("HOTEL_ID", "CWL")
HOTEL_NAME = os.getenv("HOTEL_NAME", "Corcovado Wilderness Lodge")
HOTEL_SHORT = os.getenv("HOTEL_SHORT_NAME", "Corcovado")
HOTEL_ROOMS = int(os.getenv("HOTEL_ROOMS", "30"))
HOTEL_TC = os.getenv("HOTEL_TC_USD", "530.0000")


async def seed():
    # El esquema lo crea Alembic ('alembic upgrade head'). El seed SOLO inserta
    # datos — nunca crea tablas (evita choques de índices duplicados con Alembic).
    async with SessionLocal() as db:
        # Hotel CWL
        hotel = await db.get(Hotel, HOTEL_ID)
        if not hotel:
            hotel = Hotel(
                id=HOTEL_ID,
                name=HOTEL_NAME,
                short_name=HOTEL_SHORT,
                rooms=HOTEL_ROOMS,
                tc_usd_default=Decimal(HOTEL_TC),
                closed_months="",     # sin meses cerrados — todos se calculan por fórmula
                active=True,
            )
            db.add(hotel)
            print(f"✓ Hotel {HOTEL_ID} creado ({HOTEL_NAME})")
        else:
            print(f"  Hotel {HOTEL_ID} ya existe — omitido")

        # Tipos de habitación. Los 6 de CWL_ROOM_TYPES son de Corcovado; otro
        # hotel carga los suyos en Master Data y acá no se le inventa nada.
        result = await db.execute(
            select(RoomTypeConfig).where(RoomTypeConfig.hotel_id == HOTEL_ID)
        )
        existing_types = result.scalars().all()

        if not existing_types and HOTEL_ID != "CWL":
            print(f"  {HOTEL_ID}: sin tipos de habitación — se cargan en Master Data")
        elif not existing_types:
            for rt in CWL_ROOM_TYPES:
                db.add(RoomTypeConfig(hotel_id=HOTEL_ID, **rt))
            await db.commit()
            total = sum(rt["units"] for rt in CWL_ROOM_TYPES)
            print(f"✓ {len(CWL_ROOM_TYPES)} tipos de habitación creados ({total} unidades totales)")
            for rt in CWL_ROOM_TYPES:
                print(f"    [{rt['sort_order']}] {rt['short_name']:<15} ×{rt['units']}")
        else:
            print(f"  Tipos de habitación ya existen ({len(existing_types)}) — omitidos")

        # Usuarios del equipo (idempotente: solo crea si el email no existe).
        created = 0
        for email, name, role in (TEAM_USERS if (HOTEL_ID == "CWL" or SEMBRAR_EQUIPO_CWL) else []):
            em = email.lower()
            exists = (await db.execute(select(User).where(User.email == em))).scalar_one_or_none()
            if not exists:
                db.add(User(email=em, name=name, role=role, active=True,
                            password_hash=hash_password(TEAM_TEMP_PASSWORD)))
                created += 1
        if created:
            await db.commit()
            print(f"✓ {created} usuarios del equipo creados (password temporal)")
        elif HOTEL_ID != "CWL" and not SEMBRAR_EQUIPO_CWL:
            print(f"  {HOTEL_ID}: no se siembra el equipo de Corcovado (son personas de otro hotel)")
        else:
            print("  Usuarios del equipo ya existen — omitidos")

        await db.commit()

    # department_catalog (universo canónico de deptos, derivado de las constantes)
    try:
        from app.seed_department_catalog import seed as seed_dept_catalog
        await seed_dept_catalog()
    except Exception as e:  # no romper el boot si la migración aún no corrió
        print(f"  department_catalog seed omitido: {e}")

    # Motor de mapeo del P&L. Va al final porque es lo más pesado (899 filas) y
    # porque nada de lo anterior depende de él.
    try:
        from app.seed_mapping import seed_mapping
        async with SessionLocal() as db:
            await seed_mapping(db)
    except Exception as e:
        print(f"  seed de mapeo omitido: {e}")

    # Reporte `Owners Q` (tab Reports): las 48 filas, el ruteo de las 68
    # `Línea P&L` y la capacidad. Va DESPUÉS del mapeo porque el gate de
    # cobertura se mide contra las reglas que aquél acaba de sembrar.
    try:
        from app.seed_owners_q import seed_owners_q, verificar_cobertura
        async with SessionLocal() as db:
            r = await seed_owners_q(db)
            await db.commit()
            cob = await verificar_cobertura(db)
        print(f"  owners_q: {r['filas']['total']} filas "
              f"({r['filas']['nuevas']} nuevas, {r['filas']['cambiadas']} actualizadas), "
              f"{r['ruteo']['total']} líneas ruteadas, "
              f"{r['capacidad']['nuevas']} meses de capacidad")
        if cob["ok"]:
            print(f"  owners_q cobertura ✓ {cob['lineas_ruteadas']} líneas ruteadas")
        else:
            # No se rompe el arranque —dejaría la app entera abajo— pero grita.
            # El endpoint del reporte SÍ falla si la cobertura no está.
            print(f"  ⚠️  owners_q COBERTURA INCOMPLETA — huérfanas: {cob['huerfanas']} "
                  f"destino inexistente: {cob['destino_inexistente']}")
        if cob["ruteadas_sin_regla"]:
            print(f"  owners_q: ruteadas sin reglas todavía: {cob['ruteadas_sin_regla']}")
    except Exception as e:
        print(f"  seed de owners_q omitido: {e}")

    # Catálogo de cuentas estadísticas (clase 9). Igual que el mapeo: la lista de
    # verdad vive en git, no en la base. NO sale de la tabla `accounts`, que está
    # vacía en producción (ver app/seed_stats.py).
    try:
        from app.seed_stats import seed_stats
        async with SessionLocal() as db:
            r = await seed_stats(db)
            await db.commit()
        print(f"  stat_accounts: {r['total']} cuentas "
              f"({r['nuevas']} nuevas, {r['cambiadas']} actualizadas)")
        if r["sobran"]:
            print(f"  ⚠️  cuentas estadísticas en base que no están en el JSON: "
                  f"{r['sobran']} (no se borran)")
    except Exception as e:
        print(f"  seed de estadísticas omitido: {e}")

    # Market codes de Opera. NO pisa lo que el owner edite en la app.
    try:
        from app.seed_market_codes import seed_market_codes
        async with SessionLocal() as db:
            r = await seed_market_codes(db)
            await db.commit()
        print(f"  market_codes: {r['total']} códigos ({r['nuevos']} nuevos)")
    except Exception as e:
        print(f"  seed de market codes omitido: {e}")

    # Canales comerciales: la lista que decide quién cobra.
    try:
        from app.seed_canales_comerciales import seed_canales
        async with SessionLocal() as db:
            r = await seed_canales(db)
            await db.commit()
        print(f"  canales_comerciales: {r['total']} ({r['nuevos']} nuevos)")
    except Exception as e:
        print(f"  seed de canales omitido: {e}")

    # Costos para negociación de grupos: el mapa de temporadas y los
    # parámetros del modelo. No pisa lo que el owner edite en la app.
    try:
        from app.seed_costos_grupos import (
            seed_composicion, seed_costos_grupos, seed_tarifas_rack)
        async with SessionLocal() as db:
            r = await seed_costos_grupos(db)
            await db.commit()
            rc = await seed_composicion(db)
            await db.commit()
            rr = await seed_tarifas_rack(db)
            await db.commit()
        print(f"  costos_grupos: {rc['filas']} lineas de composicion "
              f"({rc['nuevas']} nuevas)")
        print(f"  costos_grupos: {rr['filas']} tarifas rack "
              f"({rr['nuevas']} nuevas)")
        print(f"  costos_grupos: {r['temporadas']} temporadas "
              f"({r['temporadas_nuevas']} nuevas), {r['parametros']} parámetros "
              f"({r['parametros_nuevos']} nuevos)")
    except Exception as e:
        print(f"  seed de costos_grupos omitido: {e}")

    # Configuración de Guillermo. ⚠️ El manifiesto de reportes esperados NO se
    # siembra: su contenido es la decisión D-1 del owner y no se inventa. Un
    # manifiesto inventado haría que Guillermo reclamara archivos que nadie
    # prometió y diera por completo lo que no lo está.
    try:
        from app.seed_guillermo import seed_guillermo, seed_manifiesto
        async with SessionLocal() as db:
            rg = await seed_guillermo(db)
            await db.commit()
            rm = await seed_manifiesto(db)
            await db.commit()
        print(f"  guillermo: {rg['total']} parámetros ({rg['nuevos']} nuevos)")
        print(f"  guillermo: {rm['total']} reportes esperados ({rm['nuevos']} nuevos)")
    except Exception as e:
        print(f"  seed de guillermo omitido: {e}")

    # Break-Even: los departamentos y la clasificacion fijo/variable.
    #
    # ATENCION: entro aca el 2026-08-20. Antes se cargaba con un script a mano
    # que NADIE llamaba, asi que un clon levantaba con las dos tablas vacias, y
    # eso no da error: Break-Even muestra ceros y Costos de Grupos pierde el
    # `be_section` con que separa PAYROLL de COST OF SALES. Cero se lee igual
    # que "no gasto".
    #
    # Es por propiedad: sin `seed_data/<HOTEL_ID>/break_even/` no siembra nada y
    # NO hereda los porcentajes de Corcovado.
    try:
        from app.seed_break_even import seed_break_even
        async with SessionLocal() as db:
            rb = await seed_break_even(db)
            await db.commit()
        if rb["sembrado"]:
            print(f"  break_even: {rb['departamentos']} departamentos "
                  f"({rb['departamentos_nuevos']} nuevos), {rb['reglas']} reglas "
                  f"({rb['reglas_nuevas']} nuevas)")
        else:
            print(f"  break_even: {rb['hotel']} no trae semilla - se carga en la app")
    except Exception as e:
        print(f"  seed de break_even omitido: {e}")

    print("\n✅ Seed completado.")
    print("   Próximo paso: POST /api/scenarios/ para crear el Budget 2026")


if __name__ == "__main__":
    asyncio.run(seed())
