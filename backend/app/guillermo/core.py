# -*- coding: utf-8 -*-
"""Guillermo — el núcleo, sin I/O de red ni de disco.

Requisito de diseño del spec (§2), y es buena idea: **el mismo código tiene que
correr en el cron de Railway y en un agente local**. Si el núcleo supiera de
dónde vienen los archivos, cambiar de fuente sería reescribirlo.

Acá no hay `open()`, ni `requests`, ni sesión de base. Entra data, sale
veredicto. Lo que toca el mundo vive en `sources/` y `runners/`.
"""
from __future__ import annotations

import fnmatch
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

# ─── La máquina de estados (§7.5) ────────────────────────────────────────────
#
# Se escribe como MAPA y no como cadena de `if`: así el conjunto de
# transiciones válidas es legible de un vistazo, y agregar una obliga a
# escribirla acá en vez de esconderla adentro de una función.

TRANSICIONES: dict[str, set[str]] = {
    "queued": {"running"},
    "running": {"failed", "validated", "pending_review"},
    "validated": {"imported", "shadowed"},
    "pending_review": {"validated", "failed"},
    "imported": {"reverted"},
    # Terminales: de acá no se sale.
    "failed": set(),
    "shadowed": set(),
    "reverted": set(),
}

TERMINALES = {e for e, salidas in TRANSICIONES.items() if not salidas}


class TransicionInvalida(ValueError):
    """Un estado que no puede llegar adonde se le pidió."""


def puede_pasar(desde: str, hacia: str) -> bool:
    return hacia in TRANSICIONES.get(desde, set())


def transicionar(desde: str, hacia: str) -> str:
    """Devuelve `hacia`, o revienta con el motivo.

    ⚠️ Revienta a propósito en vez de devolver `False`: un batch que quedó en
    un estado imposible es peor que uno que falló, porque el que falló se ve.
    """
    if desde not in TRANSICIONES:
        raise TransicionInvalida(f"estado desconocido: «{desde}»")
    if not puede_pasar(desde, hacia):
        posibles = sorted(TRANSICIONES[desde]) or ["ninguno: es terminal"]
        raise TransicionInvalida(
            f"de «{desde}» no se puede pasar a «{hacia}». Posibles: {posibles}")
    return hacia


# ─── Normalización de texto (§7.4) ───────────────────────────────────────────
#
# ⚠️ Es el mejor aporte del spec original, y **la misma receta ya existía** en
# `importers/verificacion.py:130-148`. Acá se implementa igual a propósito —
# mismos cinco pasos— para que un texto normalizado signifique lo mismo en los
# dos lados de la app.

_PUNTUACION = re.compile(r"[^\w\s]", re.UNICODE)
_ESPACIOS = re.compile(r"\s+")


def normalizar(texto: str | None) -> str:
    """`MANT. PISCINA QUÍMICOS` y `Mant  piscina quimicos` → el mismo texto.

    1. mayúsculas · 2. sin tildes ni diacríticos · 3. sin puntuación ·
    4. espacios colapsados · 5. sin bordes.

    Sobre el resultado, el match es **exacto**: sin regex y sin fuzzy. Es lo
    que hace que la métrica «reglas nuevas → cero» pueda converger; con fuzzy,
    dos duplicados cosméticos se cuentan como reglas distintas para siempre.
    """
    if not texto:
        return ""
    t = unicodedata.normalize("NFD", str(texto))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = _PUNTUACION.sub(" ", t.upper())
    return _ESPACIOS.sub(" ", t).strip()


# ─── Validación nivel 1 · presencia (§6.2) ───────────────────────────────────

@dataclass
class ArchivoVisto:
    """Lo que el núcleo necesita saber de un archivo, sin abrirlo."""
    nombre: str
    tamano: int
    # La fecha INTERNA del reporte, si el parser la pudo sacar. `None` = no se
    # sabe, que NO es lo mismo que «no coincide».
    fecha_interna: date | None = None


@dataclass
class Hallazgo:
    nivel: int
    control: str
    pasa: bool
    detalle: str


@dataclass
class Esperado:
    report_id: str
    patron: str
    obligatorio: bool = True
    tamano_min: int = 0


def _casa(nombre: str, patron: str) -> bool:
    return bool(patron) and fnmatch.fnmatch(nombre, patron)


def nivel_1_presencia(vistos: list[ArchivoVisto],
                      esperados: list[Esperado]) -> list[Hallazgo]:
    """¿Están todos? ¿No vacíos? ¿De tamaño razonable?

    ⚠️ **Sin manifiesto no dice «todo bien»: dice que no puede opinar.** Un
    verde sobre una lista vacía de esperados es exactamente el falso positivo
    que el §6.3 quiere evitar — y es el estado de hoy, porque el manifiesto es
    la decisión D-1 del owner y nace vacío.
    """
    if not esperados:
        return [Hallazgo(1, "manifiesto", False,
                         "no hay reportes esperados configurados: no se puede "
                         "verificar la presencia (decisión D-1)")]

    fuera: list[Hallazgo] = []
    for esp in esperados:
        casan = [a for a in vistos if _casa(a.nombre, esp.patron)]
        if not casan:
            fuera.append(Hallazgo(
                1, f"presencia · {esp.report_id}", not esp.obligatorio,
                f"no llegó ningún archivo que case con «{esp.patron}»"))
            continue
        for a in casan:
            if a.tamano <= 0:
                fuera.append(Hallazgo(1, f"vacío · {esp.report_id}", False,
                                      f"«{a.nombre}» llegó vacío"))
            elif esp.tamano_min and a.tamano < esp.tamano_min:
                # ⚠️ El archivo truncado es el caso peligroso: entra, parsea y
                # da totales más chicos sin que nada falle.
                fuera.append(Hallazgo(
                    1, f"tamaño · {esp.report_id}", False,
                    f"«{a.nombre}» pesa {a.tamano} y se esperaban al menos "
                    f"{esp.tamano_min}: puede estar truncado"))
            else:
                fuera.append(Hallazgo(1, f"presencia · {esp.report_id}", True,
                                      f"«{a.nombre}» ({a.tamano} bytes)"))
    return fuera


# ─── Validación nivel 2 · identidad del período (§6.2) ───────────────────────

def nivel_2_periodo(vistos: list[ArchivoVisto], desde: date,
                    hasta: date) -> list[Hallazgo]:
    """La fecha **interna** del reporte tiene que caer en el período declarado.

    ⚠️ Es lo que detecta **el re-descargado de ayer**: el archivo llega, tiene
    el nombre de hoy, pesa lo de siempre y trae los datos de otro día. Sin este
    control eso entra y cuadra consigo mismo.

    ⚠️ Y una fecha que **no se pudo leer** no pasa como buena: se marca como
    desconocida. «No sé» y «coincide» no son lo mismo, y tratarlos igual es
    cómo un control se vuelve decorativo.
    """
    fuera: list[Hallazgo] = []
    for a in vistos:
        if a.fecha_interna is None:
            fuera.append(Hallazgo(
                2, f"período · {a.nombre}", False,
                "no se pudo leer la fecha interna del reporte"))
        elif not (desde <= a.fecha_interna <= hasta):
            fuera.append(Hallazgo(
                2, f"período · {a.nombre}", False,
                f"el reporte es del {a.fecha_interna}, y el período declarado "
                f"va del {desde} al {hasta}"))
        else:
            fuera.append(Hallazgo(2, f"período · {a.nombre}", True,
                                  str(a.fecha_interna)))
    return fuera


# ─── Detector de falso positivo (§6.3) ───────────────────────────────────────

def variacion_sospechosa(total_ahora: Decimal, total_comparable: Decimal,
                         umbral_pct: Decimal) -> tuple[bool, Decimal]:
    """Compara contra **el mismo mes del año anterior**, no contra el mes previo.

    ⚠️ Corrección al spec original, que decía «el período anterior comparable»
    sin definirlo. En Corcovado eso importa: setiembre corre al 9,1% de
    ocupación y febrero al 81,4%. Mes contra mes, la alerta salta todos los
    meses y se vuelve ruido — y una alerta que siempre suena es una alerta
    apagada.

    Quien llama es el que elige el comparable; acá se documenta cuál es.
    """
    if not total_comparable:
        # Sin comparable no hay opinión. No es «pasa».
        return (False, Decimal("0"))
    var = (total_ahora - total_comparable) / abs(total_comparable) * 100
    return (abs(var) > umbral_pct, var)


# ─── Heartbeat · dead-man switch (§12.1) ─────────────────────────────────────

def latido_vencido(ultimo: datetime | None, max_horas: int,
                   ahora: datetime | None = None) -> tuple[bool, str]:
    """¿Pasó demasiado sin que Guillermo diera señales?

    ⚠️ **Esto es lo que hace seguro que el silencio signifique «todo bien».**
    Sin dead-man switch, un sistema que sólo avisa ante problemas se comporta
    igual estando sano que estando muerto.

    ⚠️ Y **nunca haber latido cuenta como vencido.** Si «no hay registro»
    devolviera «todo bien», el estado inicial —y el de un worker que jamás
    arrancó— sería verde.
    """
    ahora = ahora or datetime.now(timezone.utc)
    if ultimo is None:
        return (True, "Guillermo nunca latió: no hay ninguna ronda registrada")
    if ultimo.tzinfo is None:
        ultimo = ultimo.replace(tzinfo=timezone.utc)
    edad = ahora - ultimo
    if edad > timedelta(hours=max_horas):
        horas = edad.total_seconds() / 3600
        return (True, f"el último latido fue hace {horas:.1f} h y el máximo "
                      f"es {max_horas} h")
    return (False, "")


# ─── El semáforo del header (§10.1) ──────────────────────────────────────────

@dataclass
class Estado:
    """Lo que la UI muestra. `state` es el contrato del §10.2.7."""
    state: str            # idle | running | pending | stuck
    color: str            # verde | ambar | rojo
    pendientes: int = 0
    mensaje: str = ""
    detalles: list[str] = field(default_factory=list)


def estado_visible(*, latido_vencido_: bool, motivo_latido: str,
                   pendientes: int, corriendo: bool,
                   nunca_arranco: bool = False,
                   configurado: bool = True) -> Estado:
    """⚠️ El orden importa: **el latido vencido gana sobre todo lo demás.**

    Un Guillermo trabado con cero pendientes se vería verde si los pendientes
    mandaran — y «cero pendientes» sería justamente la consecuencia de estar
    trabado, no una buena noticia.

    ⚠️ **«Nunca arrancó» NO es «trabado», y tampoco es «todo bien».** Es un
    tercer estado, y hace falta:

    * Marcarlo **rojo** pondría a gritar a un Guillermo recién instalado que
      todavía no tiene qué buscar —el manifiesto es la decisión D-1— y una
      alarma que suena desde el día cero se aprende a ignorar.
    * Marcarlo **verde** sería peor: un worker que jamás corrió se vería sano.

    Así que va en **gris**: no está bien, no está roto, no está encendido. Y en
    cuanto ALGUIEN CONFIGURA qué esperar, no haber corrido pasa a ser una falla
    de verdad y sí se pone rojo.
    """
    if nunca_arranco and not configurado:
        return Estado("off", "gris", pendientes,
                      "Guillermo todavía no arrancó: falta definir qué reportes "
                      "espera (D-1)", [motivo_latido])
    if latido_vencido_:
        return Estado("stuck", "rojo", pendientes,
                      motivo_latido or "sin latido", [motivo_latido])
    if pendientes > 0:
        return Estado("pending", "ambar", pendientes,
                      f"{pendientes} pendientes esperándote")
    if corriendo:
        return Estado("running", "verde", 0, "corriendo")
    return Estado("idle", "verde", 0, "al día")


# ─── Niveles de capacidad (owner, 2026-08-20) ────────────────────────────────
#
# «Podés meterle capacidades: full, medio, bajo, o como vos quieras.»
#
# ⚠️ **Lo que crece entre niveles es CUÁNDO actúa, no QUÉ puede decidir solo.**
# En los tres, una propuesta del modelo va a la cola y ahí se detiene; lo único
# que se auto-aplica son reglas que un humano aprobó antes. Esa es la regla
# absoluta del §4 del spec, y un nivel «full» que la rompiera no sería más
# capaz: sería otro sistema, uno en el que ya no se puede confiar en el
# silencio.

@dataclass(frozen=True)
class Nivel:
    clave: str
    nombre: str
    resumen: str
    # Qué puede hacer, en orden creciente.
    lee: bool = True
    avisa: bool = True
    encola: bool = False          # deja excepciones persistidas
    importa: bool = False         # escribe en el modelo
    aplica_reglas: bool = False   # sólo reglas aprobadas por un humano
    recalcula: bool = False       # corre el recálculo del escenario
    # ⚠️ `corre_solo` es «IMPORTA y RECALCULA sin que nadie se lo pida», no
    # «se despierta solo». La ronda de control —que sólo recorre y anota, y no
    # toca un número del modelo— la dispara el cron en TODOS los niveles: ver
    # `guillermo/cron.py`. Exigir el nivel más alto para que Guillermo pueda
    # MIRAR obligaría a darle permiso de escritura para conseguir un latido.
    corre_solo: bool = False
    # Lo que NUNCA hace, en ningún nivel.
    aplica_propuestas_del_modelo: bool = False


NIVELES: dict[str, Nivel] = {
    "bajo": Nivel(
        "bajo", "Bajo · mira y avisa",
        "Procesa todo y no escribe nada. Recorre solo todos los días en el "
        "horario configurado y deja sus notas en la cola. Es donde nace, y "
        "donde conviene tenerlo hasta que sus avisos sean confiables.",
        encola=True),
    "medio": Nivel(
        "medio", "Medio · asistido",
        "Importa, y auto-aplica ÚNICAMENTE reglas que un humano aprobó antes. "
        "Todo lo que no reconoce va a la cola. El recálculo lo corre cuando "
        "vos apretás el botón.",
        encola=True, importa=True, aplica_reglas=True, recalcula=True),
    "alto": Nivel(
        "alto", "Alto · autónomo",
        "Además importa y corre el recálculo por su cuenta, en el horario "
        "configurado. Sigue sin aplicar ni una propuesta suya sin aprobación.",
        encola=True, importa=True, aplica_reglas=True, recalcula=True,
        corre_solo=True),
}

# Los nombres del spec original, para que nada que ya esté guardado se rompa.
_ALIAS = {"shadow": "bajo", "assisted": "medio"}


def nivel(clave: str | None) -> Nivel:
    """El nivel vigente. ⚠️ Un valor desconocido cae al MÁS BAJO, nunca al más
    alto: si alguien escribe mal la configuración, el error tiene que quitarle
    permisos, no dárselos."""
    c = (clave or "").strip().lower()
    return NIVELES.get(_ALIAS.get(c, c), NIVELES["bajo"])


def puede(clave: str | None, capacidad: str) -> bool:
    """¿El nivel vigente puede hacer esto?"""
    n = nivel(clave)
    if capacidad == "aplica_propuestas_del_modelo":
        # ⚠️ No es un `getattr` más: se responde que NO explícitamente, para
        # que agregar un nivel nuevo no pueda habilitarlo por descuido.
        return False
    return bool(getattr(n, capacidad, False))
