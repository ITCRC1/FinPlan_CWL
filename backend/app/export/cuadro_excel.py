"""Exportador GENÉRICO de cuadros a Excel, con el formato de la casa.

**Por qué existe.** El owner pidió que todos los cuadros de todos los tabs se
puedan bajar a Excel con formato profesional. Son ~47 pantallas sin exportación
y ~11 más que exportan mal. Escribir 47 exportadores a mano no es viable: cada
uno son 200 líneas y todos se desincronizan del estilo con el tiempo.

**Y hay una razón técnica que cierra la discusión.** Las 10 pantallas que hoy
bajan Excel lo hacen desde el navegador con `xlsx` (SheetJS Community), que **no
escribe estilos de celda**: negrita, relleno, bordes y formato de moneda son de
la edición paga. Con esa librería, «formato profesional» es imposible por más
código que se escriba. Por eso esto vive en el servidor, con `openpyxl`.

**El contrato.** La pantalla manda lo que YA tiene renderizado:

    {
      "titulo": "Big Picture — Budget 2027",
      "subtitulo": "Corcovado · USD",          # opcional
      "columnas": [
        {"label": "Concepto", "ancho": 42, "formato": "texto"},
        {"label": "2026",     "ancho": 14, "formato": "usd"},
        {"label": "Var %",    "ancho": 10, "formato": "pct"},
      ],
      "filas": [
        {"label": "Ingresos",       "nivel": 0, "es_total": True,  "valores": [1000, 0.12]},
        {"label": "  Habitaciones", "nivel": 1, "es_total": False, "valores": [800, 0.10]},
      ],
    }

Los valores van como NÚMERO, nunca como texto ya formateado. Es la diferencia
entre un Excel que se puede sumar y uno que no — hoy `/reports/summary` manda
`"$1,234.00"` como cadena y el archivo resultante no sirve para nada.

Un libro puede llevar varios cuadros: cada uno es su hoja. Las pantallas con
tabs (allocations tiene 12 cuadros, cash flow directo 6) bajan todo de una.
"""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties

from openpyxl.comments import Comment
from openpyxl.worksheet.hyperlink import Hyperlink

from app.export.excel_base import (
    C, align, border, fill, font, marco_total, merged_header, nombre_de_hoja,
    set_col_widths, workbook_to_bytes,
)

# Mismos formatos que `pl_full_detail_excel`, que es la referencia del repo:
# negativo en rojo y entre paréntesis, y el cero NO se imprime — una grilla
# llena de ceros esconde las cifras que sí importan.
FORMATOS = {
    "usd":   '#,##0;[Red](#,##0);""',
    "usd2":  '#,##0.00;[Red](#,##0.00);""',
    "pct":   '0.0%;[Red](0.0%);""',
    "num":   '#,##0;[Red](#,##0);""',
    "num1":  '#,##0.0;[Red](#,##0.0);""',
    "texto": None,
}

FILA_TITULO = 1
#: ⚠️ **El subtítulo YA NO se escribe en la hoja.**
#:
#: Owner, 2026-09-30: *«que no bajen en el excel los textos insertados. que
#: bajen limpios»*.
#:
#: Era prosa —«la varianza del full year es Forecast contra Budget: el Actual
#: del año todavía no existe…»— en una banda combinada sobre las columnas. En
#: pantalla explica; en una hoja de cálculo estorba: rompe el filtro, se lleva
#: el ancho de la primera columna al copiar, y aparece pegada arriba del cuadro
#: cuando alguien lo pega en otro lado.
#:
#: Sigue viajando: va en la hoja ÍNDICE, que es donde se lee una vez, y en el
#: Word, que es un documento y no una tabla.
#:
#: ⚠️ **La constante se queda en 2 y la fila queda EN BLANCO.** Bajarla a 1
#: subiría la tabla una fila, y hay un `test_sin_franja_el_cuadro_arranca_donde_
#: siempre` que defiende justamente lo contrario: media docena de pruebas —y de
#: macros de quien ya usa estos archivos— buscan la cabecera en la fila 4. Lo
#: que se pidió fue sacar el texto, no mover el cuadro.
FILA_SUBTITULO = 2
FILA_CABECERA = 4
PRIMERA_FILA = 5


def _kpis(ws, cuadro: dict, desde: int) -> int:
    """La franja de estadísticas, arriba del cuadro. Devuelve la fila siguiente.

    Owner, 2026-09-03: *«no están saliendo las estadísticas en cada tab»*.

    ⚠️ En la pantalla la franja se dibuja UNA vez arriba de los sub-tabs, así
    que se ve en todos. Acá **cada hoja se lee sola** —se imprime, se manda
    suelta— y sin las estadísticas al lado los montos no tienen contra qué
    leerse: 56.001 de ingreso con 132 noches vendidas dice algo muy distinto
    que con 400.

    Va en gris y compacta: es contexto, no el cuadro.
    """
    filas = cuadro.get("kpis") or []
    columnas = cuadro.get("kpis_columnas") or []
    if not filas or not columnas:
        return desde

    # ── La franja NO repite los rótulos de columna ────────────────────────
    #
    # Owner, 2026-09-30: *«necesito que esto quede super alineado»*.
    #
    # ⚠️ Los repetía, y era exactamente lo que se veía torcido: el rótulo de una
    # columna de tres cortes es «AGOSTO 2026 / ACTUAL Final», más largo que la
    # celda, y sin relleno detrás Excel lo derrama sobre la celda vecina. En la
    # hoja salía «O 2026ACTUAL Final»: dos rótulos pisados, corridos respecto de
    # la cabecera de abajo.
    #
    # La cabecera de verdad está DOS FILAS más abajo y en las MISMAS columnas.
    # Con la franja alineada a esas columnas, cada estadística cae encima de su
    # corte y de su versión sin que haya que rotularla otra vez.
    # ⚠️ La raya que abre cada bloque baja también por la franja: si se cortara
    # antes de las estadísticas, el mes y el acumulado quedarían separados en la
    # tabla y pegados arriba.
    cols = cuadro.get("columnas") or []
    grupo = lambda i: cols[i - 1] if 0 < i <= len(cols) else {}   # noqa: E731

    fila = desde
    c = ws.cell(fila, 1, "ESTADÍSTICAS")
    c.font = font(bold=True, size=9, color=C["cab_titulo"])
    c.fill = fill(C["banda_seccion"])
    c.border = border(sides="all_top")
    for i in range(2, len(columnas) + 2):
        c = ws.cell(fila, i)
        c.fill = fill(C["banda_seccion"])
        c.border = _con_grupo(border(sides="all_top"), grupo(i))
    fila += 1

    for f in filas:
        rot = str(f.get("label") or "")
        c = ws.cell(fila, 1, rot)
        c.font = font(size=9)
        c.alignment = align("left")
        c.border = border()
        for i in range(2, len(columnas) + 2):
            ws.cell(fila, i).border = _con_grupo(border(), grupo(i))
        # El formato lo decide el rótulo: la ocupación es un porcentaje y la
        # tarifa son dólares. Mandarlo por fila desde la pantalla sería una
        # tercera copia de la misma decisión.
        bajo = rot.lower()
        fmt = ("pct" if "%" in rot else
               "usd2" if ("adr" in bajo or "daily" in bajo or "revpar" in bajo
                          or "cuota" in bajo) else "num")
        for i, v in enumerate(f.get("valores") or [], start=2):
            if i > len(columnas) + 1:
                break
            celda = ws.cell(fila, i, v)
            celda.number_format = FORMATOS.get(fmt, FORMATOS["usd"])
            celda.alignment = align("right")
            celda.font = font(size=9)
            celda.border = _con_grupo(border(), grupo(i))
        fila += 1
    return fila + 1          # una en blanco antes del cuadro


def _formula(col: dict, f: dict, filas: list[dict], i: int, fila: int,
             primera: int) -> str | None:
    """La celda como FÓRMULA, cuando se puede decir con certeza cuál es.

    Owner, 2026-09-30: *«los subtotales, totales y variaciones deben ser
    fórmulas reales»*. Un Excel de junta se toca: alguien corrige un actual y
    espera que la variación se mueva.

    Dos formas, y sólo esas dos:

    * `columnas[n].resta = [a, b]` → `=Xn-Yn`. Una variación es exactamente eso
      y no hay margen de error.
    * `columnas[n].suma_cols = [...]` → `=SUMA(D5:O5)`. La columna «Año» de un
      cuadro de doce meses.
    * `filas[n].suma_de = [...]` → `=X7+X9+X12`.
    * `filas[n].combina_filas = [[7, 1], [9, -1]]` → `=X7-X9`. La cascada: GOP
      es Operating Profit menos Overhead, y eso no es una suma.

    ⚠️ **La suma se escribe SÓLO si da lo mismo que el número que venía.** El
    total del P&L lo calcula el motor, no la pantalla: si el cuadro no muestra
    todos sus componentes —o los muestra netos de un reparto— la suma daría
    otra cifra y el Excel diría algo que el sistema no dice. Cuando no cuadra se
    deja el número: se pierde la fórmula, que es el lado correcto en el que
    equivocarse.
    """
    # ⚠️ Una celda VACÍA se queda vacía. Un blanco no es un cero: la fila de
    # sección no tiene números, y `=B12-C12` sobre dos celdas vacías es un cero
    # —que el formato esconde hoy, pero que suma si alguien copia la columna—.
    if (f.get("valores") or [None] * i)[i - 2] is None:
        return None

    letra = get_column_letter(i)
    resta = col.get("resta")
    if resta and len(resta) == 2:
        a, b = (get_column_letter(x + 1) for x in resta)
        return f"={a}{fila}-{b}{fila}"

    vals = f.get("valores") or []

    # ⚠️ **La tolerancia depende de la UNIDAD de la celda.**
    #
    # Medio centavo en una columna de dólares es ruido de redondeo. En una de
    # PORCENTAJE, 0,005 es medio punto: tres variaciones porcentuales pueden
    # caer ahí por pura casualidad y entonces se escribiría `=E8+E9+E10` en una
    # celda que es un cociente — una fórmula que se ve bien y está mal, que es
    # justo lo que esta comprobación existe para impedir.
    #
    # Un cociente no se suma: el costo de A&B del período no es la suma de tres
    # porcentajes. Donde la cifra es una razón, la suma tiene que dar exacta o
    # no se escribe. Una participación sobre el ingreso —que sí es aditiva—
    # cuadra al bit y sigue bajando como fórmula.
    razon = (f.get("formato") or col.get("formato") or "usd") == "pct"
    tol = 1e-9 if razon else CENTAVO

    def cuadra(valor, partes) -> bool:
        """⚠️ La fórmula se escribe SÓLO si da lo mismo que el número que vino.

        Vale para las dos sumas. Un índice mal puesto —o un cuadro que no
        muestra todos sus componentes— daría otra cifra, y una fórmula se ve
        más confiable que un número: nadie la revisaría.
        """
        return abs(sum(partes) - valor) <= tol

    # ── La columna que suma otras columnas ────────────────────────────────
    #
    # ⚠️ Si no cuadra NO se devuelve `None`: se sigue con `suma_de`. En la
    # esquina de un cuadro de doce meses la celda es fila-total y columna-suma a
    # la vez, y basta con que una de las dos sea cierta para que valga la pena
    # escribirla.
    cols = col.get("suma_cols")
    if cols:
        partes, texto = [], False
        for k in cols:
            # ⚠️ Un mes VACÍO no invalida la suma: en Excel un blanco vale cero
            # tanto en `SUM(B5:M5)` como en `B5+C5`, que es lo mismo que hace la
            # pantalla al totalizar con `?? 0`. Descartar la fórmula por un mes
            # sin cargar le quitaría el total justo a las filas incompletas, que
            # son las que hay que revisar.
            v = vals[k - 1] if 0 < k <= len(vals) else None
            if v is None:
                continue
            if isinstance(v, str):
                texto = True
                break
            partes.append(float(v))
        if not texto:
            try:
                valor = float(vals[i - 2])
            except (IndexError, TypeError, ValueError):
                valor = None
            if valor is not None and cuadra(valor, partes):
                letras = [get_column_letter(k + 1) for k in cols]
                # Doce meses seguidos se leen mejor como rango que como doce
                # sumandos.
                if list(cols) == list(range(cols[0], cols[-1] + 1)):
                    return f"=SUM({letras[0]}{fila}:{letras[-1]}{fila})"
                return "=" + "+".join(f"{x}{fila}" for x in letras)

    suma = f.get("suma_de")
    if suma:
        try:
            valor = float(vals[i - 2])
            partes = [float((filas[k].get("valores") or [])[i - 2]) for k in suma]
        except (IndexError, TypeError, ValueError):
            return None
        if not cuadra(valor, partes):
            return None      # el motor dice otra cosa: manda el motor
        return "=" + "+".join(f"{letra}{primera + k}" for k in suma)

    # ── La fila que COMBINA otras con signo ───────────────────────────────
    #
    # La cascada del P&L no se suma: el GOP es Operating Profit MENOS Overhead,
    # el EBITDA le resta los no operativos, el EBT lo financiero y la
    # depreciación, y el Net Profit el impuesto. Son las cinco líneas que todo
    # el mundo mira, y sin esto quedaban como número pegado mientras el detalle
    # de arriba ya bajaba con fórmula.
    combina = f.get("combina_filas")
    if not combina:
        return None
    try:
        valor = float(vals[i - 2])
        partes = [signo * float((filas[k].get("valores") or [])[i - 2])
                  for k, signo in combina]
    except (IndexError, TypeError, ValueError):
        return None
    if not cuadra(valor, partes):
        return None
    texto = ""
    for k, signo in combina:
        pieza = f"{letra}{primera + k}"
        texto += (pieza if not texto and signo > 0
                  else ("+" if signo > 0 else "-") + pieza)
    return "=" + texto


#: Hasta dónde puede diferir la suma de lo que se ve del número del motor, en
#: una columna de dinero.
#:
#: ⚠️ **Es un centavo, y no medio.** La comprobación existe para atrapar una
#: composición EQUIVOCADA —un total al que le faltan componentes, o que los
#: muestra netos de un reparto—, y eso aparece en dólares, no en centavos.
#:
#: Medido sobre la cascada real de Amarena, los tres ámbitos por los tres
#: cortes por las tres versiones: de 468 celdas candidatas, 76 pasaban de medio
#: centavo y sólo 12 pasaban de uno. Las 64 del medio son el redondeo de sumar
#: doce meses en otro orden que el motor; las 12 son descuadres de verdad —el
#: mayor, 5.942,28, es el Owners Fee del Club que el ámbito Hotel le resta al
#: detalle y no al subtotal—. Con medio centavo se perdía una de cada seis
#: fórmulas para no dejar pasar nada que ya se rechazaba igual.
#:
#: El precio es que la celda recalculada puede moverse un centavo respecto del
#: número que el motor dejó en caché. A cambio, la columna suma.
CENTAVO = 0.011

#: El grosor de la raya que separa un bloque de columnas del siguiente.
#:
#: Owner, 2026-09-30: *«se identifica con una línea gruesa lo que es Agosto,
#: YTD Agosto y Full Year»*. Sin ella, nueve columnas de montos son nueve
#: columnas de montos: no se ve dónde termina el mes y empieza el acumulado.
_GRUESA = Side(style="medium", color="000000")


def _borde_cabecera(col: dict, arriba: bool, abajo: bool) -> Border:
    fino = Side(style="thin", color=C["raya"])
    return Border(
        left=_GRUESA if col.get("abre_grupo") else fino,
        right=fino,
        top=_GRUESA if arriba else None,
        bottom=_GRUESA if abajo else None,
    )


def _con_grupo(base: Border, col: dict) -> Border:
    """El mismo borde de la celda, con la raya gruesa del grupo a la izquierda.

    ⚠️ Se aplica a TODAS las filas y no sólo a la cabecera: una raya que se
    corta debajo del encabezado no separa nada."""
    if not col.get("abre_grupo"):
        return base
    return Border(left=_GRUESA, right=base.right, top=base.top,
                  bottom=base.bottom)


#: El valor calculado de cada celda que lleva fórmula: `(hoja, celda) → número`.
#:
#: ⚠️ **Por qué hace falta.** `openpyxl` escribe `<f>B14-C14</f>` y NADA más: la
#: celda no trae el resultado. Excel debería calcularlo al abrir —el libro sale
#: con `fullCalcOnLoad`— pero si el usuario tiene el cálculo en Manual, o abre
#: el archivo en un visor que no evalúa, **las celdas salen en blanco**. Le pasó
#: al owner (2026-09-30): *«no pusiste los cálculos de las varianzas»* y *«los
#: checkbooks no tienen subtotales ni totales»* — estaban, como fórmula, y no se
#: veían.
#:
#: Un archivo de Excel de verdad guarda las dos cosas: la fórmula y su último
#: resultado. Eso es lo que se hace acá.
_VALORES_DE_FORMULA: dict[tuple[str, str], float] = {}


def _hoja(wb: Workbook, cuadro: dict, usados: set[str]):
    columnas = cuadro.get("columnas") or []
    filas = cuadro.get("filas") or []
    titulo = (cuadro.get("titulo") or "Cuadro").strip()
    n_col = max(1, len(columnas))

    ws = wb.create_sheet(nombre_de_hoja(cuadro.get("hoja") or titulo, usados))

    merged_header(ws, FILA_TITULO, 1, n_col, titulo, C["cab_titulo"], sz=13)

    # ⚠️ La cabecera del cuadro se corre hacia abajo lo que ocupe la franja.
    # Las constantes de fila eran fijas; con la franja delante, escribir la
    # tabla en la fila 4 la pisaría.
    FILA_CABECERA = _kpis(ws, cuadro, FILA_SUBTITULO + 2)

    # ── La cabecera, en DOS líneas ───────────────────────────────────────
    #
    # Owner, 2026-09-30, con una captura de cómo la quiere: *«esta vista se ve
    # muy cargada y está en la misma celda… podrás ver que se usan 2 celdas»*.
    #
    # Arriba la versión —«Actual», «Budget», «Variance»— y abajo el período
    # —«Agosto», «YTD Agosto», «Full Year»—. Antes iba todo junto y envuelto en
    # una celda: «Agosto · ACTUAL Final» en dos renglones que no significan
    # nada por separado.
    #
    # ⚠️ La segunda fila sólo existe si alguna columna trae `sub`. Un cuadro sin
    # períodos —el mapeo de cuentas, los anexos— no tiene por qué ganar una fila
    # en blanco.
    dos_lineas = any((col.get("sub") or "").strip() for col in columnas)
    FILA_SUB = FILA_CABECERA + 1 if dos_lineas else FILA_CABECERA
    PRIMERA_FILA = FILA_SUB + 1

    for i, col in enumerate(columnas, start=1):
        # La primera columna es la etiqueta de la fila; el resto son números.
        pos = "left" if i == 1 else "center"
        c = ws.cell(FILA_CABECERA, i, col.get("label", ""))
        c.fill = fill(C["cab_tabla"])
        c.font = font(bold=True, color=C["cab_texto"], size=10)
        c.alignment = align(pos, wrap=True)
        c.border = _borde_cabecera(col, arriba=True, abajo=not dos_lineas)
        if dos_lineas:
            c2 = ws.cell(FILA_SUB, i, (col.get("sub") or "").strip() or None)
            c2.fill = fill(C["cab_tabla"])
            c2.font = font(bold=True, color=C["cab_sub"], size=9.5)
            c2.alignment = align(pos, wrap=True)
            c2.border = _borde_cabecera(col, arriba=False, abajo=True)

    detalle = 0
    for j, f in enumerate(filas):
        fila = PRIMERA_FILA + j
        # ── Tres estados de fila, y son tres cosas distintas ─────────────────
        #
        # Owner, 2026-09-30, mostrando el tab que arregló a mano:
        #
        #   normal    rejilla fina gris, sin relleno, sin negrita
        #   sección   relleno pálido, negrita, raya arriba — SIN marco negro
        #   total     recuadro NEGRO medio + relleno + negrita
        #
        # ⚠️ Antes había sólo dos: el encabezado de sección compartía marcador
        # con el total, así que «REVENUES» salía con el mismo peso visual que
        # «NET PROFIT» y el ojo no encontraba dónde cierra cada bloque.
        es_seccion = bool(f.get("es_seccion"))
        es_total = bool(f.get("es_total")) and not es_seccion
        nivel = int(f.get("nivel") or 0)
        ultima_col = min(n_col, 1 + len(f.get("valores") or []))

        # La jerarquía va con SANGRÍA de Excel, no con espacios dentro del texto.
        # Con espacios, ordenar la columna o copiarla a otro lado se lleva la
        # sangría puesta y el nivel deja de significar nada. Es lo que hace hoy
        # `/reports/expenses`, que simula la jerarquía con espacios.
        etiqueta = ws.cell(fila, 1, f.get("label", ""))
        etiqueta.font = font(bold=es_total or es_seccion,
                             color=C["tinta"])
        etiqueta.alignment = Alignment(horizontal="left", vertical="center",
                                       indent=min(nivel, 8))
        etiqueta.border = border()
        # ⚠️ La cebra se cuenta sobre las filas de DETALLE, no sobre `j`. Con
        # `j` los encabezados de sección y los totales entran en la cuenta y la
        # alternancia se salta un renglón cada vez que pasa uno: el ojo pierde
        # el hilo justo donde más falta hace, en un checkbook de doce meses.
        cebra = False
        if not (es_total or es_seccion):
            cebra = detalle % 2 == 1
            detalle += 1
            if cebra:
                etiqueta.fill = fill(C["cebra"])
        if es_total:
            etiqueta.fill = fill(C["banda_total"])
            etiqueta.border = marco_total(True, n_col == 1)
        elif es_seccion:
            etiqueta.fill = fill(C["banda_seccion"])
            etiqueta.border = border(sides="all_top")

        # La fila puede pisar el formato de la columna. Hace falta cuando un mismo
        # cuadro mezcla unidades en la misma columna — el bloque de drivers del
        # Big Picture tiene noches, ocupación % y ADR en dólares, una debajo de
        # otra. Sin esto habría que partirlo en tres cuadros.
        fmt_fila = f.get("formato")

        for i, valor in enumerate(f.get("valores") or [], start=2):
            if i > n_col:
                break
            formula = _formula(columnas[i - 1], f, filas, i, fila, PRIMERA_FILA)
            celda = ws.cell(fila, i, formula or valor)
            if formula is not None and isinstance(valor, (int, float)):
                _VALORES_DE_FORMULA[(ws.title, celda.coordinate)] = float(valor)
            fmt = FORMATOS.get(fmt_fila or columnas[i - 1].get("formato") or "usd",
                               FORMATOS["usd"])
            if fmt:
                celda.number_format = fmt
            # El texto se alinea a la izquierda: una columna de nombres de cuenta
            # alineada a la derecha es ilegible. Pasa en las pantallas de mapeo,
            # que son casi todas de texto (cuenta · departamento · línea del P&L).
            celda.alignment = align("left" if isinstance(valor, str) else "right")
            celda.font = font(bold=es_total or es_seccion,
                              color=C["tinta"])
            col = columnas[i - 1]
            if es_total:
                # ⚠️ El negro sólo en los extremos. En todas las celdas, el
                # total saldría con la rejilla negra y parecería otra tabla.
                celda.border = _con_grupo(marco_total(False, i == ultima_col), col)
                celda.fill = fill(C["banda_total"])
            elif es_seccion:
                celda.border = _con_grupo(border(sides="all_top"), col)
                celda.fill = fill(C["banda_seccion"])
            else:
                celda.border = _con_grupo(border(), col)
                if cebra:
                    celda.fill = fill(C["cebra"])

        # ⚠️ Si la fila trae menos valores que columnas, el marco se cortaría a
        # media tabla. Se completan las celdas que faltan con el mismo formato y
        # sin contenido: el recuadro tiene que llegar a la última columna.
        if es_total or es_seccion:
            for i in range(max(2, ultima_col + 1), n_col + 1):
                celda = ws.cell(fila, i)
                celda.fill = fill(C["banda_total"] if es_total
                                  else C["banda_seccion"])
                celda.border = _con_grupo(
                    marco_total(False, i == n_col) if es_total
                    else border(sides="all_top"), columnas[i - 1])

    set_col_widths(ws, {i: (col.get("ancho") or (38 if i == 1 else 14))
                        for i, col in enumerate(columnas, start=1)})
    # Congelar la cabecera y la columna de etiquetas: sin esto, un cuadro de 12
    # meses obliga a adivinar qué fila se está mirando al llegar a diciembre.
    ws.freeze_panes = ws.cell(PRIMERA_FILA, 2)

    # ── Que imprima en UNA hoja ──────────────────────────────────────────────
    #
    # Owner, 2026-08-27: «el Excel debe ser en una sola página sin separar». Un
    # cuadro de 12 meses son 14 columnas: en vertical y sin ajuste, Excel lo
    # parte en tres o cuatro hojas y los meses quedan repartidos entre papeles
    # distintos. Un reporte partido no se puede leer ni mandar.
    #
    # `fitToPage` en `sheet_properties.pageSetUpPr` es OBLIGATORIO: sin él,
    # `fitToWidth`/`fitToHeight` quedan escritos en el archivo y Excel los
    # ignora — se ve bien en el XML y sale partido igual.
    #
    # `fitToHeight = 0` es «las hojas de alto que haga falta». Se usa 1 porque
    # el pedido es una sola hoja; un cuadro larguísimo sale con letra chica,
    # que es preferible a que se parta.
    ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_margins.left = ws.page_margins.right = 0.3
    ws.page_margins.top = ws.page_margins.bottom = 0.4
    # ⚠️ **Sin la cuadrícula de Excel** (owner, 2026-09-30: *«quitar el grid de
    # la vista de excel en todas las tabs»*). El cuadro ya trae sus propias
    # rayas; encima la cuadrícula del programa, que sigue hasta el borde de la
    # pantalla, hace que la tabla no tenga fin y que todo se vea igual de
    # importante.
    ws.sheet_view.showGridLines = False
    # El área de impresión se acota a lo escrito: sin esto, una celda tocada
    # por accidente lejos de la tabla arrastra hojas en blanco.
    ultima = PRIMERA_FILA + max(0, len(filas)) - 1
    if ultima >= FILA_TITULO:
        ws.print_area = f"A{FILA_TITULO}:{get_column_letter(n_col)}{ultima}"
    return ws


def _indice(wb: Workbook, cuadros: list[dict], nombres: list[str]) -> None:
    """La portada del libro: qué trae y en qué hoja está cada cosa.

    Owner, 2026-09-03: *«que baje bien profesional y claro»*, pidiendo que el
    Excel traiga todos los sub-tabs «tal como Word».

    ⚠️ El Word tiene su página de CONTENIDO; un libro de doce hojas sin índice
    obliga a recorrer las pestañas de abajo una por una, y los nombres van
    cortados a 31 caracteres —«Profit & Loss Statement YTD JU»—, así que ni
    siquiera se leen enteros. El índice es donde el título completo cabe.

    Va PRIMERO y con los nombres tal como quedaron, no como se pidieron: si dos
    cuadros se llamaban parecido, el libro los desambiguó y el índice tiene que
    mostrar el nombre real de la pestaña o no sirve para encontrarla.
    """
    ws = wb.create_sheet("Índice", 0)
    merged_header(ws, 1, 1, 3, "CONTENIDO", C["cab_titulo"], sz=13)
    for i, rotulo in enumerate(("#", "Hoja", "Cuadro"), start=1):
        c = ws.cell(3, i, rotulo)
        c.fill = fill(C["cab_tabla"])
        c.font = font(bold=True, color=C["white"], size=10)
        c.alignment = align("left")
        c.border = border()
    for j, (cuadro, hoja) in enumerate(zip(cuadros, nombres)):
        fila = 4 + j
        titulo = (cuadro.get("titulo") or "Cuadro").strip()
        sub = (cuadro.get("subtitulo") or "").strip()
        #: La descripción de UNA línea que el owner escribió a mano
        #: (2026-09-30). El título completo y el subtítulo largo pasan a ser la
        #: NOTA de la celda: siguen estando —explican cómo se calcula cada
        #: tab— sin volver el índice una pared de texto.
        corta = (cuadro.get("descripcion") or "").strip() or titulo
        banda = _banda_del_bloque(hoja)
        for i, valor in enumerate((j + 1, hoja, corta), start=1):
            c = ws.cell(fila, i, valor)
            c.alignment = align("left")
            c.border = border()
            if banda:
                c.fill = fill(banda)
            c.font = font(size=10)
        # ── El nombre de la hoja, como LINK ───────────────────────────────
        #
        # Owner, 2026-09-30: *«cada nombre es un link a su hoja»*. Un libro de
        # dieciocho pestañas se recorre con el índice o no se recorre: las
        # lengüetas de abajo van cortadas a 31 caracteres y hay que buscarlas
        # una por una.
        #
        # ⚠️ El nombre va entre comillas simples. Sin ellas, una hoja con
        # espacios —«P&L Ago Consolidado»— rompe la referencia y Excel abre el
        # archivo diciendo que el link no es válido.
        celda = ws.cell(fila, 2)
        # ⚠️ `location` y NO `hyperlink = "#'Hoja'!A1"`. Asignando una cadena,
        # openpyxl la guarda como destino EXTERNO: Excel abre el archivo
        # avisando que el vínculo no es válido y el link no lleva a ningún lado.
        celda.hyperlink = Hyperlink(ref=celda.coordinate,
                                    location=f"'{hoja}'!A1")
        celda.font = font(size=10, color="1F4E79", underline="single")
        # ── La explicación larga, como NOTA ───────────────────────────────
        #
        # No se pierde: explica cómo se calcula cada tab. Pero en la celda
        # convertía el índice en una pared de texto (owner, 2026-09-30: una
        # descripción corta por hoja).
        largo = titulo + (f" · {sub}" if sub else "")
        if largo.strip() and largo.strip() != corta:
            ws.cell(fila, 3).comment = Comment(largo, "FinPlan", width=420,
                                               height=170)
    set_col_widths(ws, {1: 5, 2: 34, 3: 88})
    ws.freeze_panes = ws.cell(4, 1)
    ws.sheet_view.showGridLines = False    # también acá: son TODAS las hojas
    # ⚠️ El índice también se imprime, y sin esto salía partido en DOS hojas:
    # la descripción, que es la columna ancha, caía sola en la segunda. Un
    # índice en dos papeles no es un índice.
    ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_margins.left = ws.page_margins.right = 0.3
    ws.page_margins.top = ws.page_margins.bottom = 0.4
    ws.print_area = f"A1:C{3 + len(cuadros)}"


#: Con qué color se pinta cada bloque del índice.
#:
#: ⚠️ Por el nombre de la hoja y no por el orden: el paquete se puede reordenar
#: desde «Armar paquete», y con el orden las bandas quedarían repartidas al azar.
#: ⚠️ Tres pasteles de la MISMA familia, para que el índice se lea como un
#: documento y no como una alerta. El primero era un rosa (`F3DFE0`): al lado de
#: una banda azul, un renglón rosa se lee como que algo está mal, y lo que marca
#: es el bloque del P&L.
_BLOQUES = (
    ("P&L", "DEE8F0"),          #: los tres estados de resultados — azul pálido
    ("Checkbook", "E8EADF"),    #: el detalle por cuenta — arena
)
_BANDA_RESTO = "E3EDE8"         #: estadística y anexos — salvia


def _banda_del_bloque(hoja: str) -> str:
    for prefijo, color in _BLOQUES:
        if hoja.startswith(prefijo):
            return color
    return _BANDA_RESTO


def _con_resultados(blob: bytes, valores: dict[tuple[str, str], float]) -> bytes:
    """El mismo libro, con el RESULTADO guardado al lado de cada fórmula.

    ⚠️ **No es un adorno: es lo que hace que los números se vean.** `openpyxl`
    escribe la fórmula sin su resultado, y una celda así sale en blanco en
    cualquier programa que no la evalúe al abrir —incluido Excel con el cálculo
    en Manual—. Un archivo de Excel de verdad guarda las dos cosas.

    ⚠️ Si algo sale mal, se devuelve el libro TAL CUAL. Un archivo con las
    fórmulas sin resultado se arregla con F9; uno corrupto no se abre.
    """
    if not valores:
        return blob
    try:
        import re
        import xml.etree.ElementTree as ET
        import zipfile

        zin = zipfile.ZipFile(io.BytesIO(blob))
        # Qué archivo es cada hoja. El orden de `sheetN.xml` no es garantía:
        # se sigue el r:id, que es lo que el formato define.
        NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
        libro = ET.fromstring(zin.read("xl/workbook.xml"))
        rels = ET.fromstring(zin.read("xl/_rels/workbook.xml.rels"))
        destino = {r.get("Id"): r.get("Target") for r in rels}
        archivo_de = {}
        for h in libro.iter(f"{NS}sheet"):
            t = destino.get(h.get(f"{R}id"), "")
            archivo_de[h.get("name")] = "xl/" + t.lstrip("/").removeprefix("xl/")

        por_archivo: dict[str, dict[str, float]] = {}
        for (hoja, celda), v in valores.items():
            if hoja in archivo_de:
                por_archivo.setdefault(archivo_de[hoja], {})[celda] = v

        salida = io.BytesIO()
        with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                datos = zin.read(item.filename)
                celdas = por_archivo.get(item.filename)
                if celdas:
                    texto = datos.decode("utf-8")

                    def pegar(m, celdas=celdas):
                        ref, cuerpo = m.group(1), m.group(0)
                        if ref not in celdas:
                            return cuerpo
                        # `.10g` deja el número como lo escribiría Excel, sin
                        # arrastrar los decimales del binario.
                        valor = f"{celdas[ref]:.10g}"
                        # ⚠️ `openpyxl` YA escribe un `<v></v>` VACÍO en cada
                        # celda con fórmula. Ése es el que hay que reemplazar:
                        # un resultado en blanco es lo que hacía que la celda
                        # saliera vacía. Si algún día dejara de escribirlo, se
                        # inserta detrás de `</f>`.
                        if "<v></v>" in cuerpo:
                            return cuerpo.replace("<v></v>", f"<v>{valor}</v>")
                        return cuerpo.replace("</f>", f"</f><v>{valor}</v>", 1)

                    texto = re.sub(
                        # ⚠️ Todo el patrón se detiene en el primer `</c>`:
                        # sin ese freno, un `.*?` puede saltar a la fórmula de
                        # la celda siguiente y pegar el resultado en la que no
                        # es.
                        r'<c r="([A-Z]+\d+)"[^>]*>(?:(?!</c>).)*?'
                        r'<f>(?:(?!</c>).)*?</f>(?:<v>[^<]*</v>)?</c>',
                        pegar, texto, flags=re.S)
                    datos = texto.encode("utf-8")
                zout.writestr(item, datos)
        return salida.getvalue()
    except Exception:
        return blob


def build_cuadros_workbook(cuadros: list[dict]) -> bytes:
    """Un libro con una hoja por cuadro, y un índice adelante."""
    _VALORES_DE_FORMULA.clear()      # el libro anterior no contamina a éste
    wb = Workbook()
    wb.remove(wb.active)
    usados: set[str] = set()
    nombres: list[str] = []
    for cuadro in cuadros or []:
        nombres.append(_hoja(wb, cuadro, usados).title)
    # ⚠️ El índice sólo cuando hay VARIAS hojas. En un libro de una, una portada
    # que dice «1. esa hoja» es un clic de más para llegar al único cuadro.
    if len(nombres) > 1:
        _indice(wb, cuadros or [], nombres)
    if not wb.sheetnames:            # nunca devolver un libro sin hojas
        wb.create_sheet("Sin datos")
    return _con_resultados(workbook_to_bytes(wb), _VALORES_DE_FORMULA)
