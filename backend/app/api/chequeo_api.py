# -*- coding: utf-8 -*-
"""Chequeo de la propiedad: ¿esta instalación quedó sana?

**Por qué existe (owner, 2026-08-14).** Va a sacar cuatro copias de la app, una
por hotel: Corcovado con toda su historia y las otras tres en cero. La forma en
que un clon sale mal **no da error**: la app levanta, las pantallas pintan, los
totales cuadran — y resulta que la base quedó con el `hotel_id` de Corcovado, o
que el motor del P&L no se sembró y todo el GL que se suba va a caer en ninguna
línea.

Eso solo se descubre mirando, y se descubre tarde. Esto lo pregunta de una vez.

**Es de solo lectura.** Cuenta y compara; no arregla nada. Un chequeo que además
corrige es un chequeo en el que no se puede confiar cuando dice que está todo
bien.
"""
import json
import pathlib
import re

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text

from app.auth import get_current_user
from app.db import get_session
from app.hotel_actual import HOTEL_ID, HOTEL_NAME
from app.models.hotel import Hotel
from app.textos import Idioma, t

router = APIRouter()

#: Las tablas que sostienen el motor contable. No son de ningún hotel en
#: particular: las siembra `app/seed.py` desde el JSON del repo en cada arranque.
#: Si alguna está vacía, lo que se suba después no tiene dónde caer.
#:
#: El valor es la CLAVE del texto que explica qué es esa tabla, no el texto: el
#: chequeo se lee en los dos idiomas y el nombre de la tabla no se traduce.
DEL_MOTOR = {
    "account_mapping": "chequeo.motor_account_mapping",
    "report_line_config": "chequeo.motor_report_line_config",
    "department_catalog": "chequeo.motor_department_catalog",
    "stat_accounts": "chequeo.motor_stat_accounts",
    "market_codes": "chequeo.motor_market_codes",
    "canales_comerciales": "chequeo.motor_canales_comerciales",
}

#: ATENCION (owner, 2026-08-20: «que no pierda estructura»). El control de
#: arriba pregunta «esta vacia?». **Vacia se nota; INCOMPLETA no**:
#: `account_mapping` con tres filas de 1.099 lo pasaba, y esas 1.096 cuentas que
#: faltan no fallan — caen en ninguna linea del P&L. El inventario de
#: `app/estructura.py` compara contra lo ESPERADO, leyendo la misma fuente que
#: lee el seed, y por eso no hay ni un numero escrito aca.

#: Lo que carga el owner. En una propiedad recién abierta tiene que dar CERO;
#: en la copia de Corcovado, decenas de miles.
DEL_NEGOCIO = [
    "scenarios", "pl_lines", "actual_entries", "revenue_entries", "opex_entries",
    "cost_entries", "payroll_positions", "payroll_concept_entries", "rate_cards",
    "occupancy_budgets", "allocation_entries", "statistical_entries",
    "pl_manual_inputs", "capital_projects",
]

#: Tablas con `hotel_id`. Una fila de otro hotel acá es contaminación: se veria
#: normal en pantalla y estaría sumando datos que no son de esta propiedad.
CON_HOTEL = [
    "scenarios", "room_type_configs", "rate_cards", "occupancy_budgets",
    "opex_entries", "cost_entries", "payroll_positions", "actual_entries",
    "exchange_rates", "sales_channel_configs", "package_configs",
    "capital_projects", "nonop_entries", "revenue_entries",
]

#: ⚠️ **Las que NO se llavean por `hotel_id`.** Owners Q usa `entidad`, así que
#: el control de arriba —`WHERE hotel_id <> :h`— nunca las miró. Medido antes de
#: clonar: ocho endpoints tenían «CWL» clavado como entidad por defecto, y una
#: propiedad nueva habría guardado su capacidad y sus fotos del reporte bajo la
#: entidad de Corcovado **sin que ningún control lo dijera**.
CON_ENTIDAD = ["capacidad", "report_snapshots"]


#: Campos del mapeo que solo DOCUMENTAN: si cambian, el reporte da lo mismo.
#: Todo lo demas mueve plata entre lineas del P&L y va en rojo.
SOLO_DOCUMENTAN = {"notes", "account_name_example"}


#: La carpeta de migraciones de ESTE código.
VERSIONES = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _head_del_repo() -> str:
    """La última migración que trae ESTE código."""
    nums = [int(m.group(1)) for p in VERSIONES.glob("*.py")
            if (m := re.match(r"^(\d+)_", p.name))]
    return str(max(nums)) if nums else ""


def _r(clave, titulo, estado, detalle, porque="", que_hacer="") -> dict:
    """Un renglón del chequeo.

    ⚠️ `clave` identifica la COMPROBACIÓN, no el mensaje: «identidad» sale una
    vez como error y otra como aviso, con textos distintos. Por eso las claves
    del catálogo de textos son dos (`chequeo.identidad_no_existe` y
    `chequeo.identidad_varios`) y esta sigue siendo una: el frontend la usa para
    reconocer el chequeo, y eso no puede cambiar según el resultado.
    """
    return {"clave": clave, "titulo": titulo, "estado": estado,
            "detalle": detalle, "porque": porque, "que_hacer": que_hacer}


async def _columna_de_hotel(s, tabla: str) -> str | None:
    """Con que columna se llavea esta tabla, si es que se llavea con alguna.

    Se lee del ESQUEMA, no de una lista escrita aca: una tabla nueva se cuenta
    bien sin que nadie se acuerde de agregarla. Y de paso resuelve que Owners Q
    use `entidad` donde el resto usa `hotel_id`, que fue exactamente el punto
    ciego que se encontro antes de clonar.
    """
    try:
        cols = {r[0] for r in (await s.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :t"), {"t": tabla})).all()}
    except Exception:
        return None
    for c in ("hotel_id", "property_id", "entidad"):
        if c in cols:
            return c
    return None


async def _cuanto_hay(s, tabla: str) -> int | None:
    """Cuantas filas de ESTA propiedad hay. `None` = no se pudo mirar.

    ATENCION: `None` no es cero. Una tabla que no existe y una tabla vacia se
    ven igual en un contador y significan cosas distintas — una es un despliegue
    a medias, la otra es trabajo que falta.
    """
    col = await _columna_de_hotel(s, tabla)
    try:
        if col:
            # `property_id IS NULL` cuenta: el universo del Break-Even es del
            # grupo y se guarda sin propiedad. Excluirlo diria que falta todo.
            return (await s.execute(text(
                f"SELECT count(*) FROM {tabla} "
                f"WHERE {col} = :h OR {col} IS NULL"), {"h": HOTEL_ID})).scalar() or 0
        return (await s.execute(text(f"SELECT count(*) FROM {tabla}"))).scalar() or 0
    except Exception:
        return None


async def _cuenta(s, tabla: str) -> int | None:
    """`None` si la tabla no existe — no es lo mismo que estar vacía."""
    try:
        return (await s.execute(text(f"SELECT count(*) FROM {tabla}"))).scalar() or 0
    except Exception:
        return None


@router.get("/chequeo/")
async def chequeo(_=Depends(get_current_user), idioma: str = Idioma):
    """Todo lo que puede haber salido mal en una instalación, preguntado."""
    checks: list[dict] = []
    async with get_session() as s:

        # ── 1. La identidad ──────────────────────────────────────────────────
        hoteles = list((await s.execute(select(Hotel))).scalars())
        ids = sorted(h.id for h in hoteles)
        mio = next((h for h in hoteles if h.id == HOTEL_ID), None)
        titulo_identidad = t(idioma, "chequeo.identidad_titulo")
        if mio is None:
            checks.append(_r(
                "identidad", titulo_identidad, "error",
                t(idioma, "chequeo.identidad_no_existe", hotel_id=HOTEL_ID,
                  ids=", ".join(ids) or t(idioma, "chequeo.ninguno")),
                t(idioma, "chequeo.identidad_no_existe_porque"),
                t(idioma, "chequeo.identidad_no_existe_que_hacer")))
        elif len(hoteles) > 1:
            checks.append(_r(
                "identidad", titulo_identidad, "aviso",
                t(idioma, "chequeo.identidad_varios", hotel_id=HOTEL_ID,
                  nombre=mio.name, n=len(hoteles), ids=", ".join(ids)),
                t(idioma, "chequeo.identidad_varios_porque")))
        else:
            nota = ""
            if mio.name != HOTEL_NAME:
                nota = t(idioma, "chequeo.identidad_ok_nota",
                         en_base=mio.name, en_entorno=HOTEL_NAME)
            checks.append(_r(
                "identidad", titulo_identidad, "ok",
                t(idioma, "chequeo.identidad_ok", hotel_id=HOTEL_ID,
                  nombre=mio.name, rooms=mio.rooms,
                  tc=f"{float(mio.tc_usd_default):,.2f}", nota=nota)))

        # ── 2. Datos de otro hotel ───────────────────────────────────────────
        intrusos: dict[str, int] = {}
        for tabla in CON_HOTEL:
            try:
                n = (await s.execute(text(
                    f"SELECT count(*) FROM {tabla} WHERE hotel_id <> :h"),
                    {"h": HOTEL_ID})).scalar() or 0
            except Exception:
                continue
            if n:
                intrusos[tabla] = n
        # Las de Owners Q, que se llavean por `entidad` y no por `hotel_id`.
        for tabla in CON_ENTIDAD:
            try:
                n = (await s.execute(text(
                    f"SELECT count(*) FROM {tabla} WHERE entidad <> :h"),
                    {"h": HOTEL_ID})).scalar() or 0
            except Exception:
                continue
            if n:
                intrusos[tabla] = n

        titulo_contaminacion = t(idioma, "chequeo.contaminacion_titulo")
        if intrusos:
            checks.append(_r(
                "contaminacion", titulo_contaminacion, "error",
                t(idioma, "chequeo.contaminacion_hay", tablas=", ".join(
                    f"{tabla} ({n})" for tabla, n in sorted(intrusos.items()))),
                t(idioma, "chequeo.contaminacion_hay_porque"),
                t(idioma, "chequeo.contaminacion_hay_que_hacer")))
        else:
            checks.append(_r(
                "contaminacion", titulo_contaminacion, "ok",
                t(idioma, "chequeo.contaminacion_ok")))

        # ── 3. El motor contable ─────────────────────────────────────────────
        vacias, total_motor = [], 0
        for tabla, clave_que_es in DEL_MOTOR.items():
            n = await _cuenta(s, tabla)
            if n is None or n == 0:
                vacias.append(f"{tabla} ({t(idioma, clave_que_es)})")
            else:
                total_motor += n
        titulo_motor = t(idioma, "chequeo.motor_titulo")
        if vacias:
            checks.append(_r(
                "motor", titulo_motor, "error",
                t(idioma, "chequeo.motor_vacio", tablas="; ".join(vacias)),
                t(idioma, "chequeo.motor_vacio_porque"),
                t(idioma, "chequeo.motor_vacio_que_hacer")))
        else:
            checks.append(_r(
                "motor", titulo_motor, "ok",
                t(idioma, "chequeo.motor_ok", n=f"{total_motor:,}"),
                t(idioma, "chequeo.motor_ok_porque")))

        # ── 3b. La estructura, medida contra lo ESPERADO ─────────────
        #
        # Owner, 2026-08-20: «que no pierda estructura». Lo de arriba dice si
        # una tabla tiene algo; esto dice si tiene TODO. Y separa las dos
        # familias, que no significan lo mismo: lo del grupo faltando es un
        # despliegue roto; lo de la propiedad faltando es trabajo por hacer.
        from app.estructura import GRUPO, INVENTARIO, PROPIEDAD

        faltantes: dict[str, list[str]] = {GRUPO: [], PROPIEDAD: []}
        sin_verificar: list[str] = []
        de_mas: list[str] = []
        completos: dict[str, int] = {GRUPO: 0, PROPIEDAD: 0}
        for d in INVENTARIO:
            try:
                esperado = d.esperado()
            except Exception:
                # La fuente no se pudo leer. No se da por buena ni por mala.
                sin_verificar.append(f"{d.tabla} ({d.fuente})")
                continue
            hay = await _cuanto_hay(s, d.tabla)
            if hay is None:
                sin_verificar.append(f"{d.tabla} ({d.fuente})")
            elif esperado and hay < esperado:
                faltantes[d.familia].append(
                    f"{d.tabla}: {hay:,}/{esperado:,} ← {d.fuente}")
            elif d.familia == GRUPO and hay > esperado:
                # ATENCION: de MAS tampoco es neutro. Son filas que alguien
                # agrego a mano en la app y que el repo no puede reproducir:
                # si esta base se reconstruye, se pierden y nadie lo dice. En
                # Corcovado son los departamentos 0115 Villas y 0116
                # Residencias. No es un error —la app deja agregarlos a
                # proposito— pero tiene que estar dicho.
                de_mas.append(f"{d.tabla}: {hay - esperado}")
                completos[d.familia] += 1
            elif d.familia == PROPIEDAD and not hay:
                # ATENCION: esto lo encontro el ensayo del clon el 2026-08-20.
                # Una propiedad sin carpeta de semillas espera CERO, asi que
                # `hay < esperado` nunca se cumplia y el chequeo contestaba
                # «las 5 piezas propias estan cargadas» **con la base vacia**.
                # Un control que solo puede dar verde no es un control.
                #
                # Para lo de la propiedad la pregunta no es «llego a lo
                # esperado» sino «hay ALGO»: cero es justamente la lista de lo
                # que esta propiedad todavia debe.
                faltantes[d.familia].append(f"{d.tabla} ← {d.fuente}")
            else:
                completos[d.familia] += 1

        titulo_estructura = t(idioma, "chequeo.estructura_titulo")
        if faltantes[GRUPO]:
            checks.append(_r(
                "estructura", titulo_estructura, "error",
                t(idioma, "chequeo.estructura_incompleta",
                  tablas="; ".join(faltantes[GRUPO])),
                t(idioma, "chequeo.estructura_incompleta_porque"),
                t(idioma, "chequeo.estructura_incompleta_que_hacer")))
        elif sin_verificar:
            # ATENCION: tres estados. «No se pudo mirar» NO es «esta bien» —
            # este proyecto ya conto catorce presupuestos como cuadrados sin
            # haber comparado nada.
            checks.append(_r(
                "estructura", titulo_estructura, "aviso",
                t(idioma, "chequeo.estructura_sin_verificar",
                  n=completos[GRUPO], tablas="; ".join(sin_verificar)),
                t(idioma, "chequeo.estructura_sin_verificar_porque"),
                t(idioma, "chequeo.estructura_sin_verificar_que_hacer")))
        else:
            checks.append(_r(
                "estructura", titulo_estructura, "ok",
                t(idioma, "chequeo.estructura_ok", n=completos[GRUPO])
                + (" " + t(idioma, "chequeo.estructura_de_mas",
                           tablas="; ".join(de_mas)) if de_mas else ""),
                t(idioma, "chequeo.estructura_ok_porque")
                + (" " + t(idioma, "chequeo.estructura_de_mas_porque") if de_mas else "")))

        # ── 3c. Lo que le toca cargar a ESTA propiedad ─────────────────
        #
        # Nunca en rojo: en una propiedad recien abierta falta A PROPOSITO.
        # Pintarlo de rojo el dia uno enseñaria a ignorar el rojo. Lo que si
        # hace es NOMBRARLO, para que no se descubra tarde y en cero.
        # Y los archivos de arranque, que no llenan tablas pero son estructura
        # igual: sin ellos la propiedad abre esas pantallas en blanco, y en
        # blanco no explica por que.
        from app.estructura import semillas_de_la_propiedad

        _tiene, sin_archivo = semillas_de_la_propiedad()
        if sin_archivo:
            faltantes[PROPIEDAD].append(
                t(idioma, "chequeo.propiedad_sin_archivos",
                  n=len(sin_archivo), cuales=", ".join(sin_archivo)))

        titulo_pendiente = t(idioma, "chequeo.propiedad_titulo")
        if faltantes[PROPIEDAD]:
            checks.append(_r(
                "estructura_propiedad", titulo_pendiente, "aviso",
                t(idioma, "chequeo.propiedad_falta",
                  tablas="; ".join(faltantes[PROPIEDAD])),
                t(idioma, "chequeo.propiedad_falta_porque"),
                t(idioma, "chequeo.propiedad_falta_que_hacer")))
        else:
            checks.append(_r(
                "estructura_propiedad", titulo_pendiente, "ok",
                t(idioma, "chequeo.propiedad_ok", n=completos[PROPIEDAD])))

        # ── 3d. El mapeo del repo, APLICADO ──────────────────────────
        #
        # ATENCION: esto lo encontro el owner preguntando «¿de verdad quedo
        # solido?», el 2026-08-20. El conteo cuadraba (1.099 = 1.099) y aun asi
        # **la siembra del mapeo se caia en cada despliegue**: la clave del seed
        # tenia cuatro columnas y la restriccion de la tabla cinco, asi que las
        # dos reglas de la 7120 (con vigencia distinta) se veian como una. El
        # `IntegrityError` revertia el lote entero y el `try/except` lo dejaba en
        # una linea de log.
        #
        # Contar no alcanzaba. Esto compara CONTENIDO: si alguien cambia el JSON
        # y produccion no lo toma, se ve aca — y no en el reporte, seis meses
        # despues, con los numeros ya enviados.
        titulo_mapeo = t(idioma, "chequeo.mapeo_titulo")
        try:
            from app.models.mapping import AccountMapping, ReportLineConfig
            from app.seed_mapping import ARCHIVO, _clave_linea, _clave_mapeo

            datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
            faltan, distintas, documentales = [], [], []
            for modelo, clave, bloque_json, etiqueta in (
                (ReportLineConfig, _clave_linea, "report_line_config", "línea"),
                (AccountMapping, _clave_mapeo, "account_mapping", "regla"),
            ):
                en_base = {clave(o): o for o in
                           (await s.execute(select(modelo))).scalars()}
                for fila in datos[bloque_json]:
                    o = en_base.get(clave(fila))
                    if o is None:
                        faltan.append(f"{etiqueta} {clave(fila)}")
                        continue
                    # Solo los campos que el archivo menciona: lo que la
                    # propiedad agrego por su cuenta no es una diferencia.
                    difs = [k for k, v in fila.items()
                            if (getattr(o, k, None) or None) != (v or None)]
                    if not difs:
                        continue
                    # ATENCION: se separa lo que MUEVE PLATA de lo que solo
                    # documenta. Las 29 diferencias que aparecieron el
                    # 2026-08-20 eran todas `notes`. Marcarlas en rojo junto a
                    # un cambio de linea del P&L enseñaria a ignorar el rojo, y
                    # el rojo hace falta para lo otro: mover UNA cuenta
                    # re-expreso 102 lineas del reporte sin que ningun total
                    # avisara.
                    if [k for k in difs if k not in SOLO_DOCUMENTAN]:
                        distintas.append(f"{etiqueta} {clave(fila)} [{','.join(difs)}]")
                    else:
                        documentales.append(f"{etiqueta} {clave(fila)}")
        except Exception as e:                       # pragma: no cover
            faltan, distintas, documentales = None, None, None
            detalle_error = str(e)[:200]

        if faltan is None:
            checks.append(_r(
                "mapeo", titulo_mapeo, "aviso",
                t(idioma, "chequeo.mapeo_no_se_pudo", error=detalle_error),
                t(idioma, "chequeo.mapeo_no_se_pudo_porque")))
        elif faltan or distintas:
            checks.append(_r(
                "mapeo", titulo_mapeo, "error",
                t(idioma, "chequeo.mapeo_desviado",
                  faltan=len(faltan), distintas=len(distintas),
                  ejemplos="; ".join((faltan + distintas)[:5])),
                t(idioma, "chequeo.mapeo_desviado_porque"),
                t(idioma, "chequeo.mapeo_desviado_que_hacer")))
        elif documentales:
            checks.append(_r(
                "mapeo", titulo_mapeo, "aviso",
                t(idioma, "chequeo.mapeo_documental", n=len(documentales)),
                t(idioma, "chequeo.mapeo_documental_porque"),
                t(idioma, "chequeo.mapeo_desviado_que_hacer")))
        else:
            checks.append(_r(
                "mapeo", titulo_mapeo, "ok",
                t(idioma, "chequeo.mapeo_ok",
                  n=len(datos["report_line_config"]) + len(datos["account_mapping"])),
                t(idioma, "chequeo.mapeo_ok_porque")))

        # ── 4. Las migraciones ───────────────────────────────────────────────
        head = _head_del_repo()
        try:
            en_base = (await s.execute(
                text("SELECT version_num FROM alembic_version"))).scalar() or ""
        except Exception:
            en_base = ""
        titulo_migraciones = t(idioma, "chequeo.migraciones_titulo")
        if not en_base:
            checks.append(_r(
                "migraciones", titulo_migraciones, "error",
                t(idioma, "chequeo.migraciones_sin_tabla"),
                t(idioma, "chequeo.migraciones_sin_tabla_porque"),
                t(idioma, "chequeo.migraciones_sin_tabla_que_hacer")))
        elif head and en_base != head:
            checks.append(_r(
                "migraciones", titulo_migraciones, "aviso",
                t(idioma, "chequeo.migraciones_atrasada",
                  en_base=en_base, head=head),
                t(idioma, "chequeo.migraciones_atrasada_porque"),
                t(idioma, "chequeo.migraciones_atrasada_que_hacer")))
        else:
            checks.append(_r("migraciones", titulo_migraciones, "ok",
                             t(idioma, "chequeo.migraciones_ok", en_base=en_base)))

        # ── 5. Tipos de habitación ───────────────────────────────────────────
        tipos = await _cuenta(s, "room_type_configs")
        titulo_tipos = t(idioma, "chequeo.tipos_titulo")
        if not tipos:
            checks.append(_r(
                "tipos", titulo_tipos, "aviso",
                t(idioma, "chequeo.tipos_ninguno"),
                t(idioma, "chequeo.tipos_ninguno_porque"),
                t(idioma, "chequeo.tipos_ninguno_que_hacer")))
        else:
            checks.append(_r("tipos", titulo_tipos, "ok",
                             t(idioma, "chequeo.tipos_ok", n=tipos)))

        # ── 5b. La ficha del hotel contra los tipos ──────────────────────────
        #
        # Se encontró así, corriendo este chequeo en Corcovado el 2026-08-14: la
        # ficha decía 30 habitaciones y los tipos activos sumaban 33 (se
        # agregaron Villas Deluxe y Residencia después). Ninguna pantalla lo
        # delataba.
        if tipos:
            try:
                unidades = (await s.execute(text(
                    "SELECT coalesce(sum(units), 0) FROM room_type_configs "
                    "WHERE hotel_id = :h AND active"), {"h": HOTEL_ID})).scalar() or 0
            except Exception:
                unidades = None
            fichadas = mio.rooms if mio else None
            titulo_inventario = t(idioma, "chequeo.inventario_titulo")
            if unidades is not None and fichadas is not None and unidades != fichadas:
                checks.append(_r(
                    "inventario", titulo_inventario, "aviso",
                    t(idioma, "chequeo.inventario_difiere",
                      fichadas=fichadas, unidades=unidades),
                    t(idioma, "chequeo.inventario_difiere_porque",
                      unidades=unidades),
                    t(idioma, "chequeo.inventario_difiere_que_hacer")))
            elif unidades is not None:
                checks.append(_r(
                    "inventario", titulo_inventario, "ok",
                    t(idioma, "chequeo.inventario_ok", unidades=unidades)))

        # ── 6. Usuarios ──────────────────────────────────────────────────────
        usuarios = await _cuenta(s, "users")
        titulo_usuarios = t(idioma, "chequeo.usuarios_titulo")
        if not usuarios:
            checks.append(_r(
                "usuarios", titulo_usuarios, "aviso",
                t(idioma, "chequeo.usuarios_ninguno"),
                t(idioma, "chequeo.usuarios_ninguno_porque"),
                t(idioma, "chequeo.usuarios_ninguno_que_hacer")))
        else:
            checks.append(_r("usuarios", titulo_usuarios, "ok",
                             t(idioma, "chequeo.usuarios_ok", n=usuarios)))

        # ── 7. El mix de canales cierra ──────────────────────────────────────
        try:
            from app.engine import mixer_canales as mixer
            from app.models.canal_comercial import CanalComercial
            canales = list((await s.execute(select(CanalComercial).where(
                CanalComercial.activo.is_(True)))).scalars())
            suma = float(mixer.suma_del_mix(canales))
            if canales and not mixer.mix_cierra(canales):
                checks.append(_r(
                    "mix", t(idioma, "chequeo.mix_titulo"), "aviso",
                    t(idioma, "chequeo.mix_no_cierra", suma=f"{suma:.1%}"),
                    t(idioma, "chequeo.mix_no_cierra_porque"),
                    t(idioma, "chequeo.mix_no_cierra_que_hacer")))
            else:
                checks.append(_r("mix", t(idioma, "chequeo.mix_titulo"), "ok",
                                 t(idioma, "chequeo.mix_ok", suma=f"{suma:.0%}")))
        except Exception as e:  # noqa: BLE001
            checks.append(_r("mix", t(idioma, "chequeo.mix_titulo"), "aviso",
                             t(idioma, "chequeo.mix_no_verificable",
                               error=type(e).__name__)))

        # ── 8. El dato de negocio, informativo ───────────────────────────────
        negocio = {}
        for tabla in DEL_NEGOCIO:
            n = await _cuenta(s, tabla)
            if n:
                negocio[tabla] = n
        total_negocio = sum(negocio.values())
        # El desglose son nombres de tabla y conteos: no se traduce nada.
        detalle_negocio = (
            f" ({', '.join(f'{tabla} {n:,}' for tabla, n in sorted(negocio.items(), key=lambda x: -x[1])[:6])})"
            if negocio else "")
        checks.append(_r(
            "negocio", t(idioma, "chequeo.negocio_titulo"), "info",
            t(idioma, "chequeo.negocio", n=f"{total_negocio:,}",
              detalle=detalle_negocio),
            t(idioma, "chequeo.negocio_porque")))

    orden = {"error": 0, "aviso": 1, "ok": 2, "info": 3}
    checks.sort(key=lambda c: orden.get(c["estado"], 9))
    return {
        "hotel_id": HOTEL_ID,
        "hotel_name": HOTEL_NAME,
        "errores": sum(1 for c in checks if c["estado"] == "error"),
        "avisos": sum(1 for c in checks if c["estado"] == "aviso"),
        "chequeos": checks,
    }
