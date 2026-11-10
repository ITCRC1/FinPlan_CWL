# -*- coding: utf-8 -*-
"""Ninguna pestaña de la barra queda escondida, a ningún ancho.

Owner, 2026-11-10: *«por qué Master Data se me esconde a veces»* · *«también
podés hacer que se desplieguen acá para abajo, y así no se esconde»*.

La fila de pestañas scrolleaba de lado con la barra oculta: la que no entraba
quedaba cortada en el borde y parecía no existir (en español los rótulos son más
largos, así que pasaba más). Ahora:

* Master Data y Admin van fijos a la derecha (`FIJOS_A_LA_DERECHA`).
* Las que no entran se miden y pasan a un menú «Más ▾» que se despliega hacia
  abajo, con el nombre de cada pestaña como encabezado.

Verificado en el navegador: a 2600 px no aparece «Más»; a 1920 px lleva
Break-Even y Cost; a 1000 px lleva siete.
"""
import io
import json
import os

RAIZ = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")


def _nav() -> str:
    return io.open(os.path.join(RAIZ, "components", "TopNav.tsx"), encoding="utf-8").read()


def test_master_data_va_fijo_a_la_derecha():
    assert 'const FIJOS_A_LA_DERECHA = ["masterData", "admin"]' in _nav()


def test_lo_que_no_entra_se_mide_y_va_a_mas():
    src = _nav()
    assert 'querySelectorAll<HTMLElement>("[data-nav-tab]")' in src
    assert "new ResizeObserver(medir)" in src
    assert 'return { key: "mas", items }' in src
    assert 'oculto={ocultos.includes(group.key)}' in src


def test_la_fila_ya_no_scrollea_de_lado():
    """Si la fila volviera a scrollear, una pestaña podría quedar a medio cortar
    además de estar en «Más»: dos lugares, uno de ellos invisible."""
    assert 'className="nav-scroll" ref={filaRef} style={{ overflowX: "hidden" }}' in _nav()


def test_los_links_directos_tambien_se_miden():
    """Pre-Closing y Dashboard son links, no menús: sin el atributo no se
    medirían y podrían quedar cortados sin pasar a «Más»."""
    src = _nav()
    assert '<Link href={group.href} className="nav-nowrap" title={largo} data-nav-tab={group.key}' in src


def test_mas_tiene_su_rotulo_en_los_dos_idiomas():
    for f, esperado in (("es.json", "Más"), ("en.json", "More")):
        d = json.load(io.open(os.path.join(RAIZ, "messages", f), encoding="utf-8"))
        assert d["nav"]["groups"]["mas"] == esperado
