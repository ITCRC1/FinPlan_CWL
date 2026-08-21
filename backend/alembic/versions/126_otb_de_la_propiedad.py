# -*- coding: utf-8 -*-
"""El On the Books es de la PROPIEDAD, no del escenario.

**La regla (owner, 2026-08-18).** «El escenario es solo una referencia
comparativa, pero no tiene nada que ver con las subidas.»

Lo que entra por el XML de Opera son las reservas que YA existen: un hecho de
la propiedad. El escenario es contra qué se comparan, nada más. Pero las tres
tablas del OTB estaban llaveadas por `scenario_id`, con dos consecuencias:

1. **El dato quedaba partido.** Medido en producción antes de migrar: los
   cortes 24 al 28 vivían en el *Actual 2026* y el corte 34 en el
   *Budget 2027 · Final*. Subir el XML teniendo elegido un presupuesto dejaba
   las reservas ahí, invisibles desde cualquier otro escenario.
2. **Borrar un escenario se llevaba las reservas puestas.** El FK tenía
   `ON DELETE CASCADE`: eliminar un presupuesto borraba un hecho de Opera que
   no le pertenecía.

**Qué hace.**

- Agrega `hotel_id` a `on_the_books_entries`, `otb_daily_occ` y
  `otb_week_params`, y lo rellena desde el escenario de cada fila.
- Mueve la llave única de (scenario, …) a (hotel, …). Se midió ANTES: en CWL
  hay 86 filas en dos escenarios y **cero choques** de (corte, año, mes), así
  que la fusión no pierde ni pisa nada. Igual verifica los duplicados y falla
  ruidosamente si aparecen en otra base — fusionar en silencio perdería filas.
- `scenario_id` pasa a NULLABLE y el FK se **recrea** con `ON DELETE SET NULL`:
  queda como rastro de desde dónde se subió, no como dueño del dato.

⚠️ **Los DROP van con `IF EXISTS` y en SQL crudo, a propósito.** En Postgres un
DDL que falla aborta la transacción entera, así que un `try/except` alrededor de
`op.drop_constraint` no protege nada: se traga el error de Python y deja la
transacción muerta para todo lo que venga después. `IF EXISTS` no falla nunca.
"""
from alembic import op
import sqlalchemy as sa

revision = "126"
down_revision = "125"
branch_labels = None
depends_on = None

#: tabla -> (llave única vieja, columnas que completan la llave, llave nueva)
TABLAS = {
    "on_the_books_entries": ("uq_otb_scenario_week_year_month",
                             ["week", "year", "month"],
                             "uq_otb_hotel_week_year_month"),
    "otb_daily_occ": ("uq_dailyocc_sc_wk_yr_mo_dy",
                      ["week", "year", "month", "day"],
                      "uq_dailyocc_hotel_wk_yr_mo_dy"),
    "otb_week_params": ("uq_otbparam_scenario_week",
                        ["week"],
                        "uq_otbparam_hotel_week"),
}


def upgrade() -> None:
    conn = op.get_bind()
    pg = conn.dialect.name == "postgresql"

    for tabla, (uq_viejo, cols, uq_nuevo) in TABLAS.items():
        op.add_column(tabla, sa.Column("hotel_id", sa.String(10), nullable=True))

        # El hotel sale del escenario donde estaba guardada la fila.
        conn.execute(sa.text(
            f"UPDATE {tabla} SET hotel_id = ("
            f"  SELECT s.hotel_id FROM scenarios s WHERE s.id = {tabla}.scenario_id)"
            f" WHERE hotel_id IS NULL"))

        # Filas cuyo escenario ya no existe: no hay de dónde sacar el hotel y no
        # se puede adivinar. Son huérfanas por definición.
        huerfanas = conn.execute(sa.text(
            f"SELECT COUNT(*) FROM {tabla} WHERE hotel_id IS NULL")).scalar() or 0
        if huerfanas:
            conn.execute(sa.text(f"DELETE FROM {tabla} WHERE hotel_id IS NULL"))

        # ⚠️ Verificar ANTES de crear la llave. Si dos escenarios de la misma
        # propiedad tuvieran la misma llave, fusionar PERDERÍA una de las dos
        # filas en silencio. En CWL son cero; en otra base, que falle acá.
        llave = ", ".join(["hotel_id"] + cols)
        dup = conn.execute(sa.text(
            f"SELECT COUNT(*) FROM (SELECT {llave} FROM {tabla}"
            f" GROUP BY {llave} HAVING COUNT(*) > 1) d")).scalar() or 0
        if dup:
            raise RuntimeError(
                f"{tabla}: {dup} llaves ({llave}) repetidas entre escenarios de la "
                f"misma propiedad. Fusionar perdería filas. Resolvelos a mano "
                f"antes de correr la 126.")

        op.alter_column(tabla, "hotel_id", existing_type=sa.String(10), nullable=False)
        op.create_index(f"ix_{tabla}_hotel_id", tabla, ["hotel_id"])

        if pg:
            conn.execute(sa.text(f"ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS {uq_viejo}"))
        op.create_unique_constraint(uq_nuevo, tabla, ["hotel_id"] + cols)

        # El escenario deja de ser dueño y pasa a rastro de origen. Cambiar el
        # ondelete NO se logra con alter_column: hay que rehacer el FK. Sin
        # esto, el modelo diría SET NULL y la base seguiría borrando en cascada.
        op.alter_column(tabla, "scenario_id", existing_type=sa.String(36), nullable=True)
        if pg:
            conn.execute(sa.text(
                f"ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS {tabla}_scenario_id_fkey"))
            conn.execute(sa.text(
                f"ALTER TABLE {tabla} ADD CONSTRAINT {tabla}_scenario_id_fkey"
                f" FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE SET NULL"))


def downgrade() -> None:
    conn = op.get_bind()
    pg = conn.dialect.name == "postgresql"
    for tabla, (uq_viejo, cols, uq_nuevo) in TABLAS.items():
        if pg:
            conn.execute(sa.text(
                f"ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS {tabla}_scenario_id_fkey"))
            conn.execute(sa.text(
                f"ALTER TABLE {tabla} ADD CONSTRAINT {tabla}_scenario_id_fkey"
                f" FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE"))
            conn.execute(sa.text(f"ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS {uq_nuevo}"))
        op.create_unique_constraint(uq_viejo, tabla, ["scenario_id"] + cols)
        op.drop_index(f"ix_{tabla}_hotel_id", tabla)
        op.drop_column(tabla, "hotel_id")
