"""Borrador de memoria técnica: LLM gratuito en streaming o plantilla (coste 0 €)."""
from __future__ import annotations

from datetime import date
from typing import Iterator

from . import cnae, llm
from .models import Convocatoria, Estado, Evaluacion, Perfil

TAM = {"micro": "microempresa", "pequena": "pequeña empresa", "mediana": "mediana empresa", "grande": "gran empresa"}


def _eur(v) -> str:
    return f"{v:,.0f} €".replace(",", ".") if v is not None else "[COMPLETAR]"


def _pct(v) -> str:
    return f"{v:g} %" if v is not None else "[ver bases]"


def _fecha(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "[ver convocatoria]"


def prompt(p: Perfil, c: Convocatoria, evals: list[Evaluacion]) -> str:
    reqs = "\n".join(f"- {e.requisito.texto}: {e.estado.value}" for e in evals)
    crit = "\n".join(f"- {x}" for x in c.criterios_valoracion) or "- (no detallados: usa calidad técnica, viabilidad e impacto)"
    tam = TAM.get(p.tamano().value) if p.tamano() else "[COMPLETAR]"
    return f"""Redacta en español el BORRADOR de la memoria técnica para solicitar esta ayuda pública.
Formato Markdown con encabezados ##. Tono profesional y concreto. NO inventes cifras, fechas ni datos de la empresa:
donde falte información escribe [COMPLETAR: qué falta]. Estructura:
## 1. Entidad solicitante  ## 2. Descripción del proyecto  ## 3. Objetivos y resultados medibles
## 4. Presupuesto y calendario  ## 5. Respuesta a los criterios de valoración (uno por uno)  ## 6. Impacto
## Pendiente antes de presentar (requisitos sin verificar) ## Documentación a adjuntar

CONVOCATORIA: {c.titulo}
Órgano: {c.organo}. Código BDNS: {c.codigo_bdns}. Finalidad: {c.finalidad}. Plazo hasta: {_fecha(c.fecha_fin)}.
Importe máximo por beneficiario: {_eur(c.importe_max) if c.importe_max else 'ver bases'}; intensidad: {_pct(c.intensidad)}.
Criterios de valoración:
{crit}
Documentación: {', '.join(c.documentos)}

EMPRESA: {p.razon_social} (CIF {p.cif}), {p.forma_juridica}; actividad CNAE {p.cnae} ({cnae.descripcion(p.cnae)});
{p.empleados} empleados ({tam}); facturación {_eur(p.facturacion)}; ubicación {p.provincia}, {p.comunidad}.
PROYECTO: {p.proyecto or '[COMPLETAR]'}. Inversión prevista: {_eur(p.inversion_prevista)}.
Requisitos evaluados:
{reqs}
"""


def plantilla(p: Perfil, c: Convocatoria, evals: list[Evaluacion]) -> str:
    sub = None
    if p.inversion_prevista and c.intensidad:
        sub = p.inversion_prevista * c.intensidad / 100
        sub = min(sub, c.importe_max) if c.importe_max else sub
    pend = [e for e in evals if e.estado in (Estado.falta_dato, Estado.revisar)]
    crit = "\n".join(f"### 5.{i} {x}\n[COMPLETAR: cómo responde el proyecto a este criterio, con datos.]\n"
                     for i, x in enumerate(c.criterios_valoracion, 1)) or \
        "[Revisa los criterios de valoración en las bases y responde a cada uno.]\n"
    tam = TAM.get(p.tamano().value) if p.tamano() else "[COMPLETAR]"
    return f"""# Memoria técnica — {c.titulo}

*Borrador generado el {date.today():%d/%m/%Y} para la convocatoria BDNS {c.codigo_bdns or '—'}. Revíselo antes de presentarlo.*

## 1. Entidad solicitante
- **Razón social:** {p.razon_social or '[COMPLETAR]'} · **CIF:** {p.cif or '[COMPLETAR]'}
- **Forma jurídica:** {p.forma_juridica or '[COMPLETAR]'} · **Tamaño:** {tam} ({p.empleados if p.empleados is not None else '[COMPLETAR]'} personas)
- **Actividad:** CNAE {p.cnae or '[COMPLETAR]'} — {cnae.descripcion(p.cnae) or '[COMPLETAR]'}
- **Ubicación:** {p.provincia or '[COMPLETAR]'} ({p.comunidad or '[COMPLETAR]'})

## 2. Descripción del proyecto
{p.proyecto or '[COMPLETAR: qué se va a hacer, por qué y cómo]'}

El proyecto se presenta a «{c.titulo}», de {c.organo or '[órgano convocante]'}, con finalidad: {c.finalidad or '[ver bases]'}.

## 3. Objetivos y resultados medibles
1. [COMPLETAR: objetivo principal e indicador]
2. [COMPLETAR: objetivo secundario e indicador]

## 4. Presupuesto y calendario
| Concepto | Importe |
| --- | --- |
| Inversión total prevista | {_eur(p.inversion_prevista)} |
| Intensidad de la ayuda | {_pct(c.intensidad)} |
| Ayuda solicitada (estimada) | {_eur(sub)} |

Plazo de solicitud hasta: {_fecha(c.fecha_fin)}. Ejecución: [COMPLETAR].

## 5. Respuesta a los criterios de valoración
{crit}
## 6. Impacto
[COMPLETAR: empleo, productividad, ahorro energético, ventas, impacto territorial.]

## Pendiente antes de presentar
{chr(10).join(f'- {e.requisito.texto} — {e.explicacion}' for e in pend) or '- Ninguno'}

## Documentación a adjuntar
{chr(10).join(f'- [ ] {d}' for d in c.documentos)}
"""


def generar(p: Perfil, c: Convocatoria, evals: list[Evaluacion]) -> Iterator[str]:
    emitido = False
    for trozo in llm.stream(prompt(p, c, evals)):
        emitido = True
        yield trozo
    if not emitido:
        texto = plantilla(p, c, evals)
        for i in range(0, len(texto), 60):
            yield texto[i:i + 60]
