# -*- coding: utf-8 -*-
"""El informe operativo no puede salir callado hablando de otra subida.

Owner, 2026-10-15, con el informe de setiembre abierto: *«genere el informe
operativo y me sigue mostrando una version antigua..debe actualizarse con los
datos que recien subi»*.

Tenía razón a medias, y la mitad que tenía es la peligrosa.

## Dos mitades, y solo una se rehace sola

* Los **53 cuadros** salen del espejo de Pre-Cierre, en vivo. Estaban al día.
* El **análisis** es texto escrito a mano, con las cifras adentro
  (`seed_data/<HOTEL>/informes/<año>_<mes>.json`). El de setiembre 2026 se
  redactó el 8-oct 22:54. Para cuando se pidió, el mes llevaba DOS subidas más:

      ingreso         $42.203,47  ->  $40.178,27     -$2.025
      costo de ventas $27.625,90  ->  $10.474,13    -$17.152
      otros gastos   $110.051,61  -> $150.204,86    +$40.153
      resultado     -$329.874,23  -> -$353.366,69    -$23.492

  El primer párrafo abría citando «$42.203,46 de ingreso». Esa cifra ya no
  existía en ninguna parte.

## Lo único que fallaba era el silencio

`armar()` avisaba de las secciones que **faltan** —marcas `[PENDIENTE]`—, nunca
de las que **están y hablan de otro archivo**. El documento salía completo,
cuadraba contra el motor, y mentía. Un hueco se ve; una cifra vieja bien
formateada no se ve nunca.

⚠️ Por eso el veredicto NO bloquea la descarga. Bloquear obligaría a reescribir
el análisis antes de poder mirar los cuadros nuevos, que es justo lo que uno
necesita para reescribirlo. Sale, y lo dice en rojo en la portada.
"""
import inspect

from app.informes.armador import vigencia
from app.informes.datos import Datos


def _datos(subida):
    """Un `Datos` mínimo: `vigencia()` solo mira `D.subida`."""
    d = Datos.__new__(Datos)
    d.anio, d.mes, d.subida = 2026, 9, subida
    return d


VIEJA = {"checksum": "aaa111", "archivo": "upload PL Setiembre 2026 v1.xlsx",
         "fecha": "2026-10-08 00:22:34", "tc": 454.75, "estado": "descartado"}
NUEVA = {"checksum": "bbb222", "archivo": "saldo setiembre closing period 2026.xlsx",
         "fecha": "2026-10-16 03:22:11", "tc": 458.43, "estado": "borrador"}


def test_el_analisis_de_otra_subida_se_marca_vencido():
    """El caso del owner, exactamente."""
    v = vigencia(_datos(NUEVA), {"resumen": "...", "_contra": VIEJA})
    assert v["estado"] == "vencido"
    assert v["vigente"] is False
    # Y el aviso NOMBRA los dos archivos: sin eso no se sabe qué reescribir.
    assert "upload PL Setiembre 2026 v1.xlsx" in v["aviso"]
    assert "saldo setiembre closing period 2026.xlsx" in v["aviso"]
    assert "454.75" in v["aviso"] and "458.43" in v["aviso"]


def test_el_mismo_contenido_sigue_vigente_aunque_cambie_el_nombre():
    """⚠️ La huella es del CONTENIDO, no del nombre.

    El mismo archivo se sube renombrado todo el tiempo —`INTEGRITY1.xlsx`,
    `v3.xlsx`—. Si la comparación fuera por nombre, cada renombrado invalidaría
    un análisis que sigue siendo correcto, y el aviso se volvería ruido que
    nadie lee.
    """
    otro_nombre = dict(NUEVA, archivo="saldo setiembre FINAL.xlsx")
    v = vigencia(_datos(otro_nombre), {"resumen": "...", "_contra": NUEVA})
    assert v["vigente"] is True
    assert v["estado"] == "vigente"


def test_sin_declarar_no_afirma_ninguna_de_las_dos_cosas():
    """Un análisis viejo, de antes de esta regla, no declara `_contra`. No se
    puede decir que esté vencido —puede estar perfecto— ni que esté vigente."""
    v = vigencia(_datos(NUEVA), {"resumen": "..."})
    assert v["estado"] == "sin_declarar"
    assert v["vigente"] is True          # no bloquea
    assert "no declara" in v["aviso"]    # pero lo dice


def test_sin_analisis_no_hay_nada_que_desmentir():
    """Si nadie escribió el mes, el informe ya sale con marcas [PENDIENTE]:
    agregarle un segundo aviso sería repetir lo mismo más fuerte."""
    v = vigencia(_datos(NUEVA), {})
    assert v["estado"] == "sin_analisis"
    assert v["vigente"] is True and not v["aviso"]


def test_la_subida_descartada_NO_es_la_que_manda():
    """⚠️ El mes se sube muchas veces durante la revisión y cada intento deja un
    «descartado». Comparar contra el último de esos diría que el análisis está
    vencido cuando no lo está."""
    fuente = inspect.getsource(
        __import__("app.informes.extraccion", fromlist=["x"]).extraer)
    assert "estado <> 'descartado'" in fuente
    assert "ORDER BY creado_en DESC LIMIT 1" in fuente


def test_el_aviso_viaja_al_BOTON_no_solo_al_documento():
    """Un aviso que solo vive dentro del .docx se lee después de haberlo
    mandado. Owner, 2026-10-15: el informe ya había salido así."""
    import pathlib

    api = pathlib.Path(__file__).resolve().parents[1] / "app" / "api" / "informe_api.py"
    txt = api.read_text(encoding="utf-8", errors="replace")
    assert '"X-Informe-Analisis-Vigente"' in txt
    # El literal viene partido en dos lineas en el fuente: se mira la lista
    # de cabeceras expuestas ya unida, no como esta escrita.
    i = txt.index("Access-Control-Expose-Headers")
    expuestas = txt[i:i + 400].replace('"', "").replace("\n", "")
    assert "X-Informe-Analisis-Vigente" in expuestas
    assert "X-Informe-Vigencia" in expuestas
    # ⚠️ El aviso lleva acentos y comillas; una cabecera HTTP es latin-1.
    assert "quote(v[" in txt

    front = pathlib.Path(__file__).resolve().parents[2] / "frontend"
    pantalla = (front / "app" / "month-end" / "pl" / "Pantalla.tsx").read_text(
        encoding="utf-8", errors="replace")
    assert "analisisVigente" in pantalla
    assert "r.vigencia" in pantalla


def test_la_portada_sella_de_que_subida_son_los_cuadros():
    """Quien abre el archivo tiene que ver de qué dato habla ANTES de leer la
    primera conclusión."""
    from app.informes import secciones

    fuente = inspect.getsource(secciones.portada)
    assert "Cuadros tomados de:" in fuente
    assert "EL ANALISIS ESCRITO NO CORRESPONDE" in fuente
    assert "ROJO" in fuente


def test_el_analisis_de_setiembre_2026_declara_contra_que_subida_se_escribio():
    """El mes que disparó todo esto. Reescrito el 2026-10-15 contra la subida
    del 16-oct; si alguien sube setiembre otra vez, el informe lo va a decir."""
    import json
    import pathlib

    ruta = (pathlib.Path(__file__).resolve().parents[1] / "app" / "seed_data"
            / "CWL" / "informes" / "2026_09.json")
    nar = json.loads(ruta.read_text(encoding="utf-8"))
    c = nar.get("_contra") or {}
    assert len(c.get("checksum", "")) == 64, "la huella es el sha256 del archivo"
    assert c.get("archivo") and c.get("fecha")

    # Y que no haya quedado ni una cifra de la version anterior: el texto se
    # reescribio entero, no se parchó.
    txt = json.dumps(nar, ensure_ascii=False)
    for vieja in ("42.203,4", "181.681,69", "258.366,44", "300.569,90",
                  "45.178,54", "20.100,28"):
        assert vieja not in txt, f"sobrevivio una cifra del analisis viejo: {vieja}"
