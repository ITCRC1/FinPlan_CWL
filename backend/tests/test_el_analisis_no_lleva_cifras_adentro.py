# -*- coding: utf-8 -*-
"""El análisis escrito no puede tener números adentro.

Owner, 2026-10-17, después de que el informe de setiembre quedara vencido por
tercera vez en dos días: *«seguiré moviendo setiembre..pero hay que hacer lo
necesario para que esto funcione»*.

## Por qué no alcanzaba con avisar

El aviso de vigencia —construido el 15-oct— impide que el documento mienta,
pero convierte cada subida en una tarea: reescribir 24 secciones a mano. Y
setiembre 2026 se subió **cuatro veces en doce días**. Entre el archivo del
16-oct y el del 17-oct el gasto se movió US$9.799,86 **sin que cambiara un
centavo de ingreso** —pura reclasificación— y Ventas y Mercadeo pasó de estar
por debajo del presupuesto a ser el mayor exceso de overhead.

Una tarea que se repite así termina olvidándose. Y el día que se olvide, el
documento sale completo, cuadrado y mintiendo.

## Qué cambió

El texto lleva marcas `{{...}}` en vez de cifras, y se resuelven contra el
corte al armar el documento. **La misma frase es verdadera con cualquier
archivo cargado.** De 427 cifras escritas a mano quedaron 6, y son históricas
—hablan de lo que pasó entre dos archivos— declaradas en `_contra.cifras_fijas`.

Lo que sigue escrito a mano es el JUICIO: qué hallazgo va primero, si una
favorabilidad es ahorro o diferimiento, a qué gerente se le pregunta. Eso no se
recalcula, y por eso el aviso sobrevive — pero ahora dice «revisá el juicio» en
vez de «reescribilo entero».
"""
import json
import pathlib

import pytest

from app.informes import armador
from app.informes.datos import Datos
from app.informes.plantilla import MARCA, resolver, valor

SCR = pathlib.Path(__file__).resolve().parents[1]


class _D:
    """Un corte mínimo. `plantilla` solo llama a estos métodos."""
    anio, mes = 2026, 9

    def __init__(self, ingreso, gasto):
        self._i, self._g = ingreso, gasto
        self.d = {"stats": {"ACT": [{"nights_available": 900,
                                     "nights_occupied": 35,
                                     "revenue": 18693.28, "pax": 68}]}}

    def total(self, esc, clase):
        if clase == "revenue":
            return self._i if esc == "ACT" else 86101.21
        return (self._g / 3) if esc == "ACT" else 83704.66

    def gop(self, esc):
        return self.total(esc, "revenue") - sum(
            self.total(esc, c) for c in ("cost", "payroll", "opex"))


def test_la_misma_frase_da_la_cifra_de_CADA_archivo():
    """⚠️ El corazón del arreglo, y la razón de que exista.

    Entre dos subidas del mismo mes el gasto se movió US$9.799,86. Con la cifra
    escrita adentro, el texto quedaba falso; con la marca, la frase es correcta
    en los dos casos sin tocar una letra.
    """
    frase = ("El gasto operativo fue de {{tot ACT gasto}} y el GOP "
             "{{gop ACT}}.")
    viejo = resolver(frase, _D(40178.28, 322266.71))
    nuevo = resolver(frase, _D(40178.28, 332066.57))
    assert "$322.266,71" in viejo and "-$282.088,43" in viejo
    assert "$332.066,57" in nuevo and "-$291.888,29" in nuevo
    assert viejo != nuevo        # la MISMA frase, dos resultados


def test_una_marca_que_no_resuelve_se_VE():
    """⚠️ Nunca un cero silencioso.

    Un cero se lee como «no hubo movimiento», y en un informe de variaciones
    eso es una conclusión, no un hueco. Así se descubrieron dos defectos el
    día que se escribió esto: diez marcas de clase 8 y un «Alimentas y Bebidas»
    mal escrito salieron marcados en vez de salir en cero.
    """
    faltan = []
    out = resolver("Vale {{tot ACT inventado}} pesos.", _D(1, 1), faltan)
    assert "⟦?" in out and "0" not in out.replace("⟦? tot ACT inventado⟧", "")
    assert faltan and "inventado" in faltan[0]


def test_una_cuenta_sin_movimiento_NO_vale_cero():
    """Que una cuenta no esté no es lo mismo que que valga cero: una cuenta mal
    escrita daría «$0,00» y se leería como «no hubo gasto»."""
    class SinCuentas(_D):
        def por_cuenta(self, clase, periodo="mes"):
            return {}

    with pytest.raises(KeyError):
        valor("cta 0110 9999 ACT", SinCuentas(1, 1))


def test_NO_hay_eval():
    """⚠️ Una plantilla es un dato del hotel y se edita como texto. Si pudiera
    ejecutar código, editar el análisis sería ejecutar código en el servidor."""
    fuente = (SCR / "app" / "informes" / "plantilla.py").read_text(
        encoding="utf-8", errors="replace")
    import re as _re
    # ⚠️ Los builtins SUELTOS. `re.compile` es otra cosa y esta bien.
    for prohibido in ("eval", "exec", "__import__", "compile"):
        suelto = _re.search(rf"(?<![.\w]){prohibido}\s*\(", fuente)
        assert suelto is None, f"{prohibido}: {suelto.group(0)}"


def test_las_marcas_se_resuelven_ANTES_de_las_secciones():
    """Sobre la narrativa entera y de una sola vez: así vale para párrafos,
    viñetas, celdas de cuadro y preguntas sin tocar las doce funciones que
    arman el documento — y sin que mañana alguien agregue una sección que se
    olvide de resolver."""
    fuente = __import__("inspect").getsource(armador.armar)
    assert "nar = resolver(nar, D, sin_resolver)" in fuente
    # Y lo que no resolvió se cuenta como faltante, igual que una sección que falta.
    assert "S1.FALTANTES.extend" in fuente


# ── El análisis de setiembre 2026, convertido ──────────────────────────────

def _narrativa():
    return json.loads(
        (SCR / "app" / "seed_data" / "CWL" / "informes" / "2026_09.json")
        .read_text(encoding="utf-8"))


def test_setiembre_2026_ya_no_tiene_cifras_sueltas():
    """Eran 427. Quedan las declaradas en `_contra.cifras_fijas`, que son
    históricas: hablan de lo que pasó entre dos archivos del mes."""
    nar = _narrativa()
    declaradas = int(nar["_contra"].get("cifras_fijas") or 0)
    assert declaradas <= 10, "demasiadas cifras fijas: ¿son todas historicas?"
    assert armador._cifras_a_mano(nar) <= declaradas


def test_setiembre_2026_usa_marcas_de_verdad():
    """Que no haya cifras no basta: el texto tiene que traer los números por
    marca, o sería un análisis sin números."""
    txt = json.dumps(_narrativa(), ensure_ascii=False)
    assert len(MARCA.findall(txt)) > 150


def test_el_aviso_distingue_la_cifra_del_JUICIO():
    """⚠️ Con las marcas, una subida nueva ya no vuelve falso el texto. Lo que
    SÍ puede envejecer es el juicio: «Ventas y Mercadeo ahorró 4,1%» pasó a
    «gastó 45% de más» entre dos archivos del mismo mes, y eso ningún mecanismo
    lo puede recalcular.

    Seguir gritando «vencido» por algo que ya se arregló solo convierte el
    aviso en ruido — y un aviso que suena siempre deja de leerse.
    """
    fuente = __import__("inspect").getsource(armador.vigencia)
    assert '"revisar_juicio"' in fuente
    assert "cifras_fijas" in fuente
    # El estado blando NO bloquea: las cifras están bien.
    assert '"estado": "revisar_juicio", "vigente": True' in fuente
