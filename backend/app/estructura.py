# -*- coding: utf-8 -*-
"""El inventario de lo que una instalación tiene que TENER.

**Por qué existe (owner, 2026-08-20).** *«Necesito que fortalezcas esta app para
que no pierda estructura.»* Va a clonar la app por propiedad, con las bases en
cero. El modo en que un clon pierde estructura no da error: la app levanta, las
pantallas pintan, y resulta que el catálogo de cuentas entró a medias o que la
clasificación de costos nunca se cargó — y todo lo que se suba después cae en
ninguna línea, o cae en cero, que se lee igual que «no vendió».

**Qué agrega sobre lo que ya había.** El chequeo preguntaba «¿está vacía?».
Vacía se nota; **incompleta no**. `account_mapping` con tres filas de 1.099
pasaba el control, y esas 1.096 cuentas que faltan no fallan: caen en ninguna
línea del P&L. Acá se compara contra **lo esperado**.

⚠️ **Ni un número escrito a mano.** Cada `esperado` lee la MISMA fuente que lee
el seed —el JSON del repo, la constante, el CSV—, así que agregar una cuenta al
catálogo mueve el esperado solo. Un número tecleado acá se volvería mentira en
la primera semilla que alguien agregue, y este proyecto ya pagó dos veces por
una lista escrita a mano.

## Las dos familias, que no se tratan igual

* **`GRUPO`** — viene del repo y es idéntico en las cuatro propiedades: el
  catálogo USALI, el mapeo, las líneas del P&L. Si falta, **es estructura
  perdida**: error.
* **`PROPIEDAD`** — sale de `seed_data/<HOTEL_ID>/` y es de cada hotel: sus
  canales, sus tarifas rack, su clasificación de costos. En una propiedad recién
  abierta **falta a propósito**: aviso con nombre, nunca error. Marcarlo en rojo
  el día uno enseñaría a ignorar el rojo.

Esa diferencia es la que evita las dos formas de mentir: dar por buena una
instalación a medias, y gritar por algo que todavía no le toca cargar.
"""
from __future__ import annotations

import csv
import json
import pathlib
from dataclasses import dataclass
from typing import Callable

RAIZ = pathlib.Path(__file__).resolve().parent
SEMILLAS = RAIZ / "seed_data"

GRUPO = "GRUPO"
PROPIEDAD = "PROPIEDAD"


@dataclass(frozen=True)
class Dataset:
    """Un pedazo de estructura: qué tabla lo guarda y cuánto tendría que haber."""

    clave: str
    #: La tabla donde vive. Se cuenta filtrando por hotel **si la tabla tiene
    #: columna de hotel** — se averigua leyendo el esquema, no una lista de acá.
    tabla: str
    familia: str
    #: De dónde sale el número esperado. Va en el mensaje: quien lee tiene que
    #: poder ir al archivo y contar.
    fuente: str
    #: El módulo del seed que la llena. Lo usa la prueba que vigila que ningún
    #: seed quede fuera de este inventario.
    modulo: str
    #: Lazy a propósito: importar los seeds al cargar este módulo ataría el API
    #: a ellos y encarecería el arranque.
    esperado: Callable[[], int]


def _json(nombre: str, clave: str) -> Callable[[], int]:
    def contar() -> int:
        datos = json.loads((SEMILLAS / nombre).read_text(encoding="utf-8"))
        return len(datos[clave])
    return contar


def _json_de_la_propiedad(nombre: str, clave: str) -> Callable[[], int]:
    """Cuenta en `seed_data/<HOTEL_ID>/…`. Sin archivo, cero.

    Cero acá significa «esta propiedad no trae semilla», que es distinto de
    «la semilla está vacía» — y por eso la familia PROPIEDAD no da error.
    """
    def contar() -> int:
        from app.hotel_actual import HOTEL_ID
        ruta = SEMILLAS / HOTEL_ID / nombre
        if not ruta.exists():
            return 0
        return len(json.loads(ruta.read_text(encoding="utf-8"))[clave])
    return contar


def _csv_de_la_propiedad(nombre: str) -> Callable[[], int]:
    def contar() -> int:
        from app.hotel_actual import HOTEL_ID
        ruta = SEMILLAS / HOTEL_ID / "break_even" / nombre
        if not ruta.exists():
            return 0
        # ⚠️ `utf-8` explícito: los nombres traen «Á», «—» y «·», y en Windows
        # el default es cp1252 — entrarían corruptos y el conteo sería otro.
        with ruta.open(encoding="utf-8", newline="") as f:
            return len(list(csv.DictReader(f)))
    return contar


def _catalogo_de_departamentos() -> int:
    from app.seed_department_catalog import build_rows
    return len(build_rows())


def _temporadas() -> int:
    from app.seed_costos_grupos import MAPA
    return len(MAPA)


def _parametros_de_costos() -> int:
    from app.seed_costos_grupos import PARAMETROS
    return len(PARAMETROS)


def _composicion() -> int:
    from app.seed_costos_grupos import COMPOSICION
    return sum(len(v) for v in COMPOSICION.values())


def _parametros_de_guillermo() -> int:
    from app.seed_guillermo import PARAMETROS
    return len(PARAMETROS)


def _manifiesto() -> int:
    """Lo que ESTA propiedad prometió que iba a subir. Sin manifiesto, cero.

    ⚠️ Cero no es «está todo bien»: es que Guillermo **no puede opinar**. Está
    escrito así en su propio módulo y acá se respeta — la familia PROPIEDAD no
    convierte un cero en error.
    """
    from app.hotel_actual import HOTEL_ID
    from app.seed_guillermo import MANIFIESTOS
    return len(MANIFIESTOS.get(HOTEL_ID, []))


#: Lo que tiene que estar en CUALQUIER instalación, venga de donde venga.
INVENTARIO: list[Dataset] = [
    # ── El motor contable ────────────────────────────────────────────────────
    Dataset("report_line_config", "report_line_config", GRUPO,
            "seed_data/mapping_pl.json", "seed_mapping",
            _json("mapping_pl.json", "report_line_config")),
    Dataset("account_mapping", "account_mapping", GRUPO,
            "seed_data/mapping_pl.json", "seed_mapping",
            _json("mapping_pl.json", "account_mapping")),
    Dataset("department_catalog", "department_catalog", GRUPO,
            "seed_department_catalog.build_rows()", "seed_department_catalog",
            _catalogo_de_departamentos),
    Dataset("stat_accounts", "stat_accounts", GRUPO,
            "seed_data/stats_catalog.json", "seed_stats",
            _json("stats_catalog.json", "cuentas")),
    Dataset("market_codes", "market_codes", GRUPO,
            "seed_data/market_codes.json", "seed_market_codes",
            _json("market_codes.json", "codigos")),
    # ── Owners Q ─────────────────────────────────────────────────────────────
    Dataset("report_lines", "report_lines", GRUPO,
            "seed_data/owners_q.json", "seed_owners_q",
            _json("owners_q.json", "report_lines")),
    Dataset("report_line_mapping", "report_line_mapping", GRUPO,
            "seed_data/owners_q.json", "seed_owners_q",
            _json("owners_q.json", "report_line_mapping")),
    # ── Costos de Grupos ─────────────────────────────────────────────────────
    Dataset("cfg_temporadas", "cfg_temporadas", GRUPO,
            "seed_costos_grupos.MAPA", "seed_costos_grupos", _temporadas),
    Dataset("cfg_parametros_costos", "cfg_parametros_costos", GRUPO,
            "seed_costos_grupos.PARAMETROS", "seed_costos_grupos",
            _parametros_de_costos),
    Dataset("cfg_composicion_costos", "cfg_composicion_costos", GRUPO,
            "seed_costos_grupos.COMPOSICION", "seed_costos_grupos", _composicion),
    # ── Guillermo ────────────────────────────────────────────────────────────
    Dataset("guillermo_config", "guillermo_config", GRUPO,
            "seed_guillermo.PARAMETROS", "seed_guillermo",
            _parametros_de_guillermo),
    Dataset("guillermo_expected_reports", "guillermo_expected_reports", PROPIEDAD,
            "seed_guillermo.MANIFIESTOS[HOTEL_ID]", "seed_guillermo", _manifiesto),
    # ── De la propiedad ──────────────────────────────────────────────────────
    Dataset("canales_comerciales", "canales_comerciales", PROPIEDAD,
            "seed_data/<HOTEL_ID>/canales_comerciales.json", "seed_canales_comerciales",
            _json_de_la_propiedad("canales_comerciales.json", "canales")),
    Dataset("cfg_tarifa_rack", "cfg_tarifa_rack", PROPIEDAD,
            "seed_data/<HOTEL_ID>/rack_rates.json", "seed_costos_grupos",
            _json_de_la_propiedad("rack_rates.json", "tarifas")),
    Dataset("be_department", "be_department", PROPIEDAD,
            "seed_data/<HOTEL_ID>/break_even/be_departments_seed.csv",
            "seed_break_even", _csv_de_la_propiedad("be_departments_seed.csv")),
    Dataset("be_cost_classification", "be_cost_classification", PROPIEDAD,
            "seed_data/<HOTEL_ID>/break_even/be_classification_seed.csv",
            "seed_break_even", _csv_de_la_propiedad("be_classification_seed.csv")),
]


def semillas_de_la_propiedad(hotel_id: str | None = None) -> tuple[list[str], list[str]]:
    """Qué archivos de arranque tiene esta propiedad, y cuáles le faltan.

    Estos NO llenan una tabla: son las sugerencias que la pantalla ofrece cuando
    algo está vacío —el paquete, las experiencias, las cuentas de opex, las
    tarifas de los drivers—. Por eso no entran en `INVENTARIO`, que cuenta
    filas. Pero son estructura igual: sin ellos la propiedad abre esas pantallas
    en blanco, y **en blanco no explica por qué**.

    ⚠️ **El catálogo de lo que puede existir se DERIVA de las carpetas que hay**,
    no de una lista escrita acá. Agregar un archivo nuevo a Corcovado lo vuelve
    parte de lo que se le pregunta a las demás, sin que nadie tenga que
    acordarse de anotarlo.
    """
    from app.hotel_actual import HOTEL_ID
    hotel = hotel_id or HOTEL_ID
    posibles: set[str] = set()
    for carpeta in SEMILLAS.iterdir():
        if not carpeta.is_dir() or carpeta.name.startswith(("_", ".")):
            continue
        posibles |= {a.name for a in carpeta.glob("*.json")}
    mias = {a.name for a in (SEMILLAS / hotel).glob("*.json")}         if (SEMILLAS / hotel).is_dir() else set()
    return sorted(mias), sorted(posibles - mias)
