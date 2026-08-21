# -*- coding: utf-8 -*-
"""Guillermo — ingesta autónoma de reportes. Ver `docs/GUILLERMO.md`.

`core` es puro: sin I/O de red ni de disco, para que el mismo código corra en
el cron de Railway y en un agente local. Lo que toca el mundo va aparte.
"""
