"""El hotel de ESTA instalación.

**Modelo de despliegue: un hotel = un proyecto aparte** — base propia, app
propia. No es multi-tenant en una sola base. Por eso la identidad del hotel sale
del ENTORNO y no de una tabla de hoteles ni de un selector: cada despliegue *es*
un hotel.

    HOTEL_ID=AMA HOTEL_NAME="Amarena Canvas Beach Hotel" …

Los cuatro prefijos del grupo (owner, 2026-08-12):

    CWL  Corcovado Wilderness Lodge
    AMA  Amarena
    OXI  Oxígen
    OJO  Ojochal

**No se validan acá a propósito:** una lista cerrada en el código obligaría a
tocar el repo para abrir la quinta propiedad, y el valor ya viene del entorno de
cada despliegue. El default es `CWL` para que Corcovado no cambie de
comportamiento. Lo mismo que
hace `app/seed.py`, que es quien crea la fila del hotel al arrancar.

**Por qué existe este módulo:** había 20 literales `"CWL"` repartidos por la API
y los modelos. En Corcovado son inofensivos; en un despliegue de Amarena cada uno
es una fila estampada con el hotel equivocado, o un `db.get(Hotel, "CWL")` que
devuelve `None` y rompe sin decir por qué. Una sola fuente evita las dos cosas.
"""
import os

# ID del hotel de esta instalación. Se lee UNA vez al importar: cambiarlo en
# caliente no tendría sentido —sería cambiar de hotel a mitad de un request— y
# leerlo por llamada solo escondería el error.
HOTEL_ID: str = os.getenv("HOTEL_ID", "CWL")


def hotel_id() -> str:
    """Para usar como `Depends`/default sin congelar el valor en la firma."""
    return HOTEL_ID


# Nombre visible, para los encabezados de los Excel que arma el servidor.
#
# La verdad del nombre vive en la tabla `hotels` y se edita en Provisionamiento;
# esto es el valor de arranque, porque los exportadores arman el encabezado sin
# tener a mano la fila del hotel. En un despliegue bien provisionado los dos
# coinciden. **Si el owner renombra la propiedad desde la pantalla, el
# encabezado de estos Excel sigue el valor del entorno hasta que se actualice la
# variable** — queda anotado en `docs/PLAN_TRABAJO_AUTONOMO.md`.
HOTEL_NAME: str = os.getenv("HOTEL_NAME", "Corcovado Wilderness Lodge")
HOTEL_SHORT: str = os.getenv("HOTEL_SHORT_NAME", HOTEL_ID)


def hotel_slug() -> str:
    """Sin espacios ni acentos: los dos rompen descargas en algunos navegadores.

    Es función y no constante para que el día que el nombre salga de la base
    —y no del entorno— no haya que tocar a los que la usan.
    """
    import re
    import unicodedata

    base = unicodedata.normalize("NFD", HOTEL_SHORT)
    base = "".join(c for c in base if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_") or HOTEL_ID
