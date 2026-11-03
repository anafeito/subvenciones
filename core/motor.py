"""Orquestación: perfil -> convocatorias abiertas -> elegibilidad -> encaje -> ranking."""
from __future__ import annotations

from datetime import date
from typing import Optional

from .bdns import abierta
from .elegibilidad import evaluar
from .encaje import Indice, calcular, texto_perfil
from .models import Convocatoria, Estado, Perfil, Resultado


def importe_estimado(perfil: Perfil, conv: Convocatoria) -> Optional[float]:
    """Solo si las bases dan importe por beneficiario o intensidad; la BDNS no lo publica en la ficha."""
    if perfil.inversion_prevista and conv.intensidad:
        v = perfil.inversion_prevista * conv.intensidad / 100
        return min(v, conv.importe_max) if conv.importe_max else v
    return conv.importe_max


def analizar(perfil: Perfil, convs: list[Convocatoria], indice: Optional[Indice] = None,
             historial: Optional[list[dict]] = None, hoy: Optional[date] = None) -> list[Resultado]:
    hoy = hoy or date.today()
    historial = historial or []
    abiertas = [c for c in convs if abierta(c, hoy) and (not c.fecha_inicio or c.fecha_inicio <= hoy)]
    sims = indice.similitudes(texto_perfil(perfil)) if indice else None
    res = []
    for c in abiertas:
        evals = evaluar(perfil, c.requisitos, hoy)
        sim = float(sims[indice.pos[c.id]]) if sims is not None and c.id in indice.pos else None
        enc = calcular(perfil, c, evals, sim, historial)
        elegible = not any(e.estado == Estado.no_cumple for e in evals)
        faltan = sum(e.estado == Estado.falta_dato for e in evals)
        dias = (c.fecha_fin - hoy).days if c.fecha_fin else None
        urg = 0.05 if dias is not None and dias <= 15 else 0.0
        res.append(Resultado(convocatoria=c, evaluaciones=evals, elegible=elegible, faltan_datos=faltan,
                             encaje=enc, dias_restantes=dias,
                             puntuacion=round(enc.puntuacion + urg if elegible else -1, 4)))
    return sorted(res, key=lambda r: r.puntuacion, reverse=True)
