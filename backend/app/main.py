import os

from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.auth import get_current_user
from app.candado import candado_del_escenario
# ⚠️ El import ENGANCHA el listener del ORM: un mes cerrado no se edita.
# Ver `app/candado_meses.py`.
import app.candado_meses  # noqa: F401
from app.errores import ErrorApi, manejador as _manejador_errores
from app.models.scenario import ScenarioLockedError
from app.api.accounts_api import router as accounts_router
from app.api.scenarios_api import router as scenarios_router
from app.api.exchange_rates_api import router as exchange_rates_router
from app.api.revenue_api import router as revenue_router
from app.api.payroll_api import router as payroll_router
from app.api.costs_api import router as costs_router
from app.api.opex_api import router as opex_router
from app.api.nonop_api import router as nonop_router
from app.api.capital_api import router as capital_router
from app.api.allocation_api import router as allocation_router
from app.api.pl_api import router as pl_router
from app.api.big_picture_api import router as big_picture_router
from app.api.actuals_api import router as actuals_router
from app.api.mapping_api import router as mapping_router
from app.api.audit_api import router as audit_router
from app.api.auth_api import router as auth_router
from app.api.collab_api import router as collab_router
from app.api.cashflow_directo_api import router as cashflow_directo_router
from app.api.rooms_sets_api import router as rooms_sets_router
from app.api.consolidado_api import router as consolidado_router
from app.api.integraciones_api import router as integraciones_router
from app.api.origenes_api import router as origenes_router
from app.api.gasto_por_clase_api import router as gasto_clase_router
from app.api.fb_detalle_api import router as fb_detalle_router
from app.api.ingreso_detalle_api import router as ingreso_detalle_router
from app.api.estadisticas_api import router as estadisticas_router
from app.api.checkbook_api import router as checkbook_router
from app.api.canales_api import router as canales_router
from app.api.semillas_api import router as semillas_router
from app.api.mixer_api import router as mixer_router
from app.api.chequeo_api import router as chequeo_router
from app.api.lineas_obligatorias_api import router as lineas_obligatorias_router
from app.api.consulta_api import router as consulta_router
from app.api.payroll_position_report_api import router as payroll_position_report_router
from app.api.provisioning_api import router as provisioning_router
from app.api.export_api import router as export_router
from app.api.pl_full_detail_api import router as pl_full_detail_router
from app.api.club_stats_api import router as club_stats_router
from app.api.owners_q_api import router as owners_q_router
from app.api.sembrar_cuentas_api import router as sembrar_cuentas_router
from app.api.cuadre_api import router as cuadre_router
from app.api.setup_cuenta_api import router as setup_cuenta_router
from app.api.catalogo_departamentos_api import router as catalogo_departamentos_router
from app.api.break_even_api import router as break_even_router
from app.api.costos_grupos_api import router as costos_grupos_router
from app.api.costos_grupos_sim_api import router as costos_grupos_sim_router
from app.api.costos_grupos_resumen_api import router as costos_grupos_resumen_router
from app.api.costos_grupos_master_api import router as costos_grupos_master_router
from app.api.cierre_periodos_api import router as cierre_router
from app.api.guillermo_api import router as guillermo_router
from app.hotel_actual import HOTEL_ID, HOTEL_NAME

app = FastAPI(
    title=f"FinPlan {HOTEL_ID}",
    description=f"Sistema de planificación financiera hotelera — {HOTEL_NAME}",
    version="0.2.0",
)

# Orígenes que pueden hablarle a esta API desde el navegador.
#
# `CORS_ORIGINS` es una lista separada por comas con la URL EXACTA del frontend
# de ESTA propiedad. Se agregó al mover el frontend de Vercel a Railway: los
# dominios de Railway son `*.up.railway.app`, que el regex de abajo no cubre, y
# sin esto el navegador bloquea cada llamada aunque el backend responda bien.
#
# ⚠️ **Es una lista exacta y no un comodín `*.up.railway.app`, a propósito.**
# Con `allow_credentials=True`, un comodín deja que CUALQUIER app alojada en ese
# dominio compartido —de cualquier persona— haga peticiones con la cookie de
# sesión de quien la abra. El regex de Vercel ya arrastra ese problema; no hay
# por qué repetirlo con Railway ahora que cada propiedad tiene su propia URL.
_ORIGENES = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://localhost:3002",
        "https://finplan-cwl.vercel.app",
        *_ORIGENES,
    ],
    # Allow any Vercel deployment (production + preview URLs) for this project.
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# El idioma de los errores se resuelve ACÁ, al contestar — no en cada endpoint.
# Ver `app/errores.py`: el `raise` dice qué pasó, este manejador lo dice en el
# idioma de quien preguntó (`Accept-Language`, que pone `lib/api.ts`).
app.add_exception_handler(ErrorApi, _manejador_errores)


@app.exception_handler(ScenarioLockedError)
async def _escenario_bloqueado(request: Request, exc: ScenarioLockedError):
    """Escribir en una versión enllavada devuelve 409 con el motivo, no un error 500."""
    return JSONResponse(status_code=409, content={"detail": str(exc)})


# Endpoints de datos: requieren token (Fase 0 paso C). auth y /health quedan públicos.
# ⚠️ **El candado va acá, con la sesión.** Enllavar frenaba los imports y el
# recálculo pero NO impedía editar planilla, opex, revenue ni costos: medido
# el 2026-08-20, de 194 endpoints que escriben sólo catorce lo verificaban.
# Enganchado en el router, una ruta nueva queda cubierta sin que nadie se
# acuerde — ver `app/candado.py`.
_guard = [Depends(get_current_user), Depends(candado_del_escenario)]
app.include_router(accounts_router, prefix="/api", dependencies=_guard)
app.include_router(scenarios_router, prefix="/api", dependencies=_guard)
app.include_router(exchange_rates_router, prefix="/api", dependencies=_guard)
app.include_router(revenue_router, prefix="/api", dependencies=_guard)
app.include_router(payroll_router, prefix="/api", dependencies=_guard)
app.include_router(costs_router, prefix="/api", dependencies=_guard)
app.include_router(opex_router, prefix="/api", dependencies=_guard)
app.include_router(nonop_router, prefix="/api", dependencies=_guard)
app.include_router(capital_router, prefix="/api", dependencies=_guard)
app.include_router(allocation_router, prefix="/api", dependencies=_guard)
app.include_router(pl_router, prefix="/api", dependencies=_guard)
app.include_router(big_picture_router, prefix="/api", dependencies=_guard)
app.include_router(actuals_router, prefix="/api", dependencies=_guard)
app.include_router(mapping_router, prefix="/api", dependencies=_guard)
app.include_router(audit_router, prefix="/api", dependencies=_guard)
app.include_router(collab_router, prefix="/api", dependencies=_guard)
app.include_router(cashflow_directo_router, prefix="/api", dependencies=_guard)
app.include_router(rooms_sets_router, prefix="/api", dependencies=_guard)
# El consolidado NO lleva `_guard`: trae su propia puerta, que acepta la sesión
# normal O la llave de solo lectura (`CONSOLIDADO_API_KEY`). Con `_guard` encima,
# la llave nunca llegaría a usarse — el guard global exige JWT y corta antes.
# Sin llave configurada se comporta igual que el resto: solo sesión.
app.include_router(consolidado_router, prefix="/api")
app.include_router(integraciones_router, prefix="/api", dependencies=_guard)
app.include_router(origenes_router, prefix="/api", dependencies=_guard)
app.include_router(gasto_clase_router, prefix="/api", dependencies=_guard)
app.include_router(fb_detalle_router, prefix="/api", dependencies=_guard)
app.include_router(ingreso_detalle_router, prefix="/api", dependencies=_guard)
app.include_router(estadisticas_router, prefix="/api", dependencies=_guard)
app.include_router(checkbook_router, prefix="/api", dependencies=_guard)
app.include_router(canales_router, prefix="/api", dependencies=_guard)
app.include_router(semillas_router, prefix="/api", dependencies=_guard)
app.include_router(mixer_router, prefix="/api", dependencies=_guard)
app.include_router(chequeo_router, prefix="/api", dependencies=_guard)
app.include_router(lineas_obligatorias_router, prefix="/api", dependencies=_guard)
app.include_router(consulta_router, prefix="/api", dependencies=_guard)
app.include_router(payroll_position_report_router, prefix="/api", dependencies=_guard)
app.include_router(provisioning_router, prefix="/api", dependencies=_guard)
app.include_router(export_router, prefix="/api", dependencies=_guard)
app.include_router(pl_full_detail_router, prefix="/api", dependencies=_guard)
app.include_router(club_stats_router, prefix="/api", dependencies=_guard)
app.include_router(sembrar_cuentas_router, prefix="/api", dependencies=_guard)
app.include_router(owners_q_router, prefix="/api", dependencies=_guard)
# El Cuadre —Resumen vs Detalle, y cuál de las dos produce el P&L de hoy—
# existía desde el 2026-08-14 con sus pruebas, pero NUNCA se montó: el
# módulo estaba escrito y la ruta no existía en producción. La pantalla que
# tenía que mostrar el desacuerdo devolvía 404, así que la elección seguía
# siendo invisible por otra vía.
app.include_router(cuadre_router, prefix="/api", dependencies=_guard)
# El setup de la cuenta: las cinco preguntas por cuenta, y si se alinea entre años.
app.include_router(setup_cuenta_router, prefix="/api", dependencies=_guard)
app.include_router(catalogo_departamentos_router, prefix="/api", dependencies=_guard)
app.include_router(break_even_router, prefix="/api", dependencies=_guard)
app.include_router(costos_grupos_router, prefix="/api", dependencies=_guard)
app.include_router(costos_grupos_sim_router, prefix="/api", dependencies=_guard)
app.include_router(costos_grupos_resumen_router, prefix="/api", dependencies=_guard)
app.include_router(costos_grupos_master_router, prefix="/api", dependencies=_guard)
app.include_router(cierre_router, prefix="/api", dependencies=_guard)
app.include_router(guillermo_router, prefix="/api", dependencies=_guard)
app.include_router(auth_router, prefix="/api")   # público (login/bootstrap/status)


@app.on_event("startup")
async def _load_department_catalog():
    """Carga el department_catalog en el motor = fuente única de deptos. Si la
    tabla no existe o está vacía, el motor usa sus constantes (fallback seguro)."""
    try:
        from sqlalchemy import select
        from app.db import get_session
        from app.models.department_catalog import DepartmentCatalog
        from app.engine.pl_engine import set_dept_catalog
        async with get_session() as session:
            rows = (await session.execute(select(DepartmentCatalog))).scalars().all()
        set_dept_catalog([
            {"dept_code": r.dept_code, "default_pl_group": r.default_pl_group,
             "parent_dept_code": r.parent_dept_code} for r in rows
        ])
        print(f"✅ department_catalog cargado en el motor: {len(rows)} deptos")
    except Exception as e:
        print(f"⚠️  department_catalog NO cargado (usando constantes): {e}")


@app.get("/")
async def root():
    return {"status": "ok", "project": f"FinPlan {HOTEL_ID}", "version": "0.1.0"}


@app.get("/health")
async def health():
    """Qué corre acá: propiedad, commit y migración.

    Público a propósito —es lo que se abre para comparar los cuatro despliegues
    sin entrar a Railway— y por eso no lleva nada sensible: ni URLs, ni nombres
    de usuario, ni conteos de dato.

    La consulta a la base es *best effort*: si no contesta, `status` sigue siendo
    "healthy" y se dice que no se pudo leer. Un health check que se cae con la
    base arrastra al balanceador y esconde justo el dato que se venía a buscar.
    """
    from sqlalchemy import text
    from app.db import SessionLocal
    from app.version import sha_del_despliegue, head_del_codigo

    codigo = head_del_codigo()
    base = None
    error_base = None
    try:
        async with SessionLocal() as db:
            base = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalar_one_or_none()
    except Exception as e:  # noqa: BLE001 — cualquier fallo de la base es informativo acá
        error_base = type(e).__name__

    return {
        "status": "healthy",
        "hotel_id": HOTEL_ID,
        "hotel_name": HOTEL_NAME,
        "git_sha": sha_del_despliegue() or "local",
        "alembic_codigo": codigo,
        "alembic_base": base,
        # El que importa de un vistazo: en falso, el codigo trae una migracion
        # que no corrio y la app esta hablando con un esquema viejo.
        "migraciones_al_dia": (base is not None and base == codigo),
        "base_de_datos": "ok" if error_base is None else f"sin lectura ({error_base})",
    }

