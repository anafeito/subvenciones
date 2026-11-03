"""Lectura de las bases reguladoras y extracción de requisitos (RAG ligero).

1. Descarga el texto: anuncio publicado en el diario oficial (viene en la ficha BDNS) y
   la URL de las bases (HTML o PDF).
2. Extrae requisitos estructurados, importe máximo, intensidad, criterios de valoración y
   documentación:
     - con un LLM gratuito si está configurado (Groq, Gemini, Ollama), citando el artículo;
     - si no, con heurísticas (expresiones regulares) sobre el texto.
"""
from __future__ import annotations

import io
import json
import re
from html import unescape
from typing import Optional

import httpx

from . import llm
from .models import Convocatoria, Requisito
from .territorio import COMUNIDADES

MAX_TEXTO = 45000


def _html_a_texto(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</tr>", "\n", html)
    texto = unescape(re.sub(r"<[^>]+>", " ", html))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", texto)).strip()


def descargar(url: str, timeout: float = 25) -> str:
    r = httpx.get(url, timeout=timeout, follow_redirects=True,
                  headers={"User-Agent": "Mozilla/5.0 (copiloto-subvenciones)"})
    r.raise_for_status()
    tipo = r.headers.get("content-type", "").lower()
    if "pdf" in tipo or r.content[:4] == b"%PDF":
        from pypdf import PdfReader
        lector = PdfReader(io.BytesIO(r.content))
        return "\n".join((pg.extract_text() or "") for pg in lector.pages[:40])
    return _html_a_texto(r.text)


def texto_bases(conv: Convocatoria) -> tuple[str, list[str]]:
    """Devuelve (texto, fuentes usadas)."""
    partes, fuentes = [], []
    for a in conv.anuncios:
        if a.get("texto"):
            partes.append(_html_a_texto(a["texto"]))
            fuentes.append(f"Anuncio {a.get('desDiarioOficial') or ''} {a.get('datPublicacion') or ''}".strip())
    if conv.url_bases:
        try:
            partes.append(descargar(conv.url_bases))
            fuentes.append(conv.url_bases)
        except Exception:
            pass
    return "\n\n".join(partes)[:MAX_TEXTO], fuentes


# --------------------------------------------------------------------------- heurísticas

def _num(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def extraer_heuristico(texto: str, cita: str = "Bases") -> dict:
    t = texto.lower()
    reqs: list[Requisito] = []

    def add(id_, txt, campo, op, valor):
        reqs.append(Requisito(id=id_, texto=txt, campo=campo, op=op, valor=valor, cita=cita))

    m = re.search(r"(?:menos de|inferior a|hasta un m[aá]ximo de)\s+(\d{1,4})\s+(?:personas\s+)?(?:trabajador|emplead)", t)
    if m:
        add("plantilla_max", f"Plantilla inferior a {m.group(1)} personas", "empleados", "<", int(m.group(1)))
    m = re.search(r"(?:al menos|m[ií]nimo de)\s+(\d{1,4})\s+(?:personas\s+)?(?:trabajador|emplead)", t)
    if m:
        add("plantilla_min", f"Plantilla de al menos {m.group(1)} personas", "empleados", ">=", int(m.group(1)))
    m = re.search(r"antig[üu]edad\s+(?:m[ií]nima\s+)?de\s+(?:al menos\s+)?(\d+)\s+a[ñn]os?", t)
    if m:
        add("antiguedad", f"Antigüedad mínima de {m.group(1)} años", "antiguedad_anios", ">=", float(m.group(1)))
    if re.search(r"\bmicroempresas?\b", t) and not re.search(r"\bpymes?\b|peque[ñn]as y medianas", t):
        add("micro", "Ser microempresa", "tamano", "==", "micro")

    out: dict = {"requisitos": reqs}
    m = re.search(r"(?:cuant[ií]a|importe)\s+m[aá]xim[oa][^.]{0,80}?(\d{1,3}(?:\.\d{3})+|\d{4,7})(?:,\d+)?\s*(?:euros|€)", t)
    if m:
        out["importe_max"] = _num(m.group(1))
    m = re.search(r"(\d{1,3})\s*(?:%|por ciento)\s+(?:del?|de los)\s+(?:coste|gasto|presupuesto|inversi)", t)
    if m and 0 < int(m.group(1)) <= 100:
        out["intensidad"] = float(m.group(1))
    crit = re.findall(r"\n\s*(?:[a-h]\)|\d\.)\s*([^\n]{15,140}?)\s*[:(]\s*(?:hasta\s+)?(\d{1,3})\s*puntos", texto, re.I)
    if crit:
        out["criterios_valoracion"] = [f"{c.strip()} (hasta {p} puntos)" for c, p in crit[:10]]
    return out


# --------------------------------------------------------------------------- LLM

PROMPT = """Eres experto en subvenciones españolas. A partir del texto de unas bases/convocatoria, devuelve SOLO
un JSON con esta forma (sin comentarios):
{{"importe_max": número o null (euros por beneficiario),
  "intensidad": número o null (porcentaje subvencionable),
  "requisitos": [{{"id": "corto", "texto": "requisito en una frase", "campo": CAMPO, "op": OP, "valor": ..., "cita": "Art. X"}}],
  "criterios_valoracion": ["criterio (hasta N puntos)", ...],
  "documentos": ["documento a aportar", ...]}}
CAMPO es uno de: tamano (valores micro|pequena|mediana|grande), empleados, facturacion, antiguedad_anios,
cnae (lista de códigos), inversion_prevista, minimis_recibido_3_anios, al_corriente_hacienda, al_corriente_ss.
OP es uno de: "<", "<=", ">", ">=", "==", "prefix_in", "true", "cualitativo".
Si un requisito no encaja en esos campos, usa op "cualitativo" (campo libre). No inventes: usa solo el texto.
Incluye la cita (artículo o apartado) de cada requisito.

TEXTO:
{texto}"""


def extraer_llm(texto: str) -> Optional[dict]:
    salida = llm.completar(PROMPT.format(texto=texto[:24000]), max_tokens=2500, temperatura=0.0)
    if not salida:
        return None
    try:
        ini, fin = salida.find("{"), salida.rfind("}") + 1
        datos = json.loads(salida[ini:fin])
        reqs = []
        for i, r in enumerate(datos.get("requisitos") or []):
            try:
                reqs.append(Requisito(id=str(r.get("id") or f"r{i}"), texto=str(r.get("texto", "")),
                                      campo=str(r.get("campo") or "otro"), op=str(r.get("op") or "cualitativo"),
                                      valor=r.get("valor"), cita=r.get("cita")))
            except Exception:
                continue
        datos["requisitos"] = reqs
        return datos
    except Exception:
        return None


def enriquecer(conv: Convocatoria) -> tuple[Convocatoria, dict]:
    """Lee las bases y añade a la convocatoria lo que encuentre. Devuelve (convocatoria, info)."""
    texto, fuentes = texto_bases(conv)
    info = {"fuentes": fuentes, "caracteres": len(texto), "metodo": None}
    if len(texto) < 200:
        info["metodo"] = "sin texto"
        return conv, info
    datos = extraer_llm(texto) if llm.disponible() else None
    info["metodo"] = f"IA ({llm.modelo()})" if datos else "heurísticas"
    datos = datos or extraer_heuristico(texto)
    c = conv.model_copy(deep=True)
    ya = {r.id for r in c.requisitos}
    validos = {"tamano", "empleados", "facturacion", "antiguedad_anios", "cnae", "inversion_prevista",
               "minimis_recibido_3_anios", "al_corriente_hacienda", "al_corriente_ss"}
    for r in datos.get("requisitos", []):
        if r.id in ya or r.campo in ("al_corriente_hacienda", "al_corriente_ss"):
            continue
        if r.op != "cualitativo" and r.campo not in validos:
            r.op = "cualitativo"
        c.requisitos.append(r)
    for k in ("importe_max", "intensidad"):
        if isinstance(datos.get(k), (int, float)) and datos[k] > 0:
            setattr(c, k, float(datos[k]))
    if datos.get("criterios_valoracion"):
        c.criterios_valoracion = [str(x) for x in datos["criterios_valoracion"]][:12]
    if datos.get("documentos"):
        c.documentos = [str(x) for x in datos["documentos"]][:15]
    info["requisitos_nuevos"] = len(c.requisitos) - len(conv.requisitos)
    return c, info
