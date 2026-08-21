from app.models.account import Account
from app.models.user import User
from app.models.section_assignment import SectionAssignment
from app.models.annotation import Annotation
from app.models.payroll_catalog import PayrollAccount
from app.models.hotel import Hotel
from app.models.scenario import Scenario, ScenarioLockedError
from app.models.exchange_rate import ExchangeRate, get_tc_for_month
from app.models.room_type_config import RoomTypeConfig, CWL_ROOM_TYPES
from app.models.component_label import ComponentLabel, ETIQUETAS_POR_DEFECTO, KIND_PACKAGE
from app.models.mapeo_origen import MapeoOrigen, ORIGENES
from app.models.scenario_master import ScenarioMaster
from app.models.sales_channel_config import SalesChannelConfig
from app.models.rate_card import RateCard
from app.models.occupancy_budget import OccupancyBudget
from app.models.package_config import PackageConfig
from app.models.package_menu import (
    PkgExperience, PkgExperienceItem, CWL_DEFAULT_EXPERIENCES,
)
from app.models.revenue_other import RevenueOther
from app.models.revenue_entry import RevenueEntry, REVENUE_LINES, REVENUE_LINE_LABELS
from app.models.spa_budget import SpaBudget
from app.models.historical_kpi import HistoricalKpi
from app.models.payroll_position import PayrollPosition, get_fte
from app.models.payroll_concept_entry import PayrollConceptEntry
from app.models.payroll_params import PayrollParams
from app.models.cost_entry import CostEntry
from app.models.opex_entry import OpexEntry
from app.models.nonop_entry import NonOpEntry
from app.models.capital_project import CapitalProject
from app.models.cafeteria_allocation_config import CafeteriaAllocationConfig, REMOTE_DEPTS
from app.models.laundry_allocation_config import LaundryAllocationConfig
from app.models.salary_allocation_config import SalaryAllocationConfig
from app.models.rooms_allocation_config import RoomsAllocationConfig
from app.models.dept_enablement import DeptEnablement, DIMENSIONES, SCOPE_KINDS
from app.models.laundry_params import LaundryParams
from app.models.allocation_entry import AllocationEntry
from app.models.pl_line import PLLine
from app.models.pl_manual_input import PLManualInput
from app.models.actual_entry import ActualEntry
from app.models.actual_pl_line import ActualPLLine
from app.models.mapping import ReportLineConfig, AccountMapping
from app.models.scenario_stat import ScenarioStat
# ⚠️ `DIMENSIONES` se re-exporta con otro nombre: `dept_enablement` ya tiene una
# constante que se llama igual (REVENUE/PAYROLL/OPEX/COST/PROPERTY) y son cosas
# distintas. Con el mismo nombre, la segunda importacion PISA a la primera y
# quien hiciera `from app.models import DIMENSIONES` recibiria la equivocada sin
# ningun error. Lo vigila `test_nada_se_exporta_dos_veces`.
from app.models.stat_account import StatAccount
from app.models.stat_account import DIMENSIONES as DIMENSIONES_ESTADISTICAS
from app.models.market_code import MarketCode, CANALES, CANAL_A_COMISION
from app.models.canal_comercial import CanalComercial
from app.models.canal_comision import CanalComision
from app.models.canal_mix_escenario import CanalMixEscenario
from app.models.statistical_entry import StatisticalEntry
from app.models.club_membership_stat import ClubMembershipStat
from app.models.club_fee_budget import ClubFeeBudget
from app.models.actual_room_stat import ActualRoomStat
from app.models.actual_dept_fte import ActualDeptFte
from app.models.on_the_books import OnTheBooksEntry
from app.models.otb_daily_occ import OtbDailyOcc
from app.models.channel_mix import ChannelMixEntry
from app.models.country_mix import CountryMixEntry, COUNTRY_METRICS
from app.models.ops_kpi import OpsKpiEntry
from app.models.balance_sheet_line import BalanceSheetLine
from app.models.cashflow_budget_input import CashFlowBudgetInput
from app.models.cashflow_budget_driver import CashFlowBudgetDriver
from app.models.cashflow_wc_params import CashFlowWCParams
from app.models.cashflow_params import CashFlowParams
from app.models.cashflow_version import CashFlowVersion
from app.models.belowgop_account_entry import BelowGopAccountEntry
from app.models.revenue_account_entry import RevenueAccountEntry
from app.models.otb_week_param import OtbWeekParam
from app.models.tax_params import TaxParams
from app.models.big_picture_version import BigPictureVersion
from app.models.department_catalog import DepartmentCatalog

__all__ = [
    "DepartmentCatalog",
    "Account", "PayrollAccount", "User", "SectionAssignment", "Annotation",
    "Hotel", "Scenario", "ScenarioLockedError",
    "ExchangeRate", "get_tc_for_month",
    "RoomTypeConfig", "CWL_ROOM_TYPES",
    "ComponentLabel", "ETIQUETAS_POR_DEFECTO", "KIND_PACKAGE",
    "MapeoOrigen", "ORIGENES",
    "ScenarioMaster",
    "SalesChannelConfig", "RateCard", "OccupancyBudget",
    "PackageConfig", "RevenueOther",
    "RevenueEntry", "REVENUE_LINES", "REVENUE_LINE_LABELS", "ActualRoomStat", "ActualDeptFte", "OnTheBooksEntry", "OtbDailyOcc",
    "ChannelMixEntry",
    "CountryMixEntry", "COUNTRY_METRICS",
    "OpsKpiEntry",
    "BalanceSheetLine",
    "CashFlowBudgetInput",
    "CashFlowBudgetDriver",
    "CashFlowWCParams",
    "SpaBudget",
    "HistoricalKpi",
    "PayrollPosition", "get_fte",
    "PayrollConceptEntry",
    "PayrollParams",
    "CostEntry",
    "OpexEntry",
    "NonOpEntry", "CapitalProject",
    "CafeteriaAllocationConfig", "REMOTE_DEPTS",
    "LaundryAllocationConfig", "LaundryParams",
    "AllocationEntry",
    "PLLine", "PLManualInput",
    "ActualEntry", "ActualPLLine",
    "ReportLineConfig", "AccountMapping",
    "ScenarioStat", "ClubMembershipStat", "ClubFeeBudget",
    "StatAccount", "StatisticalEntry", "DIMENSIONES_ESTADISTICAS",
    "MarketCode", "CANALES", "CANAL_A_COMISION", "CanalComercial",
    "CanalComision",
    "CanalMixEscenario",
    "CashFlowParams", "CashFlowVersion", "BelowGopAccountEntry",
    "RevenueAccountEntry", "OtbWeekParam", "TaxParams",
    "BigPictureVersion",
]
from app.models.break_even import (
    BeDepartment, BeCostClassification, BeClassificationSnapshot,
    DEPT_ACTIVO, DEPT_PENDIENTE,
)
from app.models.owners_q import (
    ReportLine, ReportLineMapping, Capacidad, ReportSnapshot,
    LINE_TYPES, NATURES,
)
from app.models.costos_grupos import (
    CfgTemporada, CfgParametro, CfgClasificacionCosto, CfgEscalon, CfgCanalCosto,
    CfgComposicion,
    TEMPORADAS,
)
# Registro de importaciones (Guillermo Fase 0). Se importa acá y no sólo desde
# la app para que `import app.models` registre la tabla: si no, las pruebas que
# recorren `Base.metadata` la ven o no según el orden en que corran.
from app.models.import_registro import ImportBatch, ImportFile, ESTADOS, MODOS
# Guillermo Fase 1: configuración, latido, manifiesto y cola de excepciones.
from app.models.guillermo import (
    GuillermoConfig, GuillermoHeartbeat, ExpectedReport, ImportException)
