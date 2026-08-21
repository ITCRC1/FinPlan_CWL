# -*- coding: utf-8 -*-
"""Semillas de arranque, POR PROPIEDAD.

Una «semilla» es lo que el sistema **sugiere** cuando una tabla todavía está
vacía: los componentes del paquete, las experiencias, los canales de venta. La
respuesta del API la marca `seeded: true` — es una sugerencia, no dato guardado.

**El problema que resuelve este módulo (owner, 2026-08-14).** Esas sugerencias
eran las de Corcovado, escritas dentro del código, y los endpoints no preguntaban
de qué hotel eran: su condición era «¿la tabla está vacía?». Una propiedad recién
abierta —correctamente identificada por su `HOTEL_ID`— recibía igual el paquete
con el transporte Sierpe/Drake, el tour a San Pedrillo y el de Isla del Caño.

No corrompía nada por sí solo: la semilla vive en la respuesta, no en la base.
Pero está a un clic de dejar de ser sugerencia — alguien abre la pantalla, ve
algo razonable, guarda, y el presupuesto queda con el producto de otro hotel.

**Cómo funciona ahora.** Cada propiedad tiene su carpeta:

    app/seed_data/<HOTEL_ID>/paquete.json
                             experiencias.json
                             canales.json

Si la carpeta no existe —que es el caso de toda propiedad nueva— `semilla()`
devuelve `None` y la pantalla nace **en blanco**, que es la verdad: todavía no se
ha cargado nada. Corcovado ve exactamente lo de siempre porque sus archivos
salieron de las constantes, valor por valor.

**Por qué archivos y no un `if hotel == …`:** para abrir la quinta propiedad no
hay que tocar el repo, solo agregar una carpeta. Y una prueba vigila que no
vuelvan a aparecer constantes `CWL_*` dentro de los endpoints.
"""
import json
import pathlib
from decimal import Decimal

from app.hotel_actual import HOTEL_ID

_RAIZ = pathlib.Path(__file__).resolve().parent


def _a_decimal(o):
    """Los números viajan como texto en el JSON para no perder precisión.

    Se reconvierten a Decimal porque el motor de revenue calcula con Decimal: un
    float acá se arrastraría hasta el P&L.
    """
    if isinstance(o, str):
        try:
            return Decimal(o)
        except Exception:
            return o
    if isinstance(o, dict):
        return {k: _a_decimal(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_a_decimal(v) for v in o]
    return o


def semilla(nombre: str, hotel_id: str | None = None):
    """La semilla `nombre` de ESTA propiedad, o `None` si no tiene.

    `None` no es un error: es una propiedad que todavía no cargó lo suyo. Quien
    llama decide qué mostrar — normalmente, nada.
    """
    ruta = _RAIZ / (hotel_id or HOTEL_ID) / f"{nombre}.json"
    if not ruta.exists():
        return None
    return _a_decimal(json.loads(ruta.read_text(encoding="utf-8")))


def tiene_semillas(hotel_id: str | None = None) -> bool:
    """¿Esta propiedad trae datos de arranque? Útil para el mensaje de la UI."""
    return (_RAIZ / (hotel_id or HOTEL_ID)).is_dir()


def semilla_cruda(nombre: str, hotel_id: str | None = None):
    """La semilla `nombre` TAL COMO ESTA EN EL ARCHIVO, sin tocar los tipos.

    `semilla()` convierte a `Decimal` toda cadena que parezca un numero, porque
    sus tres archivos alimentan el motor de revenue y un float ahi se arrastra
    hasta el P&L. Pero esa misma conversion **rompe los codigos**: `"7005"` se
    vuelve `Decimal('7005')` y `"0113"` se vuelve `Decimal('113')` — el
    departamento pierde el cero de adelante y deja de existir, en silencio.

    Los codigos de cuenta, de departamento y los nombres de canal son LLAVES, no
    cantidades. Se leen por aca.
    """
    ruta = _RAIZ / (hotel_id or HOTEL_ID) / f"{nombre}.json"
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))
