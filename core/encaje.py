"""Encaje empresa-convocatoria.

No hay datos públicos de solicitudes denegadas, así que no se puede entrenar una "probabilidad de
concesión" honesta. En su lugar se calcula un ENCAJE explicable (0-1) con:
  - similitud de texto (TF-IDF) entre el proyecto/actividad de la empresa y la convocatoria,
  - proporción de requisitos verificados como cumplidos,
  - señales del historial real de la empresa en la BDNS (ya recibió ayudas de ese órgano),
  - tipo de procedimiento (no competitivo = por orden de llegada).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from . import cnae
from .models import Convocatoria, Encaje, Estado, Evaluacion, Perfil

STOP = ("de la el en y a los las del se por para con un una al o que su sus es lo como mas más este esta "
        "bases reguladoras convocatoria convocatorias subvencion subvenciones subvención ayuda ayudas año "
        "ejercicio aprueba aprobación extracto resolución orden decreto destinadas destinados regimen régimen "
        "concurrencia competitiva publica pública publicas públicas programa linea línea 2024 2025 2026 2027").split()


def _sin_acentos(t: str) -> str:
    return unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode().lower()


_STOP = {_sin_acentos(w) for w in STOP}


def analizador(texto: str) -> list[str]:
    """Tokens con 'stemming' ligero (prefijo de 6 letras): digitalizar ~ digitalización ~ digitales."""
    toks = [w[:6] for w in re.findall(r"[a-z0-9+]{3,}", _sin_acentos(texto)) if w not in _STOP]
    return toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]


class Indice:
    def __init__(self, convs: list[Convocatoria]):
        self.ids = [c.id for c in convs]
        self.pos = {cid: i for i, cid in enumerate(self.ids)}
        self.vec = TfidfVectorizer(analyzer=analizador, min_df=1,
                                   max_df=0.5 if len(convs) >= 20 else 1.0, sublinear_tf=True)
        textos = [c.texto_busqueda() for c in convs] or ["vacio"]
        self.mat = self.vec.fit_transform(textos)

    def similitudes(self, texto: str):
        if not texto.strip() or not self.ids:
            return None
        return cosine_similarity(self.vec.transform([texto]), self.mat)[0]


def texto_perfil(p: Perfil) -> str:
    return " ".join(x for x in (p.proyecto, cnae.descripcion(p.cnae), p.proyecto) if x)


def calcular(perfil: Perfil, conv: Convocatoria, evals: list[Evaluacion], sim: Optional[float],
             historial: list[dict]) -> Encaje:
    factores: list[str] = []
    evaluables = [e for e in evals if e.estado in (Estado.cumple, Estado.no_cumple, Estado.falta_dato)]
    ratio = sum(e.estado == Estado.cumple for e in evaluables) / max(1, len(evaluables))
    s = 0.35 if sim is None else min(1.0, sim / 0.22)
    if sim is not None:
        factores.append("el proyecto encaja con el objeto de la ayuda" if s >= 0.6 else
                        "encaje parcial con el objeto de la ayuda" if s >= 0.3 else
                        "el objeto de la ayuda se parece poco al proyecto")
    else:
        factores.append("describe el proyecto para afinar el encaje")
    extra = 0.0
    org3 = (conv.organo or "").split(" · ")[-1].upper()
    if org3 and any((h.get("nivel3") or "").upper() == org3 for h in historial):
        extra += 0.5
        factores.append("la empresa ya ha recibido ayudas de este organismo")
    if conv.concurrencia_competitiva is False:
        extra += 0.5
        factores.append("no competitiva: se concede por orden de llegada, conviene darse prisa")
    elif conv.concurrencia_competitiva:
        factores.append("concurrencia competitiva: cuenta la calidad de la memoria")
    faltan = sum(e.estado == Estado.falta_dato for e in evals)
    if faltan:
        factores.append(f"{faltan} dato(s) del perfil por completar")
    punt = round(0.6 * s + 0.25 * ratio + 0.15 * min(1.0, extra), 3)
    banda = "alta" if punt >= 0.55 else "media" if punt >= 0.35 else "baja"
    return Encaje(puntuacion=punt, banda=banda, factores=factores)
