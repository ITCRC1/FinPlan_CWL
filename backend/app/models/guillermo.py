# -*- coding: utf-8 -*-
"""Las tablas de Guillermo — configuración, manifiesto, latido y excepciones.

Ver `docs/GUILLERMO.md`. **Sólo lo que FinPlan NO tenía**: el spec original
proponía crear también un `mapping_rules`, y eso ya existe como `mapeo_origen`
(decisión del owner 2026-08-19: se extiende, no se duplica).

⚠️ `hotel_id` es TEXTO en todas, igual que las otras ~60 tablas. El spec pedía
`property_id uuid FK → properties`: no existe tal tabla, y FinPlan es **una
instalación por hotel**, no multi-tenant.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, Numeric, String,
                        Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class GuillermoConfig(Base):
    """Nada hardcoded (`docs/GUILLERMO.md` §8). El valor viaja como texto:
    conviven números, horas y opciones."""
    __tablename__ = "guillermo_config"
    __table_args__ = (
        UniqueConstraint("hotel_id", "clave", name="uq_guillermo_config"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    clave: Mapped[str] = mapped_column(String(40))
    valor: Mapped[str] = mapped_column(String(120), default="")
    # Para qué sirve, en la pantalla. Sin esto la config es una lista de claves
    # que nadie se anima a tocar.
    descripcion: Mapped[str] = mapped_column(String(200), default="")


class GuillermoHeartbeat(Base):
    """El latido (§12.1) — **lo que hace que el silencio signifique «todo bien»**.

    Sin esto, un sistema que sólo avisa cuando hay problemas es indistinguible
    de uno muerto: no avisa igual en los dos casos.
    """
    __tablename__ = "guillermo_heartbeat"

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    # ok | con_excepciones | fallo
    resultado: Mapped[str] = mapped_column(String(20), default="ok")
    detalle: Mapped[str] = mapped_column(Text, default="")
    latido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True)


class ExpectedReport(Base):
    """El manifiesto: qué reportes se esperan (§6.1).

    ⚠️ **Nació vacío a propósito, y se llenó cuando el owner decidió** (D-1,
    2026-08-20): XML de Operations y Marketing todos los días, actuales del GL
    y Balance Sheet una vez al mes. Ver `app/seed_guillermo.py:MANIFIESTO`.

    La regla sigue en pie para lo que venga: **no se inventa**. Un manifiesto
    inventado haría que Guillermo reclamara archivos que nadie prometió y
    diera por completo lo que no lo está.

    Un reporte ausente es una excepción de la misma severidad que uno corrupto.
    """
    __tablename__ = "guillermo_expected_reports"
    __table_args__ = (
        UniqueConstraint("hotel_id", "report_id", name="uq_expected_report"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    report_id: Mapped[str] = mapped_column(String(60))
    # Glob del nombre: "TrialBalance_*.csv"
    patron: Mapped[str] = mapped_column(String(160), default="")
    formato: Mapped[str] = mapped_column(String(10), default="")   # csv|xlsx|xml|pdf
    frecuencia: Mapped[str] = mapped_column(String(12), default="daily")
    obligatorio: Mapped[bool] = mapped_column(Boolean, default=True)
    # Nivel 1: tamaño esperado, para detectar el archivo truncado.
    tamano_min: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    notas: Mapped[str] = mapped_column(String(200), default="")

    # ── Cómo se verifica (D-1 del owner, 2026-08-20) ─────────────────────────
    #
    # ⚠️ Son dos verificaciones distintas y hay que saber cuál se está mirando:
    #
    # `cobertura`     — hasta qué período hay dato en la tabla de destino.
    #                   Funciona HACIA ATRÁS: contesta hoy sobre lo de antes.
    # `ultima_subida` — mira `import_files`, que empezó a registrar el
    #                   2026-08-20. Es lo correcto para un XML diario (uno de
    #                   reservas mira al futuro, así que «hasta qué mes hay
    #                   dato» no dice si se subió hoy), pero NO PUEDE hablar de
    #                   antes de esa fecha, y eso hay que decirlo.
    verifica: Mapped[str] = mapped_column(String(20), default="")
    # Tabla de destino (`cobertura`) o trozo de la ruta (`ultima_subida`).
    objetivo: Mapped[str] = mapped_column(String(80), default="")
    # Un mensual que se cierra el día 10 no está atrasado el día 2.
    gracia_dias: Mapped[int] = mapped_column(Integer, default=0)


class ImportException(Base):
    """La cola de excepciones (§7.3) — **hoy las filas rechazadas se pierden**.

    Se devuelven en la respuesta HTTP y se van con ella. Persistirlas es lo que
    convierte «el import tuvo problemas» en «estos 4 conceptos esperan que
    alguien decida».
    """
    __tablename__ = "guillermo_import_exceptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    batch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("import_batches.id", ondelete="CASCADE"),
        index=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    tipo: Mapped[str] = mapped_column(String(30), default="sin_mapeo")
    linea: Mapped[int] = mapped_column(Integer, default=0)

    valor_crudo: Mapped[str] = mapped_column(String(400), default="")
    # El resultado de la normalización del §7.4, para poder ver por qué dos
    # textos que parecen iguales no matchearon.
    valor_normalizado: Mapped[str] = mapped_column(String(400), default="")
    destino_sugerido: Mapped[str] = mapped_column(String(40), default="")
    confianza: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0"))
    # ⚠️ OBLIGATORIO por el principio rector: «puede decidir, pero no puede
    # esconder». Una propuesta sin explicación no se puede auditar ni discutir.
    rationale: Mapped[str] = mapped_column(Text, default="")

    # pending | approved | rejected | auto_applied
    estado: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    resuelto_por: Mapped[str] = mapped_column(String(120), default="")
    resuelto_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
