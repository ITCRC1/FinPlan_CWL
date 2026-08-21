# -*- coding: utf-8 -*-
"""Siembra los canales comerciales.

Idempotente y **no destructivo**: inserta lo que falta y NO pisa lo que el owner
haya editado en la app. El nombre y la comisión son suyos — si los renegocia en
pantalla, un redeploy no puede revertirlos. Lo único que el seed re-afirma es la
existencia del código y su orden.
"""
import json
import pathlib
from decimal import Decimal

from sqlalchemy import select

from app.models.canal_comercial import CanalComercial

#: ⚠️ **Bajo `<HOTEL_ID>/`, no en la raíz de `seed_data/`.**
#:
#: Estaba en la raíz y se sembraba sin filtro de hotel, en CADA arranque. Los
#: siete canales son los de Corcovado —su mix y su comisión, mandados por el
#: owner desde su app de Compensación—, así que **una propiedad nueva los
#: heredaba sola**: su Net Factor sería el de otro hotel, y el ingreso saldría
#: mal sin que nada fallara. Con el mix de CWL (0,797) aplicado a una propiedad
#: que venda distinto, el error medido va de −$346.109 a +$552.314 al año.
#:
#: ⚠️ **El ORDEN importó.** Gatear esto sin la guarda de `_exigir_mix` habría
#: sido PEOR: la propiedad nueva quedaría sin mix, la tarifa neta se escribiría
#: igual a la rack y el ingreso saldría **+25%**. Heredar un mix ajeno es un
#: número equivocado y conservador; caer a «sin comisión» es equivocado e
#: inflador. Por eso primero la guarda (`revenue_api._exigir_mix`) y después
#: esto.
_SEED_DIR = pathlib.Path(__file__).parent / "seed_data"


def _archivo(hotel_id: str | None = None) -> pathlib.Path:
    from app.hotel_actual import HOTEL_ID
    return _SEED_DIR / (hotel_id or HOTEL_ID) / "canales_comerciales.json"


ARCHIVO = _archivo()


def leer() -> list[dict]:
    """Los canales de ESTA propiedad. Vacío si no tiene semilla propia.

    Una propiedad sin archivo **no hereda los canales de otra**: arranca sin mix
    y la guarda de `revenue_api._exigir_mix` le impide escribir tarifas hasta
    que alguien cargue el suyo. Es incómodo a propósito — la alternativa era
    facturar con el mix de Corcovado sin que nadie se enterara.
    """
    if not ARCHIVO.exists():
        return []
    datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))["canales"]
    vistos = set()
    for c in datos:
        code = str(c["code"]).strip()
        if not code or code in vistos:
            raise ValueError(f"canal repetido o sin codigo: {code!r}")
        vistos.add(code)
        for campo in ("comision_pct", "mix_pct"):
            p = Decimal(str(c.get(campo, 0)))
            # Fracción, no porcentaje. Un 30 en vez de 0.30 haría que el Net
            # Factor saliera negativo y nadie sabría por qué.
            if not (0 <= p <= 1):
                raise ValueError(
                    f"{code}: {campo} = {p} no es una fraccion entre 0 y 1")
    # El mix TIENE que dar 100%. Si no, el Net Factor sale de una base que no es
    # el total y el error se propaga a todo el ingreso de habitaciones — sin
    # que nada falle ni avise.
    suma = sum(Decimal(str(c.get("mix_pct", 0))) for c in datos)
    if abs(suma - Decimal("1")) > Decimal("0.0001"):
        raise ValueError(f"el mix de los canales suma {suma}, tiene que dar 1")

    # ⚠️ Y CADA UNO tiene que decir a dónde rueda. Sin esto, un canal nuevo en el
    # JSON entraría con el default del modelo —`DIRECT`— y cobraría 9,27% de
    # comisión en vez del 30% de TA: el ingreso saldría de MÁS, sin que nada
    # falle. Es el mismo agujero que la migración 120 vino a cerrar, entrando
    # por la puerta del seed.
    sin_destino = [c["code"] for c in datos if not str(c.get("rueda_a", "")).strip()]
    if sin_destino:
        raise ValueError(
            f"estos canales no dicen a qué canal de comisión ruedan: {sin_destino}. "
            f"Agregales `rueda_a` — si no, entran como DIRECT y facturan de más.")
    return datos


async def seed_canales(db) -> dict:
    canales = leer()
    if not canales:
        # Esta propiedad no trae canales propios. No se siembra nada: heredar
        # los de otra daría un Net Factor ajeno y un ingreso equivocado.
        return {"total": 0, "nuevos": 0, "sin_semilla": True}
    actuales = {c.code: c for c in (await db.execute(select(CanalComercial))).scalars()}
    # El mix llego DESPUES que la tabla (migracion 110), asi que las filas que
    # ya existian lo tienen en cero — y un mix que suma cero rompe el mixer.
    # Se rellena SOLO si nadie cargo ninguno: si hay aunque sea uno, el owner ya
    # decidio y esto no lo toca.
    sin_mix = actuales and not any(Decimal(str(c.mix_pct or 0)) for c in actuales.values())
    nuevos = 0
    for c in canales:
        code = str(c["code"]).strip()
        if code not in actuales:
            db.add(CanalComercial(
                code=code, nombre=c.get("nombre", ""),
                comision_pct=Decimal(str(c.get("comision_pct", 0))),
                mix_pct=Decimal(str(c.get("mix_pct", 0))),
                entrada=c.get("entrada", ""),
                # Explícito, nunca el default del modelo. Ver `leer()`.
                rueda_a=str(c["rueda_a"]).strip(),
                orden=c.get("orden", 0), activo=True))
            nuevos += 1
        else:
            actuales[code].orden = c.get("orden", actuales[code].orden)
            if sin_mix:
                actuales[code].mix_pct = Decimal(str(c.get("mix_pct", 0)))
    await db.flush()
    return {"total": len(canales), "nuevos": nuevos}
