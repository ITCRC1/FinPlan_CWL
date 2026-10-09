# -*- coding: utf-8 -*-
"""Lee el USALI y lo convierte en algo que el sistema pueda consultar.

El libro —*Uniform System of Accounts for the Lodging Industry*, 11.ª edición—
trae dos partes que se complementan, y las dos hacen falta:

1. **El diccionario de ingresos y gastos** (unas 105 páginas): cada artículo o
   concepto, con el departamento y la cuenta donde va. «Cots → Rooms /
   Operating Supplies». Es lo que permite revisar un asiento contra el estándar.

2. **Las definiciones de cuenta** (unas 130 páginas): un párrafo por cuenta con
   lo que incluye y lo que no. Es lo que sirve para juzgar lo que el diccionario
   no cubre, que es casi todo lo raro.

## El diccionario viene DOS VECES, y eso es lo mejor que tiene

El mismo contenido está ordenado por artículo y por departamento/cuenta:

    Item Name  Schedule Account Name      ->  Artículo | Departamento | Cuenta
    Schedule Account Name Item Name       ->  Departamento | Cuenta | Artículo

El encabezado de cada página dice cuál es. Leer los dos y cruzarlos es la única
forma barata de saber si la extracción salió bien: lo que coincide en los dos
ordenamientos está bien leído. Un catálogo de miles de reglas que nadie verificó
va a marcar mal, y a la tercera vez que marque mal nadie vuelve a abrir la
pantalla.

⚠️ **El texto es material con derechos de AHLA/HFTP.** Se guarda para uso
interno de la propiedad que compró el libro. No se reproduce en reportes que
salgan a terceros ni viaja a un clon como si fuera del sistema.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

#: Tres puntos o más: el relleno entre columnas.
PUNTOS = re.compile(r"\.{3,}")

#: Lo que no es una entrada: encabezados de página y de sección.
BASURA = re.compile(
    r"Uniform System of Accounts|Revenue and Expense Guide|Revenue Guide"
    r"|Expense Guide|Section (One|Two|Three)|Item Name|Schedule Account"
    r"|Department/")

#: Los encabezados que delatan el ordenamiento de la página.
_POR_CUENTA = "Schedule Account Name Item Name"
_POR_ITEM = "Item Name"


#: Los departamentos (schedules) del USALI. Es un vocabulario CERRADO y chico, y
#: en eso esta la gracia: la columna que contiene uno de estos ES el
#: departamento, sin importar en que orden venga la linea.
#:
#: ⚠️ Decidir por el ENCABEZADO de la pagina no funciona. El libro cambia de
#: seccion a mitad de pagina —en la 266 termina la guia de ingresos y empieza la
#: de gastos— y el encabezado de columnas aparece recien en la siguiente. Con el
#: orden arrastrado, 1.800 entradas quedaron con el departamento y el articulo
#: intercambiados sin que nada lo dijera.
SCHEDULES = {
    "rooms", "f b", "a g", "pom", "sales marketing", "mult depts",
    "info telecom", "non op i e", "golf pro shop", "health club spa",
    "misc income", "payroll rel exp", "utilities", "parking",
    "minor oper dept", "cost of sales", "laundry", "garage parking",
    "telecommunications", "other oper depts", "allowances",
}


@dataclass
class Entrada:
    """Un artículo del diccionario: dónde dice el estándar que va."""
    item: str
    schedule: str          # el departamento del USALI: Rooms, F&B, A&G…
    cuenta: str            # el nombre de cuenta: Operating Supplies, Linen…
    pagina: int
    orden: str             # de cuál de los dos ordenamientos salió


@dataclass
class Definicion:
    """Una cuenta con su definición, tal como la explica el libro."""
    cuenta: str
    texto: str
    pagina: int


@dataclass
class Lectura:
    entradas: list[Entrada] = field(default_factory=list)
    #: El catalogo fusionado: lo que de verdad se guarda y se consulta.
    catalogo: list["ItemCatalogo"] = field(default_factory=list)
    definiciones: list[Definicion] = field(default_factory=list)
    paginas: int = 0
    paginas_con_texto: int = 0
    #: Lo que coincidió entre los dos ordenamientos y lo que no.
    cruce: dict = field(default_factory=dict)


def _limpiar(s: str) -> str:
    # El PDF trae guiones largos como U+FFFD por un problema de codificación de
    # la fuente; se restituyen para que «Ribbons—typewriter» no quede ilegible.
    s = s.replace("�", "—").replace("’", "'").replace("“", '"')
    s = s.replace("”", '"')
    return " ".join(s.split()).strip(" .")


def _orden_de(texto: str) -> str | None:
    cab = texto[:500]
    if _POR_CUENTA in cab:
        return "por_cuenta"
    if _POR_ITEM in cab and "Account Name" in cab:
        return "por_item"
    return None


def leer_diccionario(paginas: list[tuple[int, str]]) -> list[Entrada]:
    """Las entradas del diccionario, de las dos secciones del libro.

    ⚠️ **El orden de las columnas se decide por LINEA, no por pagina.** La
    columna que contenga un departamento conocido ES el departamento; las otras
    dos quedan determinadas por su posicion respecto de el:

        Rooms ... Linen ... Robes          -> depto, cuenta, articulo
        Robes ... Rooms ... Linen          -> articulo, depto, cuenta

    Confiar en el encabezado de la pagina costaba 1.800 entradas con el
    departamento y el articulo intercambiados — ver la nota en `SCHEDULES`.

    ⚠️ **Y una linea sin puntos puede ser dos cosas distintas.** Si viene
    SANGRADA es la continuacion de la anterior; si arranca en la primera
    columna es el PRINCIPIO de la siguiente, que no cupo en un renglon:

        Beverage assessment (this is not other tax        <- principio
        and assessment) .............. F&B ...... Cost of Beverage Sales

        F&B ... Misc. Cost ... Banquet/conference/catering
         recoverable supplies                             <- continuacion

    Tratar las dos igual era el otro error: partia articulos a la mitad y
    pegaba el principio de uno al final del anterior.
    """
    salida: list[Entrada] = []
    for num, texto in paginas:
        colgando: Entrada | None = None
        prefijo = ""
        for linea in texto.splitlines():
            if not linea.strip():
                continue
            if BASURA.search(linea) or re.fullmatch(r"\s*\d{1,4}\s*", linea):
                colgando, prefijo = None, ""
                continue

            if not PUNTOS.search(linea):
                if linea[:1].isspace() and colgando is not None:
                    campo = "cuenta" if colgando.orden == "por_item" else "item"
                    setattr(colgando, campo,
                            _limpiar(getattr(colgando, campo) + " " + linea))
                else:
                    prefijo = _limpiar(prefijo + " " + linea)
                continue

            partes = [p for p in (_limpiar(x) for x in PUNTOS.split(linea)) if p]
            if len(partes) < 3:
                colgando, prefijo = None, ""
                continue
            a, b, c = partes[0], partes[1], " ".join(partes[2:])
            if prefijo:
                a = _limpiar(prefijo + " " + a)
                prefijo = ""
            if _norm(a) in SCHEDULES:
                e = Entrada(item=c, schedule=a, cuenta=b, pagina=num,
                            orden="por_cuenta")
            elif _norm(b) in SCHEDULES:
                e = Entrada(item=a, schedule=b, cuenta=c, pagina=num,
                            orden="por_item")
            else:
                # Ninguna columna trae un departamento conocido. No se adivina:
                # una entrada inventada es peor que una entrada que falta.
                colgando = None
                continue
            salida.append(e)
            colgando = e
    return salida


#: Una definición arranca con el nombre de la cuenta en negrita seguido de punto
#: y de «Includes». No se puede ver la negrita en el texto plano, así que se
#: reconoce por la forma: un nombre corto en mayúsculas iniciales, punto, y una
#: oración que empieza explicando qué incluye.
_DEFINICION = re.compile(
    r"^([A-Z][A-Za-z0-9&/'’\-—,\. ]{2,70}?)\.\s+"
    r"((?:Includes|Include|This account|Refer to|Represents)\b.*)$")


def leer_definiciones(paginas: list[tuple[int, str]]) -> list[Definicion]:
    """Las definiciones de cuenta del cuerpo del libro.

    Se arma por párrafo: el renglón que abre con «Nombre. Includes…» empieza
    una definición, y los renglones siguientes la continúan hasta el próximo
    nombre o el fin de la página.
    """
    salida: list[Definicion] = []
    for num, texto in paginas:
        actual: Definicion | None = None
        for linea in texto.split("\n"):
            s = linea.strip()
            if not s or BASURA.search(s) or re.fullmatch(r"\s*\d{1,4}\s*", s):
                continue
            m = _DEFINICION.match(_limpiar(s))
            if m:
                actual = Definicion(cuenta=_limpiar(m.group(1)),
                                    texto=_limpiar(m.group(2)), pagina=num)
                salida.append(actual)
            elif actual is not None:
                actual.texto = _limpiar(actual.texto + " " + s)
    return salida


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def cruzar(entradas: list[Entrada]) -> dict:
    """Compara los dos ordenamientos del diccionario.

    Lo que coincide está bien leído. Lo que aparece en uno solo hay que mirarlo
    — casi siempre es una continuación que se partió distinto.
    """
    A = {(_norm(e.item), _norm(e.schedule), _norm(e.cuenta))
         for e in entradas if e.orden == "por_item"}
    B = {(_norm(e.item), _norm(e.schedule), _norm(e.cuenta))
         for e in entradas if e.orden == "por_cuenta"}
    return {
        "por_item": len(A), "por_cuenta": len(B),
        "coinciden": len(A & B),
        "solo_por_item": len(A - B), "solo_por_cuenta": len(B - A),
        "confianza": round(len(A & B) / max(len(A | B), 1), 4),
    }


@dataclass
class ItemCatalogo:
    """Un articulo del catalogo, ya fusionado y con su nivel de confianza."""
    item: str
    schedule: str
    cuenta: str
    #: `confirmado` = los dos ordenamientos dicen lo mismo. `unico` = solo uno
    #: de los dos lo trae. Nunca se mezclan en un mismo reporte sin decir cual
    #: es cual: una regla que marca a un gerente tiene que poder decir de donde
    #: salio.
    confianza: str
    paginas: str


def fusionar(entradas: list[Entrada]) -> list[ItemCatalogo]:
    """Un solo catalogo a partir de los dos ordenamientos.

    ⚠️ **El nombre de cuenta se toma del ordenamiento por cuenta.** El libro
    abrevia en la columna angosta —«Storage Fee Rev» contra «Storage Fee
    Revenue», «Other Property & Equipment» contra «...and Equipment»— y el
    ordenamiento por departamento/cuenta es el que la trae completa.

    El DEPARTAMENTO no necesita desempate: medido sobre el libro entero, los
    1.651 articulos que aparecen en los dos ordenamientos coinciden en
    departamento el 100% de las veces. Esa es la verificacion de que la lectura
    salio bien.
    """
    por_item: dict[str, list[Entrada]] = {}
    por_cuenta: dict[str, list[Entrada]] = {}
    for e in entradas:
        (por_item if e.orden == "por_item" else por_cuenta).setdefault(
            _norm(e.item), []).append(e)

    salida: list[ItemCatalogo] = []
    for clave in sorted(set(por_item) | set(por_cuenta)):
        a = por_item.get(clave, [])
        b = por_cuenta.get(clave, [])
        # Un articulo puede ir a mas de un lado —«Apparel sales» esta en F&B y
        # en Spa— y eso NO es ambiguedad: son destinos distintos segun donde se
        # venda. Se guardan los dos.
        destinos: dict[tuple, ItemCatalogo] = {}
        for e in b + a:
            k = (_norm(e.schedule), _norm(e.cuenta))
            # El mismo destino visto desde los dos lados: se queda el nombre de
            # cuenta mas largo, que es el no abreviado.
            gemelo = next((d for kk, d in destinos.items()
                           if kk[0] == k[0] and (kk[1].startswith(k[1])
                                                 or k[1].startswith(kk[1]))), None)
            if gemelo is not None:
                if len(e.cuenta) > len(gemelo.cuenta):
                    gemelo.cuenta = e.cuenta
                gemelo.confianza = "confirmado"
                gemelo.paginas = ",".join(sorted(
                    set(gemelo.paginas.split(",")) | {str(e.pagina)}))
                continue
            destinos[k] = ItemCatalogo(
                item=e.item, schedule=e.schedule, cuenta=e.cuenta,
                confianza="unico", paginas=str(e.pagina))
        salida.extend(destinos.values())
    return salida


def leer_pdf(datos: bytes) -> Lectura:
    """Todo el libro: diccionario, definiciones y el cruce de verificación."""
    import pypdf

    r = pypdf.PdfReader(io.BytesIO(datos))
    paginas: list[tuple[int, str]] = []
    for i, p in enumerate(r.pages):
        try:
            paginas.append((i + 1, p.extract_text() or ""))
        except Exception:
            # Una página ilegible no puede tumbar las otras 390.
            paginas.append((i + 1, ""))

    con_texto = [(n, t) for n, t in paginas if t.strip()]
    #: El diccionario son las páginas que traen el encabezado de columnas; las
    #: definiciones, el resto del cuerpo. Se separan por contenido y no por
    #: número de página, para que otra edición del libro siga funcionando.
    dicc, cuerpo, en_dicc = [], [], False
    for n, t in con_texto:
        if _orden_de(t):
            en_dicc = True
        elif en_dicc and "Index" in t[:200]:
            en_dicc = False
        (dicc if en_dicc else cuerpo).append((n, t))

    entradas = leer_diccionario(dicc)
    definiciones = leer_definiciones(cuerpo)
    return Lectura(entradas=entradas, catalogo=fusionar(entradas),
                   definiciones=definiciones,
                   paginas=len(r.pages), paginas_con_texto=len(con_texto),
                   cruce=cruzar(entradas))
