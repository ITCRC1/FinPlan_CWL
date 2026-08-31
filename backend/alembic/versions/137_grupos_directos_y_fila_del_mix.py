"""CORP y GRP ya tienen canal, y el mix importado deja de partirse en dos.

Tres cosas que van juntas porque son el mismo problema visto de tres lados.

1. **CORP y GRP sin canal.** Estaban vacios a proposito desde el 2026-08-14
   («asi los tiene el owner hoy»). El 2026-08-30 el owner los decidio: CORP va
   a `Travel Agent` —le entra por agencia— y GRP a `Grupos Directos`, un canal
   NUEVO, porque el grupo directo es otro concepto y lo quiere ver aparte;
   `TAGP` ya cubre el grupo que llega por agencia. Sus noches no se cargaban:
   el importador las deja en `sin_canal` y no las escribe.

   No alcanza con editar `seed_data/market_codes.json`: `seed_market_codes.py`
   solo INSERTA los codigos que faltan y **nunca pisa el canal** de uno que ya
   existe —es del owner—, asi que en una base ya sembrada el JSON no mueve
   nada. Por eso el UPDATE va aca.

2. **Dos vocabularios de canal.** El importador del XML guardaba en
   `channel_mix_entries.channel` el canal del PMS CRUDO («Travel Agent»),
   pero la fila que el reporte ya tenia —y que la grilla editable escribe— es
   la del mix («Travel Agency»). Las noches importadas caian en filas NUEVAS y
   las de siempre se quedaban en cero, **con el total del mes cuadrando
   igual**. Se vio al cargar junio 2026: solo `OTA` parecia actualizarse,
   porque es el unico nombre que coincide en los dos vocabularios. El arreglo
   del codigo esta en `CANAL_A_MIX`; aca se reparan las filas ya escritas.

3. Se remapean **solo** las filas con `origen='xml'`. Lo cargado a mano no se
   toca: si alguien planifico un canal llamado «Website», ese es su nombre y no
   es un error que arreglar.

Revision ID: 137
Revises: 136
"""
from alembic import op
import sqlalchemy as sa

revision = "137"
down_revision = "136"
branch_labels = None
depends_on = None

# code → canal, solo si hoy esta VACIO. Nunca pisa una decision ya tomada.
CANAL_DE = {"CORP": "Travel Agent", "GRP": "Grupos Directos"}

# canal del PMS → fila del mix. Espeja `app/models/market_code.CANAL_A_MIX`;
# lo vigila `test_grupos_directos.py` para que no se separen.
A_MIX = {
    "Travel Agent": "Travel Agency",
    "Direct Client": "Direct Client + Website",
    "Website": "Direct Client + Website",
    "INHOUSE": "Other / In-House",
}
# `OTA` y `Grupos Directos` se llaman igual en los dos lados: no hay nada que mover.


def upgrade() -> None:
    con = op.get_bind()

    for code, canal in CANAL_DE.items():
        con.execute(
            sa.text("UPDATE market_codes SET canal=:c WHERE code=:k AND canal=''"),
            {"c": canal, "k": code})

    # Las filas importadas que quedaron con el nombre del PMS. Se suman contra
    # la fila destino si ya existe —«Direct Client» y «Website» caen en la
    # MISMA— y despues se borran las de origen. La unique key es
    # (scenario, month, channel, metric), asi que insertar sin sumar reventaria.
    filas = con.execute(sa.text(
        "SELECT id, scenario_id, month, channel, metric, value "
        "FROM channel_mix_entries WHERE origen='xml' AND channel IN :n"
    ).bindparams(sa.bindparam("n", expanding=True)),
        {"n": list(A_MIX)}).fetchall()

    acumulado: dict[tuple, float] = {}
    for _id, sid, mes, canal, metric, valor in filas:
        clave = (sid, mes, A_MIX[canal], metric)
        acumulado[clave] = acumulado.get(clave, 0.0) + float(valor or 0)

    for _id, *_ in filas:
        con.execute(sa.text("DELETE FROM channel_mix_entries WHERE id=:i"), {"i": _id})

    for (sid, mes, destino, metric), valor in acumulado.items():
        # ⚠️ NO se toca el `origen` de la fila destino. Si tenia algo cargado a
        # mano, sigue siendo `manual`: ese campo es lo que hace que una proxima
        # subida del XML PREGUNTE antes de pisar la correccion
        # (`channel_mix.mes_corregido_a_mano`). Marcarla `xml` al fusionar
        # apagaria ese freno en silencio y la correccion se perderia sola.
        actualizadas = con.execute(sa.text(
            "UPDATE channel_mix_entries SET value = value + :v "
            "WHERE scenario_id=:s AND month=:m AND channel=:c AND metric=:me"),
            {"v": valor, "s": sid, "m": mes, "c": destino, "me": metric}).rowcount
        if not actualizadas:
            con.execute(sa.text(
                "INSERT INTO channel_mix_entries "
                "(id, scenario_id, month, channel, metric, value, origen) "
                "VALUES (gen_random_uuid()::text, :s, :m, :c, :me, :v, 'xml')"),
                {"s": sid, "m": mes, "c": destino, "me": metric, "v": valor})


def downgrade() -> None:
    # El canal se devuelve a vacio. El remapeo de las filas NO se deshace:
    # volver a partirlas en dos vocabularios seria restaurar el bug.
    con = op.get_bind()
    for code, canal in CANAL_DE.items():
        con.execute(
            sa.text("UPDATE market_codes SET canal='' WHERE code=:k AND canal=:c"),
            {"k": code, "c": canal})
