"""Motor de elegibilidad determinista.

Cada requisito se evalúa contra el perfil y devuelve cumple / no_cumple / falta_dato,
siempre con la cita de las bases. Los requisitos cualitativos quedan en 'revisar':
el motor nunca adivina.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from .models import Estado, Evaluacion, Perfil, Requisito, Tamano
from .territorio import cubre, nombre_region, nuts_perfil

ETIQUETAS = {
    "tamano": "tamaño", "empleados": "plantilla", "facturacion": "facturación", "antiguedad_anios": "antigüedad (años)",
    "comunidad": "comunidad", "cnae": "CNAE", "al_corriente_hacienda": "al corriente con Hacienda",
    "al_corriente_ss": "al corriente con la Seguridad Social", "minimis_recibido_3_anios": "ayudas de minimis en 3 años",
    "inversion_prevista": "inversión prevista",
}
OPS = {"<": "menos de", "<=": "como máximo", ">": "más de", ">=": "al menos", "==": "igual a"}
ORDEN_TAMANO = {Tamano.micro: 0, Tamano.pequena: 1, Tamano.mediana: 2, Tamano.grande: 3}


def _valor_perfil(perfil: Perfil, campo: str, hoy: Optional[date]) -> Any:
    if campo == "tamano":
        return perfil.tamano()
    if campo == "antiguedad_anios":
        return perfil.antiguedad_anios(hoy)
    return getattr(perfil, campo, None)


def _comparar(actual: Any, op: str, esperado: Any) -> bool:
    if isinstance(actual, Tamano):
        a = ORDEN_TAMANO[actual]
        if op in ("in", "not_in"):
            vals = {Tamano(v) for v in esperado}
            return (actual in vals) if op == "in" else (actual not in vals)
        b = ORDEN_TAMANO[Tamano(esperado)]
        actual, esperado = a, b
    if op == "<":
        return actual < esperado
    if op == "<=":
        return actual <= esperado
    if op == ">":
        return actual > esperado
    if op == ">=":
        return actual >= esperado
    if op == "==":
        return actual == esperado
    if op == "in":
        return actual in esperado
    if op == "not_in":
        return actual not in esperado
    if op == "prefix_in":  # CNAE: '2511' cumple si alguna entrada es prefijo ('25')
        return any(str(actual).startswith(str(p)) for p in esperado)
    if op == "not_prefix_in":
        return not any(str(actual).startswith(str(p)) for p in esperado)
    if op == "true":
        return bool(actual) is True
    raise ValueError(f"Operador desconocido: {op}")


def _fmt(v: Any) -> str:
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 1000:
        return f"{v:,.0f} €".replace(",", ".")
    if isinstance(v, float):
        return f"{v:g}" if v.is_integer() else f"{v:.1f}"
    if isinstance(v, Tamano) or v in ("micro", "pequena", "mediana", "grande"):
        return {"micro": "microempresa", "pequena": "pequeña", "mediana": "mediana", "grande": "grande"}[getattr(v, "value", v)]
    if isinstance(v, (list, tuple, set)):
        return ", ".join(str(x) for x in v)
    return str(v)


def evaluar_requisito(perfil: Perfil, req: Requisito, hoy: Optional[date] = None) -> Evaluacion:
    cita = f" ({req.cita})" if req.cita else ""
    if req.op == "cualitativo":
        return Evaluacion(requisito=req, estado=Estado.revisar,
                          explicacion=f"Requisito cualitativo: lo valida la gestoría{cita}.")
    if req.op == "nuts":  # ámbito territorial por códigos NUTS de la BDNS
        nuts = nuts_perfil(perfil.provincia, perfil.comunidad)
        zonas = ", ".join(nombre_region(r) for r in req.valor[:5])
        if not nuts:
            return Evaluacion(requisito=req, estado=Estado.falta_dato,
                              explicacion=f"Indica la provincia o comunidad de la empresa. Ámbito: {zonas}{cita}.")
        c = cubre(req.valor, nuts)
        if c is None:
            return Evaluacion(requisito=req, estado=Estado.falta_dato,
                              explicacion=f"La ayuda es para {zonas}: indica la provincia{cita}.")
        return Evaluacion(requisito=req, estado=Estado.cumple if c else Estado.no_cumple,
                          explicacion=f"Ámbito: {zonas}; la empresa está en {nombre_region(nuts)}{cita}.")
    actual = _valor_perfil(perfil, req.campo, hoy)
    if actual is None:
        return Evaluacion(requisito=req, estado=Estado.falta_dato,
                          explicacion=f"Falta el dato «{ETIQUETAS.get(req.campo, req.campo)}» en el perfil{cita}.")
    try:
        ok = _comparar(actual, req.op, req.valor)
    except (TypeError, ValueError) as e:
        return Evaluacion(requisito=req, estado=Estado.revisar,
                          explicacion=f"No se pudo evaluar automáticamente ({e}){cita}.")
    estado = Estado.cumple if ok else Estado.no_cumple
    nombre = ETIQUETAS.get(req.campo, req.campo)
    if req.op == "true":
        expl = f"{nombre[:1].upper() + nombre[1:]}: {'sí' if actual else 'no'}{cita}."
    elif req.op in ("in", "prefix_in", "not_in", "not_prefix_in"):
        lista = _fmt(req.valor) if len(req.valor) <= 6 else f"{_fmt(req.valor[:6])}…"
        expl = f"{nombre[:1].upper() + nombre[1:]}: {_fmt(actual)} (admitidos: {lista}){cita}."
    else:
        expl = f"{nombre[:1].upper() + nombre[1:]}: {_fmt(actual)}; se exige {OPS.get(req.op, req.op)} {_fmt(req.valor)}{cita}."
    return Evaluacion(requisito=req, estado=estado, explicacion=expl)


def evaluar(perfil: Perfil, requisitos: list[Requisito], hoy: Optional[date] = None) -> list[Evaluacion]:
    return [evaluar_requisito(perfil, r, hoy) for r in requisitos]
