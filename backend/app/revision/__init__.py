# -*- coding: utf-8 -*-
"""La revisión integral de los actuales, antes de declararlos finales.

## Por qué existe

Hasta hoy la revisión del cierre pasaba por el ojo de una persona sobre un Excel
de 104 MB. Por ahí podía entrar cualquier cosa —una cuenta que USALI no
contempla, un departamento nuevo, un gasto que nadie presupuestó—: si nadie lo
miraba, entraba igual y el P&L cuadraba consigo mismo.

Owner (2026-08-31): *«es un reporte de varianzas pero también de discrepancias,
ya que cualquier cosa puede subir y el sistema no puede ignorarlos. Quizás no
rechazar la subida pero sí indicar los hallazgos.»*

## La regla: avisa, no rechaza

**Ningún hallazgo frena una carga.** Los únicos que bloquean son los cuatro
controles que ya bloqueaban —ingresos, GOP, EBITDA y utilidad neta—, y de eso se
encarga `importers/verificacion.py`, no este paquete.

Rechazar por un hallazgo tendría el efecto contrario al buscado: la gente
aprendería a esquivarlo. Lo que se pide es que **no se calle nada**.

## Cada hallazgo lleva su monto

Sin el monto no hay forma de saber si es ruido o si falta media operación, y una
lista que no distingue las dos cosas se aprende a ignorar. Es la misma razón por
la que el importador de Channel Mix reporta los market codes sin canal **con sus
noches**.

## Cinco niveles

    0  el archivo se puede creer      (se lee, trae el mes, tiene el TC)
    1  estructura                     ¿esta cuenta va a algún lado?
    2  coherencia interna             ¿el archivo se contradice a sí mismo?
    3  contra las otras fuentes       ¿el mayor amarra con los auxiliares?
    4  contra lo que se esperaba      ¿cuánto se desvió del Forecast y el Budget?

Los niveles 0 a 2 salen del archivo y del catálogo. El 3 y el 4 necesitan el
resto del sistema.
"""
from app.revision.hallazgo import GRAVEDADES, Hallazgo, hallazgo
from app.revision.nivel1_estructura import revisar as revisar_estructura
from app.revision.nivel2_coherencia import revisar as revisar_coherencia
from app.revision.nivel3_fuentes import revisar as revisar_fuentes
from app.revision.nivel4_expectativa import revisar as revisar_expectativa

__all__ = ["Hallazgo", "hallazgo", "GRAVEDADES", "revisar_estructura",
           "revisar_coherencia", "revisar_fuentes", "revisar_expectativa"]
