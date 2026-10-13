# -*- coding: utf-8 -*-
"""Una fracción × 100 no se le muestra cruda a nadie.

Owner, 2026-10-13, con la grilla de canales abierta: *«corrige esto»*, y las
celdas que circuló eran exactamente éstas:

    B2B — agency/DMC/TO      Jul 55.0000   Ago 55.0000
    Direct — website         Nov 28.0000
    Costa Rica Collection    Oct  7.0000
    Direct groups            Abr  7.0000   May 7.0000   Jun 7.0000
    OTA                      Abr  7.0000   May 7.0000

mientras las de al lado decían `60`, `26`, `5`, `31`, `43`, `35` sin cola.

## No era el guardado: era `fraccion * 100` en punto flotante

Las que se ven mal son **exactamente** las que no tienen representación binaria
exacta, y eso explica el patrón celda por celda:

    0.55 * 100 = 55.00000000000001        0.60 * 100 = 60.0   limpio
    0.28 * 100 = 28.000000000000004       0.26 * 100 = 26.0   limpio
    0.07 * 100 =  7.000000000000001       0.05 * 100 =  5.0   limpio

El número guardado estaba bien; lo que se desbordaba era la casilla.

## Por qué cuatro decimales y no menos

La fracción se guarda como `Numeric(8, 6)` —seis decimales— así que el
porcentaje tiene como máximo cuatro. Con menos se perdería una comisión real
como 26,8300%; con más vuelve la cola.

⚠️ El frontend no tiene corredor de pruebas y no se monta uno por esto. Python
tiene la MISMA aritmética IEEE 754, así que acá se prueba la lógica de verdad
—no solo que el texto esté en el archivo— y aparte se verifica que las tres
pantallas que mandaban el resultado a una casilla usen el ayudante.
"""
import pathlib
import re

FRONT = pathlib.Path(__file__).resolve().parents[2] / "frontend"

#: Las celdas que el owner circuló, con la fracción que las produce.
LAS_QUE_SE_VEIAN_MAL = ("0.55", "0.28", "0.07")
#: Las de al lado, que se veían bien. Están acá para que la prueba demuestre
#: que el patrón era el del float y no «algunas celdas al azar».
LAS_QUE_SE_VEIAN_BIEN = ("0.60", "0.26", "0.05", "0.04", "0.31", "0.43", "0.35")


def pct_de_fraccion(v) -> float:
    """La misma cuenta que `pctDeFraccion` en `frontend/lib/fmt.ts`."""
    return round(float(v) * 1e6) / 1e4


def test_el_defecto_existia_y_era_el_float():
    """Las circuladas dejan cola al multiplicar por 100; las de al lado no."""
    for s in LAS_QUE_SE_VEIAN_MAL:
        crudo = float(s) * 100
        assert crudo != round(crudo), f"{s} deberia dejar cola y no la deja"
        assert len(repr(crudo)) > 4, (s, repr(crudo))
    for s in LAS_QUE_SE_VEIAN_BIEN:
        crudo = float(s) * 100
        assert crudo == round(crudo), f"{s} no deberia dejar cola: {crudo!r}"


def test_el_ayudante_lo_arregla_sin_perder_un_valor_real():
    for s in LAS_QUE_SE_VEIAN_MAL + LAS_QUE_SE_VEIAN_BIEN:
        v = pct_de_fraccion(s)
        assert v == round(v), (s, v)
    # Y no redondea de mas: estos son porcentajes que el hotel usa de verdad.
    assert pct_de_fraccion("0.2683") == 26.83      # CCSS patronal
    assert pct_de_fraccion("0.178") == 17.8        # comision neta ponderada
    assert pct_de_fraccion("0.30") == 30.0         # impuesto de renta
    # El limite de lo que cabe en `Numeric(8, 6)`: no se puede perder.
    assert pct_de_fraccion("0.000001") == 0.0001


def test_las_pantallas_que_llenan_una_CASILLA_usan_el_ayudante():
    """⚠️ Lo que importa no es el formato: es que el valor va a una casilla.

    Un `* 100` seguido de `.toFixed(1)` es inofensivo —la cola no se ve—. El
    daño aparece cuando el resultado es el `value` de un input, porque ahí se
    muestra crudo. Eran tres sitios y los tres salen de la misma cuenta.
    """
    assert "export function pctDeFraccion" in (
        FRONT / "lib" / "fmt.ts").read_text(encoding="utf-8", errors="replace")

    for rel in ("components/GrillaMixDoce.tsx",
                "app/month-end/pl/DoceMeses.tsx",
                "app/nonop/management-fees/page.tsx"):
        txt = (FRONT / rel).read_text(encoding="utf-8", errors="replace")
        assert "pctDeFraccion" in txt, rel
        # Y que no haya quedado uno crudo suelto en la misma pantalla.
        crudos = [L.strip() for L in txt.splitlines()
                  if re.search(r"\?\?\s*0\)\s*\*\s*100|parseFloat\([^)]*\)\s*\*\s*100", L)
                  and "toFixed" not in L]
        assert not crudos, f"{rel} todavia multiplica crudo: {crudos}"
