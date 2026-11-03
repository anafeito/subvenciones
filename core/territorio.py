"""Comunidades y provincias con su código NUTS (el que usa la BDNS en `regiones`)."""
from __future__ import annotations

import re
import unicodedata

COMUNIDADES = {
    "Andalucía": "ES61", "Aragón": "ES24", "Principado de Asturias": "ES12", "Illes Balears": "ES53",
    "Canarias": "ES70", "Cantabria": "ES13", "Castilla y León": "ES41", "Castilla-La Mancha": "ES42",
    "Cataluña": "ES51", "Comunitat Valenciana": "ES52", "Extremadura": "ES43", "Galicia": "ES11",
    "Comunidad de Madrid": "ES30", "Región de Murcia": "ES62", "Comunidad Foral de Navarra": "ES22",
    "País Vasco": "ES21", "La Rioja": "ES23", "Ceuta": "ES63", "Melilla": "ES64",
}

PROVINCIAS = {  # provincia -> (NUTS3, comunidad)
    "A Coruña": ("ES111", "Galicia"), "Lugo": ("ES112", "Galicia"), "Ourense": ("ES113", "Galicia"),
    "Pontevedra": ("ES114", "Galicia"), "Asturias": ("ES120", "Principado de Asturias"),
    "Cantabria": ("ES130", "Cantabria"), "Araba/Álava": ("ES211", "País Vasco"),
    "Gipuzkoa": ("ES212", "País Vasco"), "Bizkaia": ("ES213", "País Vasco"),
    "Navarra": ("ES220", "Comunidad Foral de Navarra"), "La Rioja": ("ES230", "La Rioja"),
    "Huesca": ("ES241", "Aragón"), "Teruel": ("ES242", "Aragón"), "Zaragoza": ("ES243", "Aragón"),
    "Madrid": ("ES300", "Comunidad de Madrid"), "Ávila": ("ES411", "Castilla y León"),
    "Burgos": ("ES412", "Castilla y León"), "León": ("ES413", "Castilla y León"),
    "Palencia": ("ES414", "Castilla y León"), "Salamanca": ("ES415", "Castilla y León"),
    "Segovia": ("ES416", "Castilla y León"), "Soria": ("ES417", "Castilla y León"),
    "Valladolid": ("ES418", "Castilla y León"), "Zamora": ("ES419", "Castilla y León"),
    "Albacete": ("ES421", "Castilla-La Mancha"), "Ciudad Real": ("ES422", "Castilla-La Mancha"),
    "Cuenca": ("ES423", "Castilla-La Mancha"), "Guadalajara": ("ES424", "Castilla-La Mancha"),
    "Toledo": ("ES425", "Castilla-La Mancha"), "Badajoz": ("ES431", "Extremadura"),
    "Cáceres": ("ES432", "Extremadura"), "Barcelona": ("ES511", "Cataluña"), "Girona": ("ES512", "Cataluña"),
    "Lleida": ("ES513", "Cataluña"), "Tarragona": ("ES514", "Cataluña"),
    "Alicante/Alacant": ("ES521", "Comunitat Valenciana"), "Castellón/Castelló": ("ES522", "Comunitat Valenciana"),
    "Valencia/València": ("ES523", "Comunitat Valenciana"), "Illes Balears": ("ES53", "Illes Balears"),
    "Almería": ("ES611", "Andalucía"), "Cádiz": ("ES612", "Andalucía"), "Córdoba": ("ES613", "Andalucía"),
    "Granada": ("ES614", "Andalucía"), "Huelva": ("ES615", "Andalucía"), "Jaén": ("ES616", "Andalucía"),
    "Málaga": ("ES617", "Andalucía"), "Sevilla": ("ES618", "Andalucía"), "Murcia": ("ES620", "Región de Murcia"),
    "Ceuta": ("ES630", "Ceuta"), "Melilla": ("ES640", "Melilla"),
    "Las Palmas": ("ES70", "Canarias"), "Santa Cruz de Tenerife": ("ES70", "Canarias"),
}

_COD_A_COM = {v: k for k, v in COMUNIDADES.items()}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]", " ", s).strip()


def nuts_perfil(provincia: str | None, comunidad: str | None) -> str | None:
    """Código NUTS más fino conocido del perfil."""
    if provincia:
        for p, (cod, _) in PROVINCIAS.items():
            if _norm(provincia) in _norm(p).split(" ") or _norm(p).startswith(_norm(provincia)):
                return cod
    if comunidad:
        return COMUNIDADES.get(comunidad) or next(
            (c for k, c in COMUNIDADES.items() if _norm(comunidad) in _norm(k) or _norm(k) in _norm(comunidad)), None)
    return None


def codigo_region(descripcion: str) -> str | None:
    """'ES53 - ILLES BALEARS' -> 'ES53'.  'ESPAÑA' -> 'ES'."""
    m = re.match(r"\s*(ES[0-9A-Z]{0,3})\b", descripcion or "")
    if m:
        return m.group(1)
    if "espa" in _norm(descripcion):
        return "ES"
    return None


def nombre_region(cod: str) -> str:
    if cod == "ES":
        return "Toda España"
    if cod in _COD_A_COM:
        return _COD_A_COM[cod]
    for p, (c, _) in PROVINCIAS.items():
        if c == cod:
            return p
    return cod


def cubre(regiones: list[str], nuts: str) -> bool | None:
    """True si alguna región contiene la ubicación del perfil; None si depende de un dato más fino
    (p. ej. el perfil solo dice la comunidad y la ayuda es de una provincia); False si no."""
    if any(nuts.startswith(r) for r in regiones):
        return True
    if any(r.startswith(nuts) for r in regiones):
        return None
    return False
