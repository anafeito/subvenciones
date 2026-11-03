"""Perfil de empresa a partir del CIF, con datos públicos reales de la BDNS.

Con el CIF se consulta:
  - /concesiones/busqueda?nifCif=  -> razón social y ayudas recibidas (historial real)
  - /minimis/busqueda?nifCif=      -> ayudas de minimis de los últimos 3 años (para el tope de 300.000 €)
El resto (plantilla, facturación, CNAE, proyecto) lo declara la empresa o la gestoría.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, timedelta
from typing import Optional

from . import bdns
from .models import Perfil
from .territorio import COMUNIDADES, _norm

FORMAS = {"A": "Sociedad anónima", "B": "Sociedad limitada", "C": "Sociedad colectiva",
          "D": "Sociedad comanditaria", "E": "Comunidad de bienes", "F": "Sociedad cooperativa",
          "G": "Asociación o fundación", "J": "Sociedad civil", "N": "Entidad extranjera",
          "U": "Unión temporal de empresas", "V": "Otro tipo"}


def limpiar(cif: str) -> str:
    return re.sub(r"[\s.-]", "", cif or "").upper()


def validar_cif(cif: str) -> bool:
    cif = limpiar(cif)
    if re.fullmatch(r"\d{8}[A-Z]", cif):  # NIF de autónomo
        return cif[-1] == "TRWAGMYFPDXBNJZSQVHLCKE"[int(cif[:8]) % 23]
    if re.fullmatch(r"[XYZ]\d{7}[A-Z]", cif):  # NIE
        n = int("XYZ".index(cif[0]).__str__() + cif[1:8])
        return cif[-1] == "TRWAGMYFPDXBNJZSQVHLCKE"[n % 23]
    if not re.fullmatch(r"[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]", cif):
        return False
    d = cif[1:8]
    pares = sum(int(x) for x in d[1::2])
    impares = sum(sum(divmod(int(x) * 2, 10)) for x in d[0::2])
    control = (10 - (pares + impares) % 10) % 10
    fin = cif[-1]
    if cif[0] in "PQRSNW":
        return fin == "JABCDEFGHI"[control]
    if cif[0] in "ABEH":
        return fin == str(control)
    return fin in (str(control), "JABCDEFGHI"[control])


def _comunidad_desde(nivel2: str) -> Optional[str]:
    n = _norm(nivel2)
    for c in COMUNIDADES:
        cn = _norm(c)
        if cn in n or n in cn or n.split(" ")[-1] == cn.split(" ")[-1]:
            return c
    return None


def desde_cif(cif: str, consultar_bdns: bool = True) -> tuple[Perfil, list[dict], list[str]]:
    """Devuelve (perfil, historial de ayudas, avisos)."""
    cif = limpiar(cif)
    avisos: list[str] = []
    if not validar_cif(cif):
        avisos.append("El CIF/NIF no supera la validación del dígito de control: revísalo.")
    p = Perfil(cif=cif, forma_juridica=FORMAS.get(cif[:1]) if cif[:1].isalpha() and cif[:1] not in "XYZ" else
               "Persona física (autónomo)")
    p.fuentes["forma_juridica"] = "CIF"
    historial: list[dict] = []
    if not consultar_bdns:
        return p, historial, avisos
    try:
        historial = bdns.concesiones_nif(cif)
    except Exception:
        avisos.append("No se pudo consultar la BDNS ahora mismo; completa el perfil a mano.")
        return p, historial, avisos
    if historial:
        benef = str(historial[0].get("beneficiario") or "")
        nombre = benef.split(" ", 1)[1].strip() if " " in benef else benef
        if nombre:
            p.razon_social, p.fuentes["razon_social"] = nombre, "BDNS"
        auton = [h.get("nivel2") for h in historial if h.get("nivel1") == "AUTONOMICA" and h.get("nivel2")]
        if auton:
            com = _comunidad_desde(Counter(auton).most_common(1)[0][0])
            if com:
                p.comunidad, p.fuentes["comunidad"] = com, "BDNS (deducida)"
    else:
        avisos.append("Este CIF no tiene ayudas publicadas en la BDNS: completa el nombre y los datos a mano.")
    try:
        hace3 = date.today() - timedelta(days=3 * 365)
        mm = [m for m in bdns.minimis_nif(cif) if (bdns._fecha(m.get("fechaConcesion")) or date.min) >= hace3]
        p.minimis_recibido_3_anios = round(sum(float(m.get("ayudaEquivalente") or 0) for m in mm), 2)
        p.fuentes["minimis_recibido_3_anios"] = "BDNS"
    except Exception:
        pass
    return p, historial, avisos
