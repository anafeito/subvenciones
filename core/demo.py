"""Catálogo de EJEMPLO (convocatorias ficticias) para enseñar la app sin conexión.
Las fechas son relativas a hoy para que siempre haya plazos abiertos."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .models import Convocatoria

RUTA = Path(__file__).resolve().parent.parent / "data" / "demo_convocatorias.json"


def cargar() -> list[Convocatoria]:
    hoy = date.today()
    out = []
    for c in json.loads(RUTA.read_text(encoding="utf-8")):
        c = dict(c)
        c["fecha_inicio"] = hoy - timedelta(days=c.pop("abierta_hace_dias", 10))
        c["fecha_fin"] = hoy + timedelta(days=c.pop("cierra_en_dias", 30))
        c.pop("tasa_concesion_hist", None)
        c["titulo"] = c["titulo"] + " [EJEMPLO]"
        c["nivel1"] = "ESTATAL" if c.get("ambito") == "Estatal" else "AUTONOMICA"
        out.append(Convocatoria(**c))
    return out
