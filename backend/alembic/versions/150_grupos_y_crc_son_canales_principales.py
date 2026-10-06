# -*- coding: utf-8 -*-
"""Direct groups y Costa Rica Collection pasan a ser canales principales.

Owner, 2026-10-06, sobre el resumen por canal: *«me gustaría mover Direct Groups
y Costa Rica Collection Direct como canales principales. Ellos son tan
importantes como Agencias, OTAs y Direct»*.

La migración 120 creó `canales_comision` con tres filas —TA, OTA, DIRECT— y dejó
dicho que la tabla existe **«justamente para que agregar un cuarto sea un INSERT
y no un despliegue»**. Esto es ese INSERT, más el cambio de `rueda_a` de los dos
sub-canales que pasan a colgar de los cubos nuevos.

## ⚠️ No mueve un centavo, y conviene saber por qué

El Net Factor es `Σ mix_cubo × (1 − comisión_cubo)`, donde el mix del cubo es la
SUMA de sus sub-canales y su comisión el promedio PONDERADO por ese mix. Al
multiplicar, el producto vuelve a `Σ mix_sub × (1 − comisión_sub)` — o sea que
**agrupar distinto no cambia el resultado**. Comprobado con los doce meses del
Budget 2027 de Amarena: 0.8684 con 3, 4 o 5 cubos, idéntico mes a mes.

Lo que cambia es la lectura. Hoy «Direct» mezcla cinco sub-canales con
comisiones de 0%, 10% y 20%, y muestra un promedio de 19,46% que no es el costo
de ningún canal real. Separados, Direct queda en su costo propio y los otros dos
muestran el suyo.

## Qué NO toca

`sales_channel_configs` —las filas derivadas por escenario— se queda como está.
Las escribe el APLICAR del mixer, y hasta que alguien lo corra el motor sigue
leyendo las tres filas viejas, cuyo mix sigue sumando 100%. Por eso el ingreso
no se mueve ni siquiera por un redondeo.

Revision ID: 150
Revises: 149
"""
from alembic import op
import sqlalchemy as sa

revision = "150"
down_revision = "149"
branch_labels = None
depends_on = None

#: (code del cubo nuevo, nombre, orden, codes y nombres del sub-canal que pasa a colgar)
#:
#: Se busca por `code` O por `nombre` a propósito: el code viene de cómo se
#: sembró esta propiedad y puede diferir, y el nombre es lo que se ve en
#: pantalla. Si no coincide ninguno, la fila simplemente no se actualiza y la
#: migración no rompe nada — queda el cubo creado y sin nadie colgando, que es
#: un estado válido y visible.
NUEVOS = [
    ("CRC", "CR Collection", 4, ("CRC_DIRECT",), ("Costa Rica Collection direct",)),
    ("GROUPS", "Groups", 5, ("DIR_GROUPS",), ("Direct groups",)),
]


def upgrade() -> None:
    conn = op.get_bind()
    for code, nombre, orden, codes_sub, nombres_sub in NUEVOS:
        conn.execute(
            sa.text(
                "INSERT INTO canales_comision (code, nombre, orden, activo) "
                "VALUES (:code, :nombre, :orden, true) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"code": code, "nombre": nombre, "orden": orden},
        )
        conn.execute(
            sa.text(
                "UPDATE canales_comerciales SET rueda_a = :code "
                "WHERE code = ANY(:codes) OR nombre = ANY(:nombres)"
            ),
            {"code": code, "codes": list(codes_sub), "nombres": list(nombres_sub)},
        )


def downgrade() -> None:
    conn = op.get_bind()
    # Primero se devuelven los sub-canales a DIRECT: borrar el cubo con alguien
    # colgando dejaría ese mix apuntando a un destino inexistente, y ese mix
    # **desaparece del derivado** — la suma bajaría de 100% y el Net Factor se
    # calcularía sobre una base que no es el total. Nada fallaría.
    for code, _nombre, _orden, codes_sub, nombres_sub in NUEVOS:
        conn.execute(
            sa.text(
                "UPDATE canales_comerciales SET rueda_a = 'DIRECT' "
                "WHERE code = ANY(:codes) OR nombre = ANY(:nombres)"
            ),
            {"codes": list(codes_sub), "nombres": list(nombres_sub)},
        )
        conn.execute(
            sa.text("DELETE FROM canales_comision WHERE code = :code"),
            {"code": code},
        )
