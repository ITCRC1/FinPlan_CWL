# -*- coding: utf-8 -*-
"""De dónde salen los archivos (`docs/GUILLERMO.md` §5).

**Acá vive el I/O; el núcleo no lo conoce.** Cambiar de fuente —de una carpeta
local a un buzón de correo, a SFTP o a la API de Opera— no toca `core.py`. Ese
es todo el punto del contrato.

⚠️ **Ninguna fuente está conectada todavía**, y no es un olvido: cuál se usa
depende de decisiones del owner que siguen abiertas (D-2 formato, D-4 si OHIP
está en la licencia). `FolderSource` existe porque es la única que no necesita
nada de nadie, y sirve de puente.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass
class ArchivoTraido:
    nombre: str
    contenido: bytes
    origen: str


@dataclass
class Periodo:
    desde: date
    hasta: date


class ReportSource(Protocol):
    """El contrato del §5. Una fuente sólo sabe traer archivos."""

    def fetch(self, periodo: Periodo) -> list[ArchivoTraido]:
        ...


class FolderSource:
    """Una carpeta del disco. El puente de la Fase 1 (camino C del §5)."""

    def __init__(self, carpeta: str, patrones: list[str] | None = None,
                 estabilidad_seg: int = 30):
        self.carpeta = carpeta
        self.patrones = patrones or ["*"]
        # ⚠️ **Nunca leer al primer evento.** Con una carpeta sincronizada
        # (OneDrive) o SFTP, el archivo puede estar a medio escribir cuando se
        # detecta: entra truncado, parsea igual y da totales más chicos sin que
        # nada falle. Se espera a que el tamaño deje de moverse.
        self.estabilidad_seg = estabilidad_seg

    def _estable(self, ruta: str) -> bool:
        try:
            t = os.path.getmtime(ruta)
        except OSError:
            return False
        return (time.time() - t) >= self.estabilidad_seg

    def fetch(self, periodo: Periodo) -> list[ArchivoTraido]:
        import fnmatch

        if not os.path.isdir(self.carpeta):
            return []
        fuera: list[ArchivoTraido] = []
        for nombre in sorted(os.listdir(self.carpeta)):
            if not any(fnmatch.fnmatch(nombre, p) for p in self.patrones):
                continue
            ruta = os.path.join(self.carpeta, nombre)
            if not os.path.isfile(ruta) or not self._estable(ruta):
                continue
            try:
                with open(ruta, "rb") as fh:
                    fuera.append(ArchivoTraido(nombre, fh.read(), "folder"))
            except OSError:
                # Un archivo que no se puede leer NO se saltea en silencio: se
                # omite acá y la validación de nivel 1 lo va a reportar como
                # ausente, que es la verdad desde el punto de vista del batch.
                continue
        return fuera


class MailSource:
    """Buzón dedicado (camino B). **Sin implementar**: depende de que Opera
    tenga configurado el Scheduled Report, que es decisión del owner."""

    def fetch(self, periodo: Periodo) -> list[ArchivoTraido]:
        raise NotImplementedError(
            "MailSource no está conectado: falta configurar el Scheduled Report "
            "en Opera (D-1/D-2)")


class OhipSource:
    """Opera Cloud API (camino A). **Sin implementar**: depende de D-4, si OHIP
    está habilitado en la licencia. El spec avisa de no darlo por hecho."""

    def fetch(self, periodo: Periodo) -> list[ArchivoTraido]:
        raise NotImplementedError(
            "OhipSource no está conectado: falta confirmar con el partner de "
            "Oracle si OHIP está en la licencia (D-4)")
