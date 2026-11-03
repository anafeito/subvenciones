"""LLM gratuito y opcional, vía cualquier API compatible con OpenAI.

Configúralo con variables de entorno o con los *secrets* de Streamlit:

  Groq (capa gratuita, recomendado en Streamlit Cloud):
      LLM_BASE_URL = "https://api.groq.com/openai/v1"
      LLM_MODEL    = "llama-3.3-70b-versatile"
      LLM_API_KEY  = "gsk_..."             # gratis en console.groq.com
  Google Gemini (capa gratuita):
      LLM_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
      LLM_MODEL    = "gemini-2.0-flash"    # usa un modelo disponible en tu cuenta
      LLM_API_KEY  = "..."                 # gratis en aistudio.google.com
  Ollama (local):
      LLM_BASE_URL = "http://localhost:11434/v1"   LLM_MODEL = "llama3.1"

Sin configuración, todo funciona con plantillas y heurísticas (coste 0 €).
Los nombres de modelo cambian con el tiempo: si uno falla, prueba otro de la lista del proveedor.
"""
from __future__ import annotations

import json
import os
from typing import Iterator, Optional

import httpx


def _cfg(clave: str, defecto: str = "") -> str:
    v = os.getenv(clave)
    if v:
        return v
    try:
        import streamlit as st
        return str(st.secrets.get(clave, defecto))
    except Exception:
        return defecto


def config() -> tuple[str, str, str]:
    return (_cfg("LLM_BASE_URL").rstrip("/"), _cfg("LLM_MODEL", "llama-3.3-70b-versatile"), _cfg("LLM_API_KEY", "x"))


def disponible() -> bool:
    return bool(config()[0])


def modelo() -> Optional[str]:
    return config()[1] if disponible() else None


def _peticion(prompt: str, max_tokens: int, temperatura: float, stream: bool) -> dict:
    return {"model": config()[1], "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": temperatura, "stream": stream}


def completar(prompt: str, max_tokens: int = 1500, temperatura: float = 0.2) -> Optional[str]:
    base, _, key = config()
    if not base:
        return None
    try:
        r = httpx.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"},
                       json=_peticion(prompt, max_tokens, temperatura, False), timeout=90)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None


def stream(prompt: str, max_tokens: int = 2500) -> Iterator[str]:
    base, _, key = config()
    if not base:
        return
    try:
        with httpx.stream("POST", f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"},
                          json=_peticion(prompt, max_tokens, 0.4, True), timeout=120) as r:
            r.raise_for_status()
            for linea in r.iter_lines():
                if not linea.startswith("data: ") or linea.strip() == "data: [DONE]":
                    continue
                try:
                    delta = json.loads(linea[6:])["choices"][0].get("delta", {}).get("content")
                except (ValueError, KeyError, IndexError):
                    continue
                if delta:
                    yield delta
    except Exception:
        return
