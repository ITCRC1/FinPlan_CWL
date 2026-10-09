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
    #: Los renglones aprobados de cada Schedule: la otra mitad del libro.
    renglones: list["Renglon"] = field(default_factory=list)
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
                   renglones=leer_renglones(con_texto),
                   paginas=len(r.pages), paginas_con_texto=len(con_texto),
                   cruce=cruzar(entradas))


# ─────────────────────────────────────────────────────────────────────────────
# Los SCHEDULES: el formato de cada departamento
# ─────────────────────────────────────────────────────────────────────────────
#
# Cada Schedule —palabras del libro— «designates the revenue and expense
# accounts that are approved as line items in the Uniform System», y aclara que
# «the Uniform System does not provide for the addition or substitution of other
# revenue or expense line items».
#
# Es distinto del diccionario: el diccionario da EJEMPLOS de artículos; el
# Schedule da el RENGLÓN del reporte. Se guarda como referencia del panel —qué
# dice el estándar que lleva este departamento—, no como alarma.
#
# ⚠️ **Medido antes de construirlo.** Contra las 252 cuentas que usó setiembre
# 2026 la regla «esta cuenta no es renglón aprobado de su schedule» dio UN
# hallazgo, y dudoso: 130 cuentas (51.6%) son propias del hotel y el estándar
# nunca las nombró, y 68 (27.0%) caen en departamentos donde el libro no da
# lista. Como alarma no sirve en esta propiedad. Como referencia por
# departamento, sí.

#: El rótulo del cuadro, en MAYÚSCULAS: «ROOMS—SCHEDULE 1». La prosa que lo
#: explica usa el mismo nombre en minúsculas —«Rooms—Schedule 1 reflects…»—, y
#: por eso se distinguen sin mirar el número de página.
_TITULO_CUADRO = re.compile(r"^([A-Z][A-Z&/'\u2019,\.\- ]{3,60})[\u2014\-]+SCHEDULE\s+(\d+)\s*$")

#: Las dos frases con las que el libro declara que un schedule tiene lista
#: cerrada. Usa una u otra según el schedule: la 1 en Rooms y F&B, la 2 en
#: Miscellaneous Income y en Payroll-Related Expenses. El Schedule 3 —Other
#: Operated Departments— no trae ninguna, y por eso queda sin lista: dice
#: «only the revenues and expenses […] that exist at an individual property».
_DECLARA_LISTA = re.compile(
    r"approved as line items"
    r"|does not provide for the addition or substitution", re.I)

#: El nombre con que el DICCIONARIO llama a cada schedule. Es la llave de
#: apareo: las ~1.950 entradas del diccionario traen este nombre, no el del
#: título del cuadro.
NOMBRE_EN_DICCIONARIO = {
    "ROOMS": "Rooms",
    "FOOD AND BEVERAGE": "F&B",
    "OTHER OPERATED DEPARTMENTS": "Minor Oper. Dept",
    "MISCELLANEOUS INCOME": "Misc. Income",
    "ADMINISTRATIVE AND GENERAL": "A&G",
    "INFORMATION AND TELECOMMUNICATIONS SYSTEMS": "Info & Telecom",
    "SALES AND MARKETING": "Sales/Marketing",
    "PROPERTY OPERATION AND MAINTENANCE": "POM",
    "UTILITIES": "Utilities",
    "MANAGEMENT FEES": "Management Fees",
    "NON-OPERATING INCOME AND EXPENSES": "Non Op. I&E",
    "HOUSE LAUNDRY": "Laundry",
    "STAFF DINING": "Staff Dining",
    "PAYROLL-RELATED EXPENSES": "Payroll-Rel. Exp",
}

#: Lo que aparece en el cuadro y NO es un renglón de cuenta: encabezados de
#: columna, rótulos de periodo, totales, y los encabezados del bloque de
#: planilla que se repiten en los catorce schedules.
_NO_ES_RENGLON = re.compile(
    r"^\s*(\$|%|aCtual|foreCast|Budget|Prior|Year|Period|Current|to\-date"
    r"|SCHEDULE|Operating Statements|Uniform System|continued"
    r"|Total|TOTAL|Net |Gross |Departmental|REVENUE|EXPENSES"
    r"|Payroll|Cost of|Other Expenses"
    r"|Labor Costs and Related|Salaries, Wages|Labor and Bonuses"
    r"|Management$|Non\-Management$|Service Charges)\b", re.I)

#: Un renglón de cuenta: mayúscula inicial, sin relleno de puntos y sin montos.
_ES_RENGLON = re.compile(r"^[A-Z][A-Za-z0-9&/'\u2019\u2014\-,\. ]{2,60}$")


@dataclass
class Renglon:
    """Un renglón aprobado del reporte de un departamento."""
    numero: int            # el número del Schedule: 1..14
    titulo: str            # como lo titula el cuadro: ROOMS, HOUSE LAUNDRY…
    schedule: str          # como lo llama el diccionario: Rooms, Laundry…
    renglon: str           # el nombre del renglón: Linen, Contract Services…
    orden: int             # en qué posición lo trae el cuadro
    pagina: int
    lista_aprobada: bool   # ¿el libro declara lista cerrada para este schedule?


def leer_renglones(paginas: list[tuple[int, str]]) -> list[Renglon]:
    """Los renglones aprobados de cada Schedule, con su marca de lista cerrada.

    Encuentra los cuadros por su título en MAYÚSCULAS y lee hasta el título
    siguiente. La marca `lista_aprobada` sale de la prosa del propio libro, no
    de una lista escrita a mano: así otra edición sigue funcionando.
    """
    # 1 · ¿qué schedules declara el libro con lista aprobada?
    #
    # La prosa viene partida a mitad de palabra —«and des-\nignates the revenue
    # and expense accounts that are approved as line items»—, así que primero se
    # pega la página y se deshace el guion de corte.
    declara: dict[int, bool] = {}
    for _n, texto in paginas:
        plano = re.sub(r"[\u00ad\-]\s*\n\s*", "", texto)
        plano = " ".join(plano.split())
        for m in re.finditer(r"[\u2014\-]Schedule\s+(\d+)\b", plano):
            num = int(m.group(1))
            # La declaración viene en la misma oración que el nombre.
            cerca = plano[m.end():m.end() + 400]
            if _DECLARA_LISTA.search(cerca):
                declara[num] = True
            else:
                declara.setdefault(num, False)

    # 2 · los cuadros
    salida: list[Renglon] = []
    actual: tuple[int, str, str] | None = None
    vistos: set[tuple[int, str]] = set()
    for n, texto in paginas:
        for cruda in texto.split("\n"):
            s = _limpiar(cruda)
            if not s:
                continue
            t = _TITULO_CUADRO.match(s)
            if t:
                titulo = " ".join(t.group(1).split())
                dicc = NOMBRE_EN_DICCIONARIO.get(titulo)
                actual = (int(t.group(2)), titulo, dicc) if dicc else None
                continue
            if actual is None or len(s) < 3:
                continue
            if _NO_ES_RENGLON.match(s) or _NO_ES_RENGLON.match(cruda):
                continue
            if "...." in s or re.search(r"\d{2,}", s):
                continue
            if actual[1].lower() in s.lower():
                continue
            if not _ES_RENGLON.match(s):
                # Prosa: el cuadro terminó.
                if len(s) > 70:
                    actual = None
                continue
            k = (actual[0], s.lower())
            if k in vistos:
                continue
            vistos.add(k)
            salida.append(Renglon(
                numero=actual[0], titulo=actual[1], schedule=actual[2],
                renglon=s, orden=len(salida), pagina=n,
                lista_aprobada=declara.get(actual[0], False)))
    return salida
