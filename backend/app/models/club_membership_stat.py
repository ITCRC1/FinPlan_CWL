import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ClubMembershipStat(Base):
    """Conteo de socios del Club Madresal por escenario × mes.

    **Por qué es un estadístico y no una línea de plata.** El Club vende
    **acceso a las instalaciones** del hotel. Detrás hay un desarrollo
    inmobiliario que NO es parte de este P&L; lo que sí entra es la cuota de
    acceso, que se cobra en el departamento 260 y ya vive en `REV_CLUB`. El
    conteo de socios explica esa cuota —cuántos pagan, cuántos están
    condicionados— pero no es dinero, así que va arriba con los KPIs de
    habitaciones y no en ninguna línea del estado de resultados.

    **El total del año NO es la suma de los doce meses**, es el saldo de
    **diciembre**. Son socios, no ingresos: sumar 121 + 121 + 123… daría 1.500
    socios donde hay 129. En el Excel de Amarena las filas 11–14 son, junto con
    la ocupación y el ADR, las únicas cuatro con semántica no aditiva
    (`docs/fase2/ESCANEO_03_FORMULAS.md` §5.13).

    **Es de Amarena y se va a ir.** El owner lo dijo explícito: esto desaparece
    cuando el Club se opere por fuera del hotel. Por eso la visibilidad NO se
    decide acá ni con un `if` por hotel, sino con la matriz de provisionamiento:
    se muestra si el departamento `260` está habilitado en esa propiedad. El día
    que el Club salga, se desmarca en Provisionamiento y esto se apaga solo, sin
    tocar código. Los datos quedan (apagar esconde, nunca borra).
    """
    __tablename__ = "club_membership_stats"
    __table_args__ = (
        UniqueConstraint("scenario_id", "month", name="uq_club_membership_stat"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    month: Mapped[int] = mapped_column(Integer)          # 1-12

    total: Mapped[int] = mapped_column(Integer, default=0)          # Total Membresías
    condicionados: Mapped[int] = mapped_column(Integer, default=0)  # Membresías Condicionados
    pagando: Mapped[int] = mapped_column(Integer, default=0)        # Membresías Pagando
    acuerdo_pago: Mapped[int] = mapped_column(Integer, default=0)   # En acuerdo de pago

    def __repr__(self) -> str:
        return f"<ClubMembershipStat m{self.month} total={self.total}>"
