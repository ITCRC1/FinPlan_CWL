# -*- coding: utf-8 -*-
"""Administración: 0180 es la madre, 0181 y 0184 solo llevan planilla.

Owner (2026-08-14): «0180 es el departamento madre, 0181 y 0184 son hijos; 0181
y 0184 solo tienen planilla, no tienen cuentas de gastos porque sus gastos se
postean en la 0180».

## Qué hace

1. **Saca 49 reglas de gasto** que el hijo duplicaba de la madre: 35 del `0184`
   y 14 del `0181`. Las 49 son cuentas que el `0180` YA tiene, así que el hijo
   las hereda por la cadena de padres y aterriza en la MISMA línea `OH_ADMIN` —
   pasa de modo `exact` a modo `parent` y nada más.

2. **Une el `0181` a `OH_ADMIN`.** Su planilla (17 cuentas 6xxx) y su `4901` de
   reparto apuntaban a `OH_EMPLOYEE_BENEFITS`, una línea aparte que da **0,00 en
   los 12 escenarios**. Hoy unirlo cuesta cero; el día que entre dato, mover una
   línea con plata adentro ya es caro. El `4901` va a la misma línea que sus
   débitos: el crédito de reparto tiene que netear ahí y no restarle a otro.

3. **Le corrige el nombre.** El mapeo decía «Departamento de Beneficios
   Empleados» y `DEPT_NAMES` decía «Management»: dos verdades para el mismo
   código. Manda la planilla, que es la que tiene gente — `GERENTE GENERAL` y
   `Gerencia Operaciones`. Queda «Gerencia (Management)» en los dos lados.

## Lo que NO hace, y por qué

Quedan **15 reglas de gasto en el `0181`** intactas: 7060 China, 7065 Cleaning
Supplies, 7140 Dishwashing, 7195 Flatware, 7235 Glassware, 7275 Ice, 7295
Kitchen Fuel, 7300 Kitchen Smallwares, 7310 Laundry, 7350 Linen, 7460 Paper and
Plastics, 7490 Printing, 7695 Utensils, y 5700/5701 Costo 1 y 2.

Son el juego de cuentas de un **comedor de empleados**, y las 15 existen TAMBIÉN
en la Cafetería `0220`. El `0180` no tiene ninguna de las 15. Sacarlas de acá no
las manda a Administración: las manda a **Habitaciones y a A&B por descarte**,
que es el error caro de este sistema — el GOP cuadra igual y la plata cambia de
línea sola. Repuntarlas a `OH_ADMIN` tampoco: vajilla y menaje de cocina no son
gasto de Administración.

**Falta que el owner decida** si esas 15 se van a la Cafetería `0220` o si se le
abren al `0180`. Hoy no urge: los 12 escenarios dan 0,00 en las 15.

## El P&L no se mueve

Verificado línea por línea contra los 20 escenarios de producción, con el mapeo
leído del archivo: idéntico. Los totales, con `scripts.foto_pl_totales`:
idéntico.

## El seed manda

Todo esto vive en `app/seed_data/mapping_pl.json` y en `DEPT_NAMES` de
`app/seed_department_catalog.py`, que es de donde el seed re-afirma las tablas en
CADA arranque. Esta migración NO decide nada: solo **borra lo que el seed dejó de
nombrar**, porque `seed_mapping` inserta y actualiza pero no borra lo que sobra.
Sin este borrado, las 49 reglas viejas y las 18 con el nombre viejo quedarían
vivas en la base y el `0181` sumaría en dos líneas a la vez.

Revision ID: 112
Revises: 111
"""
from alembic import op
import sqlalchemy as sa

revision = "112"
down_revision = "111"
branch_labels = None
depends_on = None

NOMBRE_VIEJO = "Departamento de Beneficios Empleados"
NOMBRE_NUEVO = "Gerencia (Management)"

# Cuentas de gasto que el hijo duplicaba de la madre 0180. Se heredan igual.
FUERA_0181 = ["7105", "7110", "7125", "7150", "7175", "7185", "7335", "7380",
              "7400", "7665", "7670", "7675", "7680", "7685"]
FUERA_0184 = ["7015", "7020", "7045", "7050", "7070", "7100", "7105", "7110",
              "7115", "7120", "7125", "7145", "7150", "7175", "7185", "7225",
              "7270", "7325", "7335", "7355", "7380", "7390", "7400", "7465",
              "7485", "7495", "7510", "7535", "7540", "7545", "7665", "7670",
              "7675", "7680", "7685"]


def upgrade() -> None:
    # 1. Las 49 duplicadas de la madre.
    for dept, cuentas in (("0181", FUERA_0181), ("0184", FUERA_0184)):
        op.execute(sa.text(
            "DELETE FROM account_mapping WHERE dept_code = :d "
            "AND account_code = ANY(:c)"
        ).bindparams(sa.bindparam("d", value=dept),
                     sa.bindparam("c", value=cuentas,
                                  type_=sa.ARRAY(sa.String))))

    # 2. Las 18 con el nombre viejo (planilla + 4901). El seed las re-inserta
    #    con `source_department = 'Gerencia (Management)'` y `OH_ADMIN`; sin
    #    borrarlas quedarían las dos versiones, porque el nombre es parte de la
    #    llave del seed y no lo puede alcanzar por UPDATE.
    #    Las 15 del comedor de empleados NO se tocan: conservan el nombre viejo
    #    a propósito, que es lo que son.
    op.execute(sa.text(
        "DELETE FROM account_mapping WHERE dept_code = '0181' "
        "AND source_department = :viejo "
        "AND (account_code LIKE '6%' OR account_code = '4901')"
    ).bindparams(viejo=NOMBRE_VIEJO))

    # 3. El nombre del departamento. `seed_department_catalog` lo re-afirma en
    #    cada arranque desde `DEPT_NAMES`; esto solo adelanta el efecto, y por
    #    eso dice EXACTAMENTE lo mismo que `DEPT_NAMES["0181"]`.
    #    `name_en` no se toca: `build_rows()` lo escribe vacío para todos, así
    #    que ponerle algo acá sería una migración que el seed revierte sola —
    #    es lo que le pasó a la 092 con 'Human Resources'.
    op.execute(sa.text(
        "UPDATE department_catalog SET dept_name = :n WHERE dept_code = '0181'"
    ).bindparams(n=NOMBRE_NUEVO))


def downgrade() -> None:
    # No se reconstruyen las 49 ni las 18: la fuente de verdad es
    # `mapping_pl.json`, y volver el archivo atrás + arrancar deja la base como
    # estaba. Escribirlas acá sería una tercera copia de la misma decisión, que
    # es exactamente el problema que la migración 097 documentó.
    op.execute(sa.text(
        "UPDATE department_catalog SET dept_name = 'Management' "
        "WHERE dept_code = '0181'"))
