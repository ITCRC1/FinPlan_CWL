"""Lo que el recálculo HACE no es un aviso.

Owner, 2026-11-24, señalando el texto amarillo junto al botón Recalcular:
*«esto volvió a salir»*. Era «1 líneas en colones se reexpresaron» y «Riesgos del
trabajo (INS) repartido por FTE»: el recálculo haciendo su trabajo, con el mismo
⚠ que «no hay tipo de cambio». Ahora esos mensajes son `Nota` y viajan en
`notas`; en `avisos` queda solo lo que hay que mirar.
"""
import inspect

from app.engine import recalculate
from app.engine.recalculate import Nota, separar_notas


def test_separar_notas():
    avisos, notas = separar_notas(["sin TC", Nota("INS repartido"), Nota("colones")])
    assert avisos == ["sin TC"]
    assert notas == ["INS repartido", "colones"]


def test_los_mensajes_informativos_son_notas():
    src = inspect.getsource(recalculate)
    for texto in ("están en colones: se", "repartido por {cfg.basis}",
                  "meses con FTE 0 quedaron en cero", "Ingreso sincronizado",
                  "Noches sincronizadas", "Tarifas del paquete bajadas"):
        i = src.index(texto)
        antes = src[max(0, i - 120):i]
        assert "Nota(" in antes, f"«{texto}» volvió a ser un aviso"


def test_los_avisos_de_verdad_siguen_siendo_avisos():
    src = inspect.getsource(recalculate)
    for texto in ("La planilla NO se recalculó", "no cerró en $0 después de repartir",
                  "se dejaron como estaban: traen números"):
        i = src.index(texto)
        antes = src[max(0, i - 120):i]
        assert "Nota(" not in antes, f"«{texto}» quedó escondido como nota"


def test_las_dos_ramas_devuelven_notas():
    src = inspect.getsource(recalculate.recalculate_scenario)
    assert src.count('"notas"') >= 2
