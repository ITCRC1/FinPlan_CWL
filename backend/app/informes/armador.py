# -*- coding: utf-8 -*-
"""Arma el documento. Lo usan el endpoint y el script de linea de comandos.

La division que sostiene todo esto: **los cuadros son automaticos y el analisis
no**. Los 53 cuadros salen del corte igual todos los meses; el juicio —que
hallazgo va primero, si una favorabilidad es ahorro o diferimiento, que se le
pregunta a que gerente— se escribe a mano en
`seed_data/<HOTEL>/informes/<anio>_<mes>.json`.

Si falta narrativa el informe sale igual, con marcas «[PENDIENTE: clave]» en el
lugar del texto y la lista de lo que falta. Un hueco que se ve es util; una
seccion que desaparece sin avisar, no.
"""
from __future__ import annotations

import json
import pathlib
import re

from app.informes import secciones as S1
from app.informes import secciones2 as S2
from app.informes.datos import Datos
from app.informes.formato import doc_nuevo
from app.informes.plantilla import resolver


def ruta_narrativa(anio: int, mes: int, hotel: str | None = None) -> pathlib.Path:
    from app.hotel_actual import HOTEL_ID
    h = hotel or HOTEL_ID
    return (pathlib.Path(__file__).resolve().parents[1] / "seed_data" / h
            / "informes" / f"{anio}_{mes:02d}.json")


def cargar_narrativa(anio: int, mes: int, hotel: str | None = None) -> dict:
    """El analisis del mes, si alguien lo escribio.

    ⚠️ Vive en `seed_data/<HOTEL>/informes/` y no en `app/`, y no es un detalle
    de orden: es contenido DE UNA PROPIEDAD. Un clon no puede heredar el
    analisis de otro hotel —`tests/test_un_hotel_por_instalacion.py` no deja que
    el nombre de Corcovado viva dentro de `app/` como valor—.
    """
    ruta = ruta_narrativa(anio, mes, hotel)
    if not ruta.exists():
        return {}
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    datos.pop("_nota", None)
    return datos


def vigencia(D: Datos, nar: dict | None = None) -> dict:
    """Si el analisis escrito describe ESTE dato o uno anterior.

    ⚠️ Owner, 2026-10-15: *«me sigue mostrando una version antigua»*. El
    informe tiene dos mitades y solo una se rehace sola:

    * los 53 CUADROS salen del espejo, en vivo — siempre estan al dia;
    * el ANALISIS es texto a mano, con las cifras escritas adentro.

    El de setiembre 2026 se redacto el 8-oct. Para cuando se pidio, el mes
    llevaba dos subidas mas: el ingreso habia bajado $2.025, el costo de ventas
    $17.152, y el resultado estaba $23.492 peor. El documento salia completo,
    cuadraba, y su primer parrafo citaba una cifra que ya no existia.

    **Lo unico que fallaba era el silencio.** `armar()` avisaba de las secciones
    que FALTAN, no de las que estan y hablan de otro archivo. Un hueco se ve; una
    cifra vieja bien formateada, no.

    La narrativa declara contra que subida se escribio en `_contra.checksum`.
    Son dos huellas del CONTENIDO: si el archivo se vuelve a subir renombrado,
    el checksum es el mismo y el analisis sigue vigente, que es lo correcto.

    Sin `_contra` el veredicto es `"sin_declarar"`: no se puede afirmar que este
    vieja, y tampoco que este bien. Se dice eso y no se inventa ninguna de las
    dos.
    """
    if nar is None:
        nar = cargar_narrativa(D.anio, D.mes)
    sub = D.subida or {}
    contra = (nar or {}).get("_contra") or {}
    if not nar:
        return {"estado": "sin_analisis", "vigente": True, "aviso": "",
                "subida": sub, "contra": contra}
    if not contra.get("checksum"):
        return {"estado": "sin_declarar", "vigente": True,
                "aviso": ("El analisis escrito no declara contra que subida se "
                          "redacto: no se puede verificar que describa este dato."),
                "subida": sub, "contra": contra}
    if not sub.get("checksum"):
        return {"estado": "sin_subida", "vigente": True,
                "aviso": ("No hay una subida viva de Pre-Cierre para el mes: no "
                          "se puede verificar la vigencia del analisis."),
                "subida": sub, "contra": contra}
    if contra["checksum"] == sub["checksum"]:
        return {"estado": "vigente", "vigente": True, "aviso": "",
                "subida": sub, "contra": contra, "cifras_a_mano": 0}

    # El mes se volvio a subir. Cuanto duele depende de si el texto todavia
    # lleva cifras ESCRITAS A MANO.
    #
    # Owner, 2026-10-17: *«seguire moviendo setiembre..pero hay que hacer lo
    # necesario para que esto funcione»*. Desde las marcas `{{...}}`, los
    # numeros se refrescan solos: una subida nueva ya no vuelve falso el texto.
    # Lo que SI puede envejecer es el juicio —«Ventas y Mercadeo ahorro 4,1%»
    # paso a «gasto 45% de mas» entre dos archivos del mismo mes— y eso ningun
    # mecanismo lo puede recalcular.
    # ⚠️ El autor DECLARA cuantas cifras dejo a mano a proposito. Son las
    # historicas —«entre el 16 y el 17 el gasto se movio US$9.799,86»—, que
    # hablan del pasado y no envejecen con una subida nueva. Si aparecen MAS de
    # las declaradas, alguien escribio una cifra del mes dentro del texto y el
    # aviso vuelve a ser duro.
    declaradas = int(contra.get("cifras_fijas") or 0)
    a_mano = max(0, _cifras_a_mano(nar) - declaradas)
    de_a_de = (
        f"El mes se volvio a subir: el analisis se escribio contra "
        f"«{contra.get('archivo') or '?'}» del {contra.get('fecha') or '?'}"
        + (f" (TC {contra['tc']})" if contra.get("tc") else "")
        + f" y los cuadros salen de «{sub.get('archivo') or '?'}» del "
        f"{sub.get('fecha') or '?'}"
        + (f" (TC {sub['tc']})" if sub.get("tc") else "") + ".")
    if a_mano:
        return {
            "estado": "vencido", "vigente": False, "cifras_a_mano": a_mano,
            "aviso": (de_a_de + f" El texto todavia tiene {a_mano} cifra"
                      f"{'s' if a_mano != 1 else ''} escrita"
                      f"{'s' if a_mano != 1 else ''} a mano, que ya no "
                      "corresponden: hay que reescribirlo o pasarlas a marcas."),
            "subida": sub, "contra": contra}
    return {
        "estado": "revisar_juicio", "vigente": True, "cifras_a_mano": 0,
        "aviso": (de_a_de + " Las cifras del texto se recalcularon solas; lo que "
                  "conviene revisar es el JUICIO —que hallazgo va primero, si "
                  "una favorabilidad es ahorro o diferimiento—, porque eso no "
                  "se recalcula."),
        "subida": sub, "contra": contra}


#: Una cifra escrita a mano en el texto: `$40.178,28`, `1.234,56`, `-53,3%`.
#: ⚠️ Se buscan solo numeros con separador de miles o decimales. Un «3» suelto
#: es casi siempre parte de una frase («tres gerentes», «clase 7»), y marcarlo
#: convertiria el aviso en ruido que nadie lee.
_CIFRA = re.compile(r"-?\$?\d{1,3}(?:\.\d{3})+(?:,\d+)?|-?\d+,\d+\s*%?")


def _cifras_a_mano(x) -> int:
    """Cuantas cifras quedan escritas a mano en la narrativa, sin resolver."""
    if isinstance(x, str):
        return len(_CIFRA.findall(x))
    if isinstance(x, dict):
        return sum(_cifras_a_mano(v) for k, v in x.items()
                   if not k.startswith("_"))
    if isinstance(x, (list, tuple)):
        return sum(_cifras_a_mano(v) for v in x)
    return 0


def armar(D: Datos, nar: dict | None = None):
    """Devuelve `(documento, faltantes)`.

    `faltantes` son las claves de narrativa que no estaban: es lo que hay que
    escribir para que el informe quede completo.
    """
    if nar is None:
        nar = cargar_narrativa(D.anio, D.mes)
    # ⚠️ Las marcas se resuelven UNA vez, sobre la narrativa entera, ANTES de
    # que ninguna seccion la toque. Asi vale para parrafos, vinetas, celdas de
    # cuadro y preguntas sin tocar las doce funciones que arman el documento —
    # y sin que manana alguien agregue una seccion que se olvide de resolver.
    sin_resolver: list[str] = []
    nar = resolver(nar, D, sin_resolver)
    S1.FALTANTES.clear()
    S1.FALTANTES.extend(f"marca: {x}" for x in sin_resolver)
    agg = D.mayor()

    d = doc_nuevo()
    S1.portada(d, D, nar, vigencia(D, nar))
    S1.indice(d, D)
    d.add_page_break()
    S1.seccion1(d, D, nar)
    d.add_page_break()
    S1.seccion2(d, D, nar)
    d.add_page_break()
    S1.seccion3(d, D, nar)
    d.add_page_break()
    S2.seccion4(d, D, agg, nar)
    d.add_page_break()
    S2.seccion5(d, D, agg, nar)
    d.add_page_break()
    S2.seccion6(d, D, nar)
    d.add_page_break()
    S2.seccion7(d, D, nar)
    d.add_page_break()
    S2.seccion8(d, D, nar)
    S2.seccion9(d, D, nar)
    d.add_page_break()
    S2.seccion10(d, D, nar)
    d.add_page_break()
    S2.seccion11(d, D, nar)
    d.add_page_break()
    S2.seccion12(d, D, nar)
    return d, sorted(set(S1.FALTANTES))


def cuadre(D: Datos) -> dict:
    """Los numeros que tienen que coincidir con la pantalla, y la verificacion
    del GOP.

    ⚠️ **El invariante es que los dos GOP sean IGUALES.** El del reporte —por
    naturaleza, ingreso menos clases 5/6/7— y el del motor —por departamento—
    son dos caminos al mismo numero.

    Hasta el 2026-10-09 diferian por el credito de reparto de la cuenta 4999,
    que el tab descartaba mientras mostraba su gasto: $18.789,30 en setiembre
    2026 y $35.763,30 en los dos meses cargados. Ya entra, y por eso ahora se
    exige CERO. Si vuelve a aparecer una diferencia y resulta ser el credito,
    el aviso lo dice: es la causa que ya se conoce.
    """
    cred = sum(D.creditos_allocation().values())
    motor = D.pl("ACT", "GOP") or D.pl("ACT", "TOTAL_GOP")
    dif = D.gop("ACT") - motor
    cuadra = abs(dif) < 0.02
    return {
        "escenarios": [
            {"clave": e, "rotulo": D.rotulo(e),
             "ingreso": round(D.total(e, "revenue"), 2),
             "gasto": round(D.tot_gasto(e), 2),
             "gop": round(D.gop(e), 2)}
            for e in D.escs],
        "credito_allocation": round(cred, 2),
        "gop_reporte": round(D.gop("ACT"), 2),
        "gop_motor": round(motor, 2),
        "diferencia": round(dif, 2),
        "cuadra": cuadra,
        "motivo": ("" if cuadra else
                   "la diferencia es el credito de reparto 4999: volvio a quedar "
                   "fuera del reporte" if abs(dif - cred) < 0.02 else
                   "la diferencia NO es el credito de reparto: hay otra causa"),
    }
