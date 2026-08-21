# -*- coding: utf-8 -*-
"""
LA CONFIGURACION DE ALLOCATIONS VIAJA COMPLETA AL COPIAR.

No basta con llevarse los departamentos que participan: hay que llevarse tambien
los EXCLUIDOS. Si en la copia faltara la fila de un excluido, ese departamento
volveria a recibir cafeteria —o lavanderia— sin que nadie lo pidiera, y el costo
aparecerio donde no corresponde.

Caso real: Cocina (0122) no come en la propiedad y Ventas (0190) es remoto. Si su
exclusion no viaja, el reparto les carga almuerzo.
"""
from sqlalchemy.orm import class_mapper

from app.api.scenarios_api import COPY_DATASETS, DEFAULT_COPY_DATASETS
from app.models.benefit_allocation_config import BenefitAllocationConfig
from app.models.cafeteria_allocation_config import CafeteriaAllocationConfig
from app.models.laundry_allocation_config import LaundryAllocationConfig
from app.models.laundry_params import LaundryParams
from app.models.salary_allocation_config import SalaryAllocationConfig


def test_las_configuraciones_de_reparto_estan_en_la_copia():
    for Model in (CafeteriaAllocationConfig, LaundryAllocationConfig,
                  SalaryAllocationConfig, LaundryParams, BenefitAllocationConfig):
        assert Model in COPY_DATASETS["allocations"], (
            f"{Model.__name__} no viaja: la copia quedaria con otro reparto")
    assert "allocations" in DEFAULT_COPY_DATASETS


def test_la_marca_de_participacion_es_una_columna_mapeada():
    """El copy clona columna por columna: si `participates` no estuviera mapeada,
    la copia nacería con el default y los excluidos volverian a participar."""
    for Model in (CafeteriaAllocationConfig, LaundryAllocationConfig):
        cols = {c.key for c in class_mapper(Model).columns}
        assert "participates" in cols, f"{Model.__name__}: no viajaria la exclusion"
        assert "dept_code" in cols


def test_la_copia_reemplaza_y_no_mezcla():
    """Con replace, el destino queda EXACTAMENTE como el origen. Si solo agregara,
    un departamento excluido en el origen podria quedar participando en el destino
    por una fila vieja."""
    import inspect
    from app.api import scenarios_api
    src = inspect.getsource(scenarios_api.copy_scenario_data)
    assert "replace" in src
    assert "sa_delete(Model)" in src, "no limpia el destino antes de copiar"


def test_los_kilos_de_lavanderia_tambien_viajan():
    """Los kilos definen las proporciones del reparto de lavanderia: sin ellos la
    copia repartiria distinto aunque el costo sea el mismo."""
    cols = {c.key for c in class_mapper(LaundryAllocationConfig).columns}
    assert any(c.startswith("kilos") or "kg" in c for c in cols), (
        f"no encuentro los kilos en {sorted(cols)}")


# ── EL MODELO VIAJA INTACTO ──────────────────────────────────────────────────
# Tres veces ya paso lo mismo: se agrego una tabla al escenario y NADIE la puso en
# la lista de copia, asi que la version nueva nacia sin esa parte del modelo y el
# numero salia distinto sin explicacion (los conceptos de planilla, el reparto de
# beneficios, el tipo de cambio). Esta prueba obliga a decidir: o viaja, o queda
# escrito por que no.

# Tablas del escenario que NO se copian A PROPOSITO, con el motivo.
NO_VIAJAN = {
    # Cache del P&L: nadie lo lee, el destino lo regenera al recalcular. Copiarlo
    # solo arrastraria numeros viejos.
    "pl_lines": "cache regenerable",
    # OJO: `actual_entries` y `actual_pl_lines` SI viajan (datasets 'actuals' y
    # 'pl_snapshot', y desde el arreglo del copy tambien POR DEFECTO). Quedan
    # listadas aca solo por historia; la lista que manda es COPY_DATASETS.
    "actual_room_stats": "estadisticas reales",
    "actual_dept_fte": "FTE real por departamento — mismo motivo que actual_room_stats",
    "balance_sheet_lines": "balance real",
    "on_the_books_entries": "reservas en firme",
    "otb_daily_occ": "ocupacion diaria real",
    "otb_week_params": "parametros de la semana OTB",
    # Colaboracion: son de la version, no del modelo.
    "annotations": "comentarios de la version",
    "section_assignments": "responsables de la version",
    # Traza de importaciones (Guillermo Fase 0). NO viajan, y es la respuesta
    # correcta: el registro dice QUE ARCHIVO recibio ESE escenario. Copiarlo
    # haria que la version nueva afirme haber recibido archivos que nunca
    # recibio — y como la traza existe justamente para auditar, una traza
    # copiada es peor que ninguna.
    "import_batches": "traza de quien subio que — es del escenario que lo recibio",
    "import_files": "identidad del archivo — misma razon que import_batches",
}


def test_toda_tabla_del_escenario_esta_clasificada():
    """Si aparece una tabla nueva con scenario_id y nadie la clasifico, esto falla.

    No juzga si debe copiarse: obliga a que alguien lo decida y lo escriba.
    """
    import app.models  # noqa: F401  — registra todos los modelos
    from app.db import Base

    copiadas = {M.__tablename__ for ds in COPY_DATASETS.values() for M in ds}
    sin_clasificar = []
    for tabla in Base.metadata.tables.values():
        if "scenario_id" not in tabla.columns:
            continue
        if tabla.name in copiadas or tabla.name in NO_VIAJAN:
            continue
        sin_clasificar.append(tabla.name)

    assert not sin_clasificar, (
        f"Estas tablas del escenario no viajan al copiar y nadie dijo por que: "
        f"{sorted(sin_clasificar)}. Agreguelas a COPY_DATASETS o a NO_VIAJAN con "
        f"el motivo.")


def test_el_modelo_de_planning_viaja_por_defecto():
    """Lo que define como se CALCULA un presupuesto tiene que viajar entero."""
    por_defecto = {M.__tablename__ for ds, ms in COPY_DATASETS.items()
                   if ds in DEFAULT_COPY_DATASETS for M in ms}
    imprescindibles = {
        "payroll_positions", "payroll_concept_entries", "payroll_params",
        "opex_entries", "cost_entries", "nonop_entries", "revenue_entries",
        "rate_cards", "occupancy_budgets", "scenario_stats", "exchange_rates",
        "cafeteria_allocation_config", "laundry_allocation_config",
        "laundry_params", "benefit_allocation_config",
        "cashflow_params", "cashflow_directo_config", "tax_params",
    }
    faltan = imprescindibles - por_defecto
    assert not faltan, f"no viajan por defecto: {sorted(faltan)}"
