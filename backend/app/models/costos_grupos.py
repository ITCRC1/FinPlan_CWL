# -*- coding: utf-8 -*-
"""Configuración del módulo de Costos para Negociación de Grupos.

**Sólo lo que FinPlan NO tenía.** El spec (`COSTOS_GRUPOS.md`) describe seis
tablas: `cfg_temporadas`, `cfg_parametros`, `fact_pl_mensual`,
`fact_overhead_mensual`, `fact_no_operativo` y `fact_volumenes`.

⚠️ **Las cuatro `fact_*` NO se crean, y es la decisión de fondo del módulo.**
Medido antes de escribir una línea:

* El P&L mensual por departamento, el overhead y los no-operativos **ya los
  produce el motor** (`compute_pl_month`). Copiarlos a una tabla sería tener
  dos fuentes del mismo número, que es exactamente cómo se separan: el día que
  alguien recalcula el escenario, la copia se queda vieja y nadie se entera.
* Los volúmenes **ya tienen su estructura**: `stat_accounts` (39 cuentas clase
  9), `statistical_entries` (escenario × cuenta × mes × depto, con `origen`) y
  `scenario_stats` (habitaciones disponibles, ocupadas y huéspedes).

Así que acá viven **la configuración** —lo que el spec llama `cfg_*`— y nada
más. Los hechos se leen del motor en `app/engine/costos_grupos.py`.

⚠️ **Lo que el inventario encontró y hay que tener presente al leer cualquier
salida de este módulo:** las 39 cuentas de estadística están **vacías**. El
spec decía que faltaban spa y tienda (§8, puntos 5-7); faltan TODAS. Lo único
que existe de verdad es habitaciones. Por eso el módulo marca cada costo
unitario con el origen de su denominador: sin eso, un piso apoyado en un
prorrateo se ve igual de firme que uno real.
"""
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Las tres temporadas del spec (§2). El mapa mes → temporada es DATO, no código:
# noviembre en MEDIA es una decisión comercial que el propio spec marca como
# revisable, y el owner puede moverla sin tocar una línea.
TEMPORADAS = ("ALTA", "MEDIA", "BAJA")


class CfgTemporada(Base):
    """Mes → temporada, con sus días abiertos.

    ⚠️ `dias_abiertos` es lo que hace que el cierre anual sea DATO y no una
    excepción escrita en el código. Verificado contra producción: el cierre es
    **octubre** —el spec lo daba por confirmar— pero **no está en todos los
    escenarios**: el Forecast Working 2026 y el Budget Final 2027 lo traen
    cerrado (10.020 hab-noche), mientras que el Budget Working 2027 y los
    Actuals lo tienen abierto (10.950).

    Esa diferencia mueve el overhead por habitación disponible de $216 a $198
    —un 9% en el piso— así que la validación 3 compara contra el escenario
    base, no contra un número escrito a mano.
    """

    __tablename__ = "cfg_temporadas"
    __table_args__ = (
        UniqueConstraint("hotel_id", "mes", name="uq_cfg_temporada"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    mes: Mapped[int] = mapped_column(Integer)                       # 1-12
    temporada: Mapped[str] = mapped_column(String(8))               # ALTA | MEDIA | BAJA
    dias: Mapped[int] = mapped_column(Integer, default=0)
    dias_abiertos: Mapped[int] = mapped_column(Integer, default=0)


class CfgParametro(Base):
    """Los parámetros del módulo, uno por fila.

    Fila por parámetro y no columnas fijas: el spec ya nombra nueve y anticipa
    más (índice estacional, umbrales de desplazamiento). Con columnas, cada
    parámetro nuevo es una migración; así es una fila.

    El valor viaja como texto y se convierte al leer, porque conviven números
    (`0.03`), enteros y opciones (`M2`, `B`, `SI`). Guardarlos tipados obligaría
    a tres columnas de valor y a saber cuál mirar.
    """

    __tablename__ = "cfg_parametros_costos"
    __table_args__ = (
        UniqueConstraint("hotel_id", "clave", name="uq_cfg_parametro_costos"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    clave: Mapped[str] = mapped_column(String(48))
    valor: Mapped[str] = mapped_column(String(64))


class CfgClasificacionCosto(Base):
    """Qué parte de una línea de gasto es variable, fija o escalonada (§3.1).

    El spec pide explícitamente que **comparta criterio con Break-Even**, que ya
    clasifica fijo/variable por cuenta y departamento (`be_cost_classification`).
    Esta tabla NO lo duplica: guarda sólo lo que Break-Even no tiene —el tercer
    tramo, el **escalonado**— y deja que el resto se lea de allá.

    Un porcentaje en cero significa «lo que diga Break-Even». Una fila acá es
    una excepción deliberada, no la norma.
    """

    __tablename__ = "cfg_clasificacion_costos"
    __table_args__ = (
        UniqueConstraint("hotel_id", "dept_code", "linea_gasto",
                         name="uq_cfg_clasificacion_costos"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    dept_code: Mapped[str] = mapped_column(String(10), default="")
    linea_gasto: Mapped[str] = mapped_column(String(120), default="")
    pct_variable: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0"))
    pct_fijo: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0"))
    pct_escalonado: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0"))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)


class CfgEscalon(Base):
    """Costos que aparecen al cruzar un umbral (§4.4).

    Sin estos, el modelo subestima grupos grandes: el guía adicional, el
    vehículo que no cabe, el turno extra de cocina, el bloque de habitaciones
    que hay que abrir. Se suman al costo del grupo **antes** del gross-up.
    """

    __tablename__ = "cfg_escalones_costos"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    dept_code: Mapped[str] = mapped_column(String(10), default="")
    driver: Mapped[str] = mapped_column(String(32))       # pax | hab_grupo | pax_tour…
    umbral: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    costo_adicional: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    descripcion: Mapped[str] = mapped_column(String(200), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CfgCanalCosto(Base):
    """Comisión por canal, y si aplica a grupos (§3.1, §4.8).

    ⚠️ `comision_pct` es **por departamento y canal**, no global, y de ahí sale
    el gross-up del §4.8. El revenue del P&L de CWL ya viene NETO de comisión de
    agencias: Habitaciones y paquetes llevan comisión embebida (factor 0.8220
    con la mezcla real), pero tienda, spa y consumos en sitio se venden directo
    —factor 1.0— y aplicarles el gross-up sería inventar un techo que no existe.
    """

    __tablename__ = "cfg_canales_costos"
    __table_args__ = (
        UniqueConstraint("hotel_id", "canal", "dept_code",
                         name="uq_cfg_canal_costos"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    canal: Mapped[str] = mapped_column(String(48))
    dept_code: Mapped[str] = mapped_column(String(10), default="")   # "" = todos
    comision_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0"))
    aplica_a_grupos: Mapped[bool] = mapped_column(Boolean, default=True)


class CfgComposicion(Base):
    """De qué líneas del P&L se compone cada concepto de costo.

    ⚠️ **Esto estaba escrito en el código y el owner pidió que fuera editable**
    (2026-08-19), a propósito de Sustainability. Tenía razón, y no sólo por ese
    caso: la composición es donde se equivoca uno, y donde cada propiedad
    difiere. Con la tabla, corregirla es una fila; en el código, es un
    despliegue.

    El caso que lo destapó: la semilla del spec daba $92,12 por habitación
    ocupada y sólo cerraba sumando `REV_SUSTAINABILITY` + `REV_MISC_OTHER` —
    en el libro de origen eran un mismo cubo. **Decisión del owner: van
    SEPARADOS.** Con eso Sustainability baja a $54,38 y «Other / Misc» pasa a
    ser su propio departamento.

    `rol` distingue las tres preguntas que el módulo hace sobre un mismo
    departamento:
      * `propio`  — el costo completo del departamento (§4.1)
      * `venta`   — sólo el costo variable, el que va al Piso 1 marginal
      * `ingreso` — su revenue, para la contribución que la Golden Rate resta
    """

    __tablename__ = "cfg_composicion_costos"
    __table_args__ = (
        UniqueConstraint("hotel_id", "concepto", "rol", "line_code",
                         name="uq_cfg_composicion_costos"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    concepto: Mapped[str] = mapped_column(String(32))     # ROOMS, FB, SUSTAINABILITY…
    rol: Mapped[str] = mapped_column(String(10))          # propio | venta | ingreso
    line_code: Mapped[str] = mapped_column(String(40))    # OPEX_ROOMS, COS_FB_FOOD…
    activa: Mapped[bool] = mapped_column(Boolean, default=True)


class CfgTarifaRack(Base):
    """El tarifario RACK de referencia para negociar grupos.

    ⚠️ **Esta tabla NO mueve ningún P&L, y es a propósito.** El módulo mide
    costo por unidad física; el precio entra sólo como TECHO de la negociación
    (spec §1: ningún piso puede depender del precio). Si estas tarifas vivieran
    en `rate_cards` del escenario, editarlas movería el ingreso del Forecast
    2026 —la base validada del módulo— y el piso se movería solo, que es
    justamente lo que la validación 6 existe para impedir.

    ⚠️ **Por MES, no por temporada.** El rack baja en temporada baja justo
    cuando el piso sube: en setiembre Agujas vale $400 contra un piso de
    $1.012. Promediar por temporada taparía exactamente el mes que duele.
    """
    __tablename__ = "cfg_tarifa_rack"
    __table_args__ = (
        UniqueConstraint("hotel_id", "room_type_code", "mes",
                         name="uq_cfg_tarifa_rack"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    # ⚠️ La llave es el CÓDIGO (BL01, BI02…), no el nombre: el código es fijo
    # por categoría y el nombre es una etiqueta que se puede renombrar.
    room_type_code: Mapped[str] = mapped_column(String(20))
    mes: Mapped[int] = mapped_column(Integer)
    rack: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    neto: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    pax: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
