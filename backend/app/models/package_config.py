from decimal import Decimal
from sqlalchemy import String, Numeric, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

# Component names used throughout the system
COMPONENT_FOOD = "FOOD"
COMPONENT_BEV = "BEVERAGE"
COMPONENT_ACTIVITIES = "ACTIVITIES"
COMPONENT_TRANSPORT = "TRANSPORT"
COMPONENT_SUSTAINABILITY = "SUSTAINABILITY"

# Default package rates from Budget2026_Revenue_CORCO.xlsx Key Indicators
# (per guest per night, in USD)
CWL_DEFAULT_PACKAGE = {
    COMPONENT_FOOD: {
        "rate_per_pax_night": Decimal("108.0000"),  # Breakfast($18) + Lunch($36) + Dinner($54)
        "is_commissionable": True,
        "bev_food_ratio": Decimal("0.3400"),        # Beverage = 34% of Food
    },
    COMPONENT_ACTIVITIES: {
        "rate_per_pax_night": Decimal("101.0000"),  # Snorkeling($48) + PN Walk($53)
        "is_commissionable": True,
        "bev_food_ratio": None,
    },
    COMPONENT_TRANSPORT: {
        "rate_per_pax_night": Decimal("35.0000"),   # Transfer
        "is_commissionable": True,
        "bev_food_ratio": None,
    },
    COMPONENT_SUSTAINABILITY: {
        "rate_per_pax_night": Decimal("28.0000"),   # Government sustainability fee
        "is_commissionable": False,                  # No channel commission applied
        "bev_food_ratio": None,
    },
}


class PackageConfig(Base):
    """Per-scenario package component rates (per guest per night)."""
    __tablename__ = "package_configs"
    __table_args__ = (
        UniqueConstraint("scenario_id", "component", name="uq_package_config"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    hotel_id: Mapped[str] = mapped_column(String(10), nullable=False)
    component: Mapped[str] = mapped_column(String(20), nullable=False)
    rate_per_pax_night: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    is_commissionable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # For BEVERAGE only: revenue = food_revenue × bev_food_ratio
    bev_food_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
