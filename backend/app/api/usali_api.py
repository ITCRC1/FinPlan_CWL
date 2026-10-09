# -*- coding: utf-8 -*-
"""El USALI dentro de la aplicación: subirlo y consultarlo.

Owner, 2026-10-08: *«yo quiero subir el pdf y que el documento viva en la app y
se use para análisis»*.

Esta es la **etapa 1** de tres, y conviene saber qué hace y qué todavía no:

1. **El documento vive acá** (esto). Se sube, se lee, se guarda y se consulta.
   Todavía NO marca nada.
2. **El puente** — cada cuenta de Integrity apareada con su cuenta USALI. Sin
   eso el catálogo no puede tocar un asiento: el libro habla por nombre
   —«Rooms / Operating Supplies»— y la contabilidad por número —`7400-0110`—.
3. **Las reglas** — recién ahí la auditoría compara el detalle contra el
   estándar.

El orden no es capricho. Una regla nueva que marca cien cosas el primer mes no
se revisa: se ignora, y después nadie vuelve a abrir la pantalla. Con las etapas
1 y 2 hechas, cuando la 3 marque algo se va a poder decir por qué.
"""
from __future__ import annotations

import hashlib
import json
import re

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy import delete as sa_delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_admin, get_current_user
from app.db import get_db
from app.errores import ErrorApi
from app.hotel_actual import HOTEL_ID
from app.importers.registro_dep import registro_de_subida
from app.models.usali import (UsaliDefinicion, UsaliDocumento, UsaliItem,
                              UsaliRenglon)

router = APIRouter(tags=["usali"])

#: Un archivo de 391 páginas pesa 2,8 MB. El tope deja lugar a una edición más
#: grande y corta cualquier cosa que claramente no sea el libro.
TOPE_MB = 40


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


@router.get("/usali/estado/")
async def estado(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Qué hay cargado. La pantalla lo consulta antes de ofrecer la búsqueda."""
    doc = (await db.execute(select(UsaliDocumento)
                            .where(UsaliDocumento.hotel_id == HOTEL_ID)
                            .order_by(UsaliDocumento.subido_en.desc())
                            .limit(1))).scalars().first()
    if doc is None:
        return {"hay": False}
    schedules = [
        {"schedule": s, "items": n} for s, n in (await db.execute(
            select(UsaliItem.schedule, func.count())
            .where(UsaliItem.hotel_id == HOTEL_ID)
            .group_by(UsaliItem.schedule)
            .order_by(func.count().desc()))).all()]
    return {
        "hay": True,
        "archivo": doc.archivo,
        "paginas": doc.paginas,
        "paginas_con_texto": doc.paginas_con_texto,
        "items": doc.items,
        "items_confirmados": doc.items_confirmados,
        "definiciones": doc.definiciones,
        "renglones": doc.renglones,
        "cruce": json.loads(doc.cruce or "{}"),
        "subido_en": doc.subido_en.isoformat() if doc.subido_en else None,
        "subido_por": doc.subido_por,
        "schedules": schedules,
    }


# Toda puerta que recibe un archivo y escribe queda registrada: meses
# despues, «¿de que archivo salio este catalogo?» tiene que poder
# contestarse sin preguntarle a nadie.
@router.post("/usali/subir/", dependencies=[Depends(registro_de_subida)])
async def subir(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_admin),
):
    """Sube el PDF, lo lee y reemplaza lo que hubiera.

    ⚠️ **Reemplaza, no acumula.** Igual que el mayor: la llave de negocio es la
    propiedad, y subir otra edición le cae encima a la anterior. Dos ediciones
    conviviendo serían dos estándares para la misma cuenta, y ninguna pantalla
    podría decir cuál manda.
    """
    from app.importers.usali_pdf import leer_pdf

    crudo = await file.read()
    if not crudo:
        raise ErrorApi(422, "usali.archivo_vacio")
    if len(crudo) > TOPE_MB * 1024 * 1024:
        raise ErrorApi(422, "usali.archivo_grande", tope=TOPE_MB)
    if not crudo[:5].startswith(b"%PDF"):
        raise ErrorApi(422, "usali.no_es_pdf")

    try:
        lectura = leer_pdf(crudo)
    except Exception as e:                       # pragma: no cover - defensivo
        raise ErrorApi(422, "usali.no_se_pudo_leer", detalle=str(e)[:200])

    if not lectura.catalogo:
        # Un PDF escaneado da cero entradas. Decirlo es la diferencia entre
        # «su archivo es una imagen» y una pantalla vacía sin explicación.
        raise ErrorApi(
            422, "usali.sin_entradas",
            paginas=lectura.paginas, con_texto=lectura.paginas_con_texto)

    # ── reemplazo, en una sola transacción ────────────────────────────────
    for modelo in (UsaliItem, UsaliDefinicion, UsaliRenglon,
                   UsaliDocumento):
        await db.execute(sa_delete(modelo).where(modelo.hotel_id == HOTEL_ID))

    db.add(UsaliDocumento(
        hotel_id=HOTEL_ID, archivo=file.filename or "usali.pdf",
        checksum=hashlib.sha256(crudo).hexdigest(),
        paginas=lectura.paginas, paginas_con_texto=lectura.paginas_con_texto,
        items=len(lectura.catalogo),
        items_confirmados=sum(1 for c in lectura.catalogo
                              if c.confianza == "confirmado"),
        definiciones=len(lectura.definiciones),
        renglones=len(lectura.renglones),
        cruce=json.dumps(lectura.cruce, ensure_ascii=False),
        subido_por=getattr(user, "email", "")))

    vistos: set[tuple] = set()
    for c in lectura.catalogo:
        k = (_norm(c.item), c.schedule, c.cuenta)
        if k in vistos:
            continue
        vistos.add(k)
        db.add(UsaliItem(hotel_id=HOTEL_ID, item=c.item[:400],
                         item_norm=_norm(c.item)[:400], schedule=c.schedule[:80],
                         cuenta=c.cuenta[:200], confianza=c.confianza,
                         paginas=c.paginas[:60]))
    vistas: set[tuple] = set()
    for d in lectura.definiciones:
        k = (_norm(d.cuenta), d.pagina)
        if k in vistas:
            continue
        vistas.add(k)
        db.add(UsaliDefinicion(hotel_id=HOTEL_ID, cuenta=d.cuenta[:200],
                               cuenta_norm=_norm(d.cuenta)[:200],
                               texto=d.texto, pagina=d.pagina))
    # Los renglones del Schedule: la otra mitad del libro. Se guarda tambien
    # cuando el schedule NO tiene lista aprobada —Schedule 3—, porque esa
    # ausencia es informacion: es la que evita decirle a alguien que su cuenta
    # del Spa esta mal cuando el estandar nunca dio lista para el Spa.
    vistos_r: set[tuple] = set()
    for g in lectura.renglones:
        k = (g.numero, _norm(g.renglon))
        if k in vistos_r:
            continue
        vistos_r.add(k)
        db.add(UsaliRenglon(hotel_id=HOTEL_ID, numero=g.numero,
                            titulo=g.titulo[:80], schedule=g.schedule[:80],
                            renglon=g.renglon[:200],
                            renglon_norm=_norm(g.renglon)[:200],
                            orden=g.orden, pagina=g.pagina,
                            lista_aprobada=g.lista_aprobada))
    await db.commit()

    return {
        "ok": True, "archivo": file.filename,
        "paginas": lectura.paginas, "paginas_con_texto": lectura.paginas_con_texto,
        "items": len(vistos), "definiciones": len(vistas),
        "renglones": len(vistos_r),
        "cruce": lectura.cruce,
    }


@router.get("/usali/buscar/")
async def buscar(
    q: str = Query("", description="texto a buscar en el artículo o la cuenta"),
    schedule: str = Query("", description="filtrar por departamento del USALI"),
    limite: int = Query(80, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Dónde dice el estándar que va algo.

    Busca en el artículo y en el nombre de cuenta, porque las dos preguntas son
    legítimas: «¿dónde va el combustible?» y «¿qué va en Operating Supplies?».
    """
    stmt = select(UsaliItem).where(UsaliItem.hotel_id == HOTEL_ID)
    texto = _norm(q)
    if texto:
        like = f"%{texto}%"
        stmt = stmt.where(or_(UsaliItem.item_norm.like(like),
                              func.lower(UsaliItem.cuenta).like(f"%{q.lower()}%")))
    if schedule:
        stmt = stmt.where(UsaliItem.schedule == schedule)
    glos = _terminos_es()
    filas = (await db.execute(stmt.order_by(UsaliItem.item_norm)
                              .limit(limite))).scalars().all()
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    return {
        "total": total, "recortado": total > len(filas),
        # La cuenta en espanol al lado del ingles: el que busca «¿donde va
        # el cemento?» lee el destino sin traducir de cabeza. El ingles se
        # mantiene porque es el nombre que el libro y el catalogo usan.
        "filas": [{"item": f.item, "schedule": f.schedule, "cuenta": f.cuenta,
                   "cuenta_es": _es(f.cuenta, glos),
                   "confianza": f.confianza, "paginas": f.paginas}
                  for f in filas],
    }


#: Cuando una cuenta del hotel se parece lo suficiente a una del estandar como
#: para mostrar su definicion al lado. Medido sobre las 65 cuentas de setiembre
#: 2026: con 0,90 entran 40 (61,5%) y todas son el mismo nombre escrito igual
#: —el catalogo del hotel se armo sobre USALI—; entre 0,75 y 0,90 entran 6 mas,
#: que son variantes reales; por debajo de 0,75 empieza la basura («Cafeteria»
#: contra «Collateral Material»).
UMBRAL_EXACTO = 0.90
UMBRAL_PARECIDO = 0.75


def _parecido(a: str, b: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, _norm_cta(a), _norm_cta(b)).ratio()


def _norm_cta(s: str) -> str:
    """Normaliza para comparar NOMBRES DE CUENTA.

    Resuelve las abreviaturas que el libro y la contabilidad escriben distinto
    —«Misc. Other Rev» contra «Miscellaneous Other Revenue»— antes de medir el
    parecido. Sin esto, dos nombres de la misma cuenta caen por debajo del
    umbral y la definicion no se muestra.
    """
    s = _norm(s)
    for a, b in (("exp ", "expense "), ("rev ", "revenue "),
                 ("misc ", "miscellaneous "), ("supp ", "supplies "),
                 ("equip ", "equipment "), ("maint ", "maintenance "),
                 ("admin ", "administrative ")):
        s = s.replace(a, b)
    return " ".join(s.split())


#: El glosario ES de los ROTULOS del USALI: los nombres de cuenta y los
#: renglones de los Schedules, para leer el panel en espanol.
#:
#: ⚠️ **No es una traduccion del libro, y la distincion importa.** Se traducen
#: los 335 rotulos —etiquetas cortas de cuenta, terminologia contable estandar—
#: y las 468 definiciones quedan en el idioma del original, que es texto de
#: AHLA/HFTP.
#:
#: ⚠️ **Tampoco mejora el apareo automatico, y eso se midio.** El traslape
#: entre dos listas es simetrico: da igual traducir el libro al espanol que
#: traducir los articulos al ingles, que es lo que ya se probo (19% de
#: cobertura, la mitad mal). La razon de fondo la dan los datos del hotel: de
#: los 40 articulos que mas plata mueven en setiembre 2026, unos seis son
#: sustantivos que el diccionario nombraria — el resto son servicios
#: («Payroll Processing», «Oracle Hospitality», «I Prefer Charges»),
#: combustible por marca («PLUS 91», «DIESEL», CRC 13 M entre los dos), codigos
#: («100libRo», «217846») y comida. El libro no los nombra en ningun idioma.
#:
#: Esto es para LEER. Ver `el-usali-explica-no-alarma` en la memoria.
def _terminos_es() -> dict[str, str]:
    """{llave normalizada: termino en espanol}. Vacio si no hay glosario."""
    from app.seed_data import semilla_del_grupo
    try:
        d = (semilla_del_grupo("usali_terminos_es") or {})["terminos"]
    except Exception:      # noqa: BLE001 — sin glosario se queda en ingles
        return {}
    return {k: v["es"] for k, v in d.items() if v.get("es")}


def _es(rotulo: str, glosario: dict[str, str]) -> str:
    """El rotulo en espanol, o cadena vacia si el glosario no lo tiene.

    Vacio y NO el ingles repetido: la pantalla muestra los dos lado a lado, y
    «Building — Building» se lee como un error del sistema.
    """
    # Un rotulo vacio no se traduce. Sin esto se llevaba lo que hubiera en la
    # llave vacia, que es un termino que no es de nadie.
    k = _norm(rotulo)
    return glosario.get(k, "") if k else ""


#: Departamento de la contabilidad -> departamento del USALI. Es la parte que no
#: se adivina: la correspondencia la miro una persona.
#:
#: Los del Schedule 3 —Spa, Tours, Transporte, Retail, Lavanderia, Innoceana—
#: quedan adrede en una casilla SIN lista aprobada. No es un hueco: es lo que
#: dice el libro, «only the revenues and expenses […] that exist at an
#: individual property».
DEPTO_A_SCHEDULE = {
    "0110": "Rooms", "0111": "Rooms", "0112": "Rooms", "0113": "Rooms",
    "0114": "Rooms",
    "0120": "F&B", "0121": "F&B", "0122": "F&B", "0123": "F&B", "0124": "F&B",
    "0125": "F&B", "0126": "F&B", "0127": "F&B", "0128": "F&B", "0129": "F&B",
    "0130": "Health Club/Spa", "0131": "Health Club/Spa",
    "0132": "Health Club/Spa", "0133": "Health Club/Spa",
    "0140": "Health Club/Spa",
    "0150": "Minor Oper. Dept", "0151": "Minor Oper. Dept",
    "0152": "Minor Oper. Dept", "0155": "Minor Oper. Dept",
    "0156": "Minor Oper. Dept", "0160": "Minor Oper. Dept",
    "0162": "Minor Oper. Dept", "0165": "Minor Oper. Dept",
    # La lavanderia interna SI tiene schedule propio: el 12, House Laundry.
    "0161": "Laundry",
    "0180": "A&G", "0181": "A&G", "0182": "A&G", "0183": "A&G",
    "0184": "A&G", "0186": "A&G",
    "0190": "Sales/Marketing", "0191": "Sales/Marketing",
    "0200": "POM",
    "0205": "Utilities", "0210": "Utilities",
    # La cafeteria de empleados es el Schedule 13, Staff Dining — y el libro le
    # pide lo mismo que el P&L de esta propiedad: «Net Recovery […] should
    # always net to zero to reflect full allocation of this department».
    "0220": "Staff Dining",
    "0230": "Info & Telecom",
    "0240": "Non Op. I&E", "0250": "Non Op. I&E",
}


#: El diccionario y los Schedules no llaman igual a todos los departamentos. El
#: diccionario tiene casillas que NO son un schedule: «Health Club/Spa» es un
#: Other Operated Department —Schedule 3— y «Mult. Depts» quiere decir «este
#: renglon vive en varios schedules», que no es ninguno en particular.
#:
#: ⚠️ Esto importa para no afirmar de mas. Contra setiembre 2026, el 27% de las
#: cuentas cae en una de estas casillas; tratarlas como si tuvieran lista
#: aprobada marcaba 13 cuentas, y las 13 estaban bien puestas.
SCHEDULE_DEL_DICCIONARIO = {
    "Health Club/Spa": 3,
    "Golf Pro Shop": 3,
    "Parking": 3,
    "Garage Parking": 3,
    "Minor Oper. Dept": 3,
    "Other Oper. Depts": 3,
    "Rooms": 1, "F&B": 2, "Misc. Income": 4, "A&G": 5,
    "Info & Telecom": 6, "Sales/Marketing": 7, "POM": 8, "Utilities": 9,
    "Management Fees": 10, "Non Op. I&E": 11, "Laundry": 12,
    "Staff Dining": 13, "Payroll-Rel. Exp": 14,
}


#: Como nombra el TEXTO del libro a cada casilla del diccionario. Hace falta
#: solo donde la pagina no alcanza: las cuatro definiciones del Schedule 3
#: —golf, spa, parking, other operated— viven en el mismo rango de paginas, y
#: lo unico que las distingue es que el texto dice de cual habla.
NOMBRA_AL_DEPTO = {
    "Health Club/Spa": ("health club", "spa"),
    "Golf Pro Shop": ("golf",),
    "Parking": ("parking", "garage"),
    "Garage Parking": ("parking", "garage"),
    "Minor Oper. Dept": ("other operated", "minor operated"),
    "Rooms": ("rooms",),
    "F&B": ("food and beverage",),
    "A&G": ("administrative and general",),
    "Info & Telecom": ("information and telecommunications",),
    "Sales/Marketing": ("sales and marketing",),
    "POM": ("property operation",),
    "Utilities": ("utilities",),
    "Laundry": ("house laundry",),
    "Staff Dining": ("staff dining",),
}


def _habla_de(texto: str, schedule: str) -> bool:
    """¿Esta definicion dice explicitamente que habla de ESTE departamento?"""
    t = (texto or "")[:300].lower()
    return any(p in t for p in NOMBRA_AL_DEPTO.get(schedule, ()))


def _nombra_otro(texto: str, schedule: str) -> bool:
    """¿Nombra un departamento que NO es este?

    Es lo que evita el error de Tours. El Schedule 3 tiene cuatro definiciones
    de «Miscellaneous» —golf, spa, parking y other operated— en el mismo rango
    de paginas, asi que por pagina las cuatro parecen suyas. Sin este chequeo,
    a Tours le salia primero la del campo de golf.
    """
    t = (texto or "")[:300].lower()
    mias = set(NOMBRA_AL_DEPTO.get(schedule, ()))
    for otro, patrones in NOMBRA_AL_DEPTO.items():
        if otro == schedule:
            continue
        for p in patrones:
            if p in t and p not in mias:
                return True
    return False


async def _schedule_por_pagina(db: AsyncSession):
    """Una funcion que dice a que Schedule pertenece cada pagina del libro.

    Las definiciones del libro van DETRAS del cuadro de su Schedule, asi que la
    pagina alcanza para saber de que departamento habla cada una. Los cortes
    salen de `usali_renglones` —la pagina donde esta cada cuadro— y no de una
    tabla escrita a mano: otra edicion del libro mueve las paginas y esto sigue.

    ## Por que hace falta

    Owner, 2026-10-09, mirando el panel: la cuenta «Miscellaneous» trae SEIS
    definiciones —paginas 57, 70, 80, 89, 98 y 112—, una por departamento,
    porque el libro define «cualquier gasto de este departamento que no encaje
    en los otros renglones» una vez por cada uno. Sin saber a cual pertenece
    cada una, el panel mostraba las de Parking y Golf arriba de la que importa.

    ## Medido

    En las 9 definiciones cuyo TEXTO nombra el departamento, la pagina coincide
    con lo que dice el texto en las 9. («food and beverage» es F&B,
    «administrative and general» es A&G, y golf, spa y parking son Other
    Operated Departments — el Schedule 3.)
    """
    filas = (await db.execute(
        select(UsaliRenglon.numero, UsaliRenglon.schedule,
               func.min(UsaliRenglon.pagina))
        .where(UsaliRenglon.hotel_id == HOTEL_ID)
        .group_by(UsaliRenglon.numero, UsaliRenglon.schedule))).all()
    cortes = sorted((int(p or 0), n, s) for n, s, p in filas)

    def de(pagina: int) -> str:
        # El ultimo cuadro que quedo ANTES de esta pagina.
        quien = ""
        for p0, _n, s in cortes:
            if p0 <= (pagina or 0):
                quien = s
        return quien
    return de


async def _renglones_del_schedule(db: AsyncSession, schedule: str) -> dict:
    """Que renglones aprueba el estandar para este departamento.

    Devuelve `lista_aprobada=False` cuando el libro no da lista —el Schedule 3,
    Other Operated Departments, dice «only the revenues and expenses […] that
    exist at an individual property»—. Decirlo es la mitad util de la respuesta:
    evita que alguien lea el silencio como «su cuenta esta mal».
    """
    num = SCHEDULE_DEL_DICCIONARIO.get(schedule)
    if num is None:
        return {"schedule": schedule, "numero": None, "lista_aprobada": False,
                "renglones": [],
                "motivo": "este renglon del diccionario no es un solo "
                          "departamento del reporte"}
    filas = (await db.execute(
        select(UsaliRenglon)
        .where(UsaliRenglon.hotel_id == HOTEL_ID, UsaliRenglon.numero == num)
        .order_by(UsaliRenglon.orden))).scalars().all()
    if not filas:
        return {"schedule": schedule, "numero": num, "lista_aprobada": False,
                "renglones": [], "motivo": "no hay USALI cargado"}
    aprobada = bool(filas[0].lista_aprobada)
    glos = _terminos_es()
    return {
        "schedule": schedule,
        "numero": num,
        "titulo": filas[0].titulo,
        "titulo_es": _es(filas[0].titulo, glos),
        "lista_aprobada": aprobada,
        "motivo": "" if aprobada else
                  "el estandar no da lista cerrada para este departamento",
        "renglones": [g.renglon for g in filas],
        # El mismo renglon en espanol, en el MISMO orden. Lista aparte y no
        # un campo dentro de cada fila: el que ya consume `renglones` sigue
        # funcionando sin cambiar nada.
        "renglones_es": [_es(g.renglon, glos) for g in filas],
    }


@router.get("/usali/schedule/")
async def schedule_de(
    schedule: str = Query(..., description="el departamento del USALI"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Los renglones aprobados del reporte de un departamento."""
    return await _renglones_del_schedule(db, schedule)


@router.get("/usali/para-cuenta/")
async def para_cuenta(
    nombre: str = Query(..., description="el nombre de la cuenta del hotel"),
    schedule: str = Query("", description="el departamento del USALI, si se sabe"),
    dept: str = Query("", description="el departamento de la contabilidad"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Que dice el estandar de una cuenta del hotel.

    Owner, 2026-10-08, sobre por que esto y no una regla automatica: el
    diccionario del USALI habla de ARTICULOS en ingles y el mayor del hotel de
    PROVEEDORES en espanol —medido: 98,3% de las descripciones no comparte una
    sola palabra con el libro—. Aparear asiento contra estandar no se puede.

    Aparear NOMBRE DE CUENTA si: el catalogo del hotel se armo sobre USALI y el
    61,5% de las cuentas de setiembre 2026 tiene el nombre identico.

    ⚠️ **Esto NO afirma nada.** Devuelve lo que el libro dice de una cuenta que
    se llama parecido, con el parecido a la vista, para que una persona lo lea y
    decida. La diferencia importa: una regla que afirma mal deja de mirarse; una
    referencia que se equivoca se ignora y no cuesta nada.
    """
    # El que llama pasa el departamento de la contabilidad —«0110»— y el
    # puente vive aca: la pantalla no tiene por que saber como se llaman los
    # departamentos del USALI.
    if dept and not schedule:
        schedule = DEPTO_A_SCHEDULE.get(dept, "")

    filas = (await db.execute(
        select(UsaliDefinicion)
        .where(UsaliDefinicion.hotel_id == HOTEL_ID))).scalars().all()
    nombres_dic = [r[0] for r in (await db.execute(
        select(UsaliItem.cuenta).where(UsaliItem.hotel_id == HOTEL_ID)
        .distinct())).all()]

    mejor, punt = None, 0.0
    for d in filas:
        p = _parecido(nombre, d.cuenta)
        if p > punt:
            mejor, punt = d, p
    # El diccionario tambien nombra cuentas, y algunas no tienen definicion.
    mejor_dic, punt_dic = None, 0.0
    for c in nombres_dic:
        p = _parecido(nombre, c)
        if p > punt_dic:
            mejor_dic, punt_dic = c, p

    cuenta_usali = (mejor.cuenta if punt >= punt_dic and mejor else mejor_dic)
    calidad = max(punt, punt_dic)
    grado = ("exacto" if calidad >= UMBRAL_EXACTO
             else "parecido" if calidad >= UMBRAL_PARECIDO else "ninguno")

    if grado == "ninguno":
        # ⚠️ Se contesta que no hay, y no el candidato malo. Mostrar
        # «Cafeteria -> Collateral Material» ensena a desconfiar de la pantalla.
        return {"nombre": nombre, "grado": "ninguno", "parecido": round(calidad, 3),
                "cuenta_usali": None, "definiciones": [], "items": [],
                "schedule": (await _renglones_del_schedule(db, schedule)
                             if schedule else None)}

    defs = [d for d in filas if _norm_cta(d.cuenta) == _norm_cta(cuenta_usali or "")]
    # De que departamento habla cada definicion, y la que importa primero.
    # Owner, 2026-10-09: «Miscellaneous» trae seis, una por departamento.
    de_pagina = await _schedule_por_pagina(db)
    dep_de = {d.pagina: de_pagina(d.pagina) for d in defs}
    # Tres niveles: el texto lo dice, o la pagina lo dice y el texto no nombra
    # a otro, o ninguno. El segundo chequeo es el que evita que a Tours le
    # salga primero la definicion del campo de golf.
    propia = {d.pagina: bool(schedule) and (
                  _habla_de(d.texto, schedule)
                  or (dep_de.get(d.pagina) == schedule
                      and not _nombra_otro(d.texto, schedule)))
              for d in defs}
    if schedule:
        # Primero la que habla de SU departamento —por el texto o por la
        # pagina—, despues el resto en el orden del libro.
        defs = sorted(defs, key=lambda d: (not propia[d.pagina], d.pagina))
    items = (await db.execute(
        select(UsaliItem)
        .where(UsaliItem.hotel_id == HOTEL_ID, UsaliItem.cuenta == cuenta_usali)
        .order_by(UsaliItem.item_norm).limit(200))).scalars().all()
    if schedule:
        propios = [i for i in items if i.schedule == schedule]
        otros = [i for i in items if i.schedule != schedule]
        items = propios + otros
    return {
        "nombre": nombre,
        "grado": grado,
        "parecido": round(calidad, 3),
        "cuenta_usali": cuenta_usali,
        "cuenta_usali_es": _es(cuenta_usali or "", _terminos_es()),
        "definiciones": [{"cuenta": d.cuenta, "texto": d.texto,
                          "pagina": d.pagina,
                          "schedule": dep_de.get(d.pagina, ""),
                          "es_del_depto": bool(propia.get(d.pagina))}
                         for d in defs],
        "items": [{"item": i.item, "schedule": i.schedule} for i in items],
        # Que lleva ESE departamento segun el estandar. Es lo que el owner
        # pidio el 2026-10-08: «cada cuenta tiene la descripcion y va por
        # departamento».
        "schedule": (await _renglones_del_schedule(db, schedule)
                     if schedule else None),
    }


@router.get("/usali/excel/")
async def excel(
    q: str = Query(""),
    schedule: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """El catalogo en Excel: diccionario, definiciones y renglones del reporte.

    No es un adorno: con las ~1.950 filas afuera se puede revisar el catalogo de
    corrido y, sobre todo, es la base para armar el PUENTE contra las cuentas de
    Integrity, que es la etapa 2. Esa correspondencia la tiene que mirar una
    persona.

    ⚠️ Baja lo que la pantalla esta mostrando, filtros incluidos. Este proyecto
    ya pago una vez por un Excel que no era lo que se veia.
    """
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    stmt = select(UsaliItem).where(UsaliItem.hotel_id == HOTEL_ID)
    texto = _norm(q)
    if texto:
        like = f"%{texto}%"
        stmt = stmt.where(or_(UsaliItem.item_norm.like(like),
                              func.lower(UsaliItem.cuenta).like(f"%{q.lower()}%")))
    if schedule:
        stmt = stmt.where(UsaliItem.schedule == schedule)
    items = (await db.execute(stmt.order_by(UsaliItem.schedule, UsaliItem.cuenta,
                                            UsaliItem.item_norm))).scalars().all()
    defs = (await db.execute(
        select(UsaliDefinicion).where(UsaliDefinicion.hotel_id == HOTEL_ID)
        .order_by(UsaliDefinicion.pagina))).scalars().all()
    renglones = (await db.execute(
        select(UsaliRenglon).where(UsaliRenglon.hotel_id == HOTEL_ID)
        .order_by(UsaliRenglon.numero, UsaliRenglon.orden))).scalars().all()

    wb = Workbook()
    cab = Font(bold=True, color="FFFFFF")
    fondo = PatternFill("solid", fgColor="1F3B63")

    h = wb.active
    h.title = "Diccionario"
    h.append(["Departamento", "Cuenta", "Articulo", "Origen", "Paginas"])
    for c in h[1]:
        c.font, c.fill = cab, fondo
    for x in items:
        h.append([x.schedule, x.cuenta, x.item,
                  "confirmado" if x.confianza == "confirmado" else "de un solo lado",
                  x.paginas])
    for col, ancho in zip("ABCDE", (22, 34, 60, 16, 12)):
        h.column_dimensions[col].width = ancho
    h.freeze_panes = "A2"

    d = wb.create_sheet("Definiciones")
    d.append(["Cuenta", "Pagina", "Definicion"])
    for c in d[1]:
        c.font, c.fill = cab, fondo
    for x in defs:
        d.append([x.cuenta, x.pagina, x.texto])
    for col, ancho in zip("ABC", (34, 9, 140)):
        d.column_dimensions[col].width = ancho
    for fila in d.iter_rows(min_row=2, min_col=3, max_col=3):
        fila[0].alignment = Alignment(wrap_text=True, vertical="top")
    d.freeze_panes = "A2"

    g = wb.create_sheet("Renglones del reporte")
    g.append(["Sch.", "Departamento", "Orden", "Renglon aprobado",
              "Lista cerrada", "Pagina"])
    for c in g[1]:
        c.font, c.fill = cab, fondo
    for x in renglones:
        g.append([x.numero, x.schedule, x.orden + 1, x.renglon,
                  # Decirlo en la hoja y no solo en pantalla: el Schedule 3 no
                  # tiene lista, y quien lea el Excel suelto tiene que saberlo.
                  "si" if x.lista_aprobada else "NO - el estandar no da lista",
                  x.pagina])
    for col, ancho in zip("ABCDEF", (7, 20, 8, 46, 30, 9)):
        g.column_dimensions[col].width = ancho
    g.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        buf.getvalue(),
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"),
        headers={"Content-Disposition": 'attachment; filename="USALI_catalogo.xlsx"'})


@router.get("/usali/definicion/")
async def definicion(
    cuenta: str = Query(..., description="nombre de cuenta del USALI"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Qué dice el libro que incluye esa cuenta, y qué artículos le asigna."""
    n = _norm(cuenta)
    defs = (await db.execute(
        select(UsaliDefinicion)
        .where(UsaliDefinicion.hotel_id == HOTEL_ID,
               UsaliDefinicion.cuenta_norm == n))).scalars().all()
    if not defs:
        # El nombre de cuenta del diccionario puede venir abreviado; se busca
        # por prefijo antes de contestar que no hay nada.
        defs = (await db.execute(
            select(UsaliDefinicion)
            .where(UsaliDefinicion.hotel_id == HOTEL_ID,
                   UsaliDefinicion.cuenta_norm.like(f"{n[:24]}%"))
            .limit(3))).scalars().all()
    items = (await db.execute(
        select(UsaliItem).where(UsaliItem.hotel_id == HOTEL_ID,
                                UsaliItem.cuenta == cuenta)
        .order_by(UsaliItem.item_norm).limit(300))).scalars().all()
    return {
        "cuenta": cuenta,
        "definiciones": [{"cuenta": d.cuenta, "texto": d.texto, "pagina": d.pagina}
                         for d in defs],
        "items": [{"item": i.item, "schedule": i.schedule,
                   "confianza": i.confianza} for i in items],
    }
