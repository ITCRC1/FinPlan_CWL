# -*- coding: utf-8 -*-
"""El rótulo en español del Cash Flow Budget -> su clave de traducción.

⚠️ **El motor no traduce: nombra.** Igual que `etiquetas_cashflow.py` (el flujo
DIRECTO): la fila sigue viajando con su `label` —el texto de siempre, que es el
respaldo— y además con `label_key` cuando es una etiqueta fija de la pantalla.
La pantalla prefiere el catálogo (`cfbFila`) y cae al `label` si no hay clave.

`app/engine/` no puede enterarse del idioma —regla del proyecto, vigilada por
`tests/test_i18n_locale.py`—, así que acá no hay texto en inglés: hay claves.

⚠️ **Solo están los rótulos que hoy salen EN ESPAÑOL.** El resto del cuadro
—`Revenue`, `Deposits Received`, `Beginning Cash`…— ya viaja en inglés y en
inglés se ve en las dos pantallas; meterlos acá cambiaría lo que ve el usuario
en español, y esto es una traducción, no un rediseño.

⚠️ **Los rótulos que vienen de la BASE no están acá a propósito** —los nombres
de línea del balance ancla, de departamento, de escenario—. Eso es DATO, no
interfaz: al no encontrarse en este mapa salen sin `label_key` y la pantalla usa
el nombre tal cual llega.
"""

#: rótulo fijo (tal como lo emite el motor) -> clave dentro de `cfbFila`
ETIQUETAS: dict[str, str] = {
    # Filas del cuadro (WC_ROWS / OTHER_ROWS / ajuste a caja real)
    "Servicio F&B por pagar (10% empleados)": "servicio_fb_por_pagar",
    "Impuesto de renta (liquidación anual)": "impuesto_de_renta_liquidacion_anual",
    "Ajuste manual": "ajuste_manual",
    "Ajuste a caja real (meses cerrados)": "ajuste_a_caja_real_meses_cerrados",
    # Partidas del Balance Sheet proyectado (`project_balance_sheet`)
    "Depósitos de huéspedes": "depositos_de_huespedes",
    "Cuentas por cobrar (A/R)": "cuentas_por_cobrar_ar",
    "Cuentas por pagar (A/P)": "cuentas_por_pagar_ap",
    "Provisión aguinaldo": "provision_aguinaldo",
    "IVA por pagar / crédito": "iva_por_pagar_credito",
    "Crédito de Renta (retención tarjeta)": "credito_de_renta_retencion_tarjeta",
}


def clave(label: str) -> str | None:
    """La clave de un rótulo, o None si no es una etiqueta fija de la pantalla."""
    return ETIQUETAS.get((label or "").strip())
