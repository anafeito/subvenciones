"""Modelos de datos."""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Tamano(str, Enum):
    micro = "micro"
    pequena = "pequena"
    mediana = "mediana"
    grande = "grande"


class Perfil(BaseModel):
    cif: Optional[str] = None
    razon_social: Optional[str] = None
    forma_juridica: Optional[str] = None
    fecha_constitucion: Optional[date] = None
    comunidad: Optional[str] = None
    provincia: Optional[str] = None
    cnae: Optional[str] = None
    empleados: Optional[int] = None
    facturacion: Optional[float] = None
    al_corriente_hacienda: Optional[bool] = None
    al_corriente_ss: Optional[bool] = None
    minimis_recibido_3_anios: Optional[float] = None
    proyecto: Optional[str] = None
    inversion_prevista: Optional[float] = None
    fuentes: dict[str, str] = Field(default_factory=dict)

    def tamano(self) -> Optional[Tamano]:
        if self.empleados is None:
            return None
        e, f = self.empleados, self.facturacion
        if e < 10 and (f is None or f <= 2_000_000):
            return Tamano.micro
        if e < 50 and (f is None or f <= 10_000_000):
            return Tamano.pequena
        if e < 250 and (f is None or f <= 50_000_000):
            return Tamano.mediana
        return Tamano.grande

    def antiguedad_anios(self, hoy: Optional[date] = None) -> Optional[float]:
        if not self.fecha_constitucion:
            return None
        return ((hoy or date.today()) - self.fecha_constitucion).days / 365.25

    def es_empresa(self) -> bool:
        return True  # el copiloto está pensado para personas jurídicas o autónomos con actividad


class Requisito(BaseModel):
    """op: '<' '<=' '>' '>=' '==' 'in' 'prefix_in' 'nuts' 'true' 'cualitativo'"""
    id: str
    texto: str
    campo: str
    op: str
    valor: Any = None
    cita: Optional[str] = None


class Convocatoria(BaseModel):
    id: str
    codigo_bdns: Optional[str] = None
    titulo: str
    organo: Optional[str] = None
    nivel1: Optional[str] = None             # ESTATAL | AUTONOMICA | LOCAL | OTROS
    ambito: Optional[str] = None
    regiones: list[str] = Field(default_factory=list)   # códigos NUTS: ES, ES52, ES523...
    importe_max: Optional[float] = None
    intensidad: Optional[float] = None
    presupuesto_total: Optional[float] = None
    fecha_recepcion: Optional[date] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    abierto: Optional[bool] = None
    texto_plazo: Optional[str] = None
    tipo_convocatoria: Optional[str] = None
    concurrencia_competitiva: Optional[bool] = None
    minimis: bool = False
    tipo: Optional[str] = None
    beneficiarios: list[str] = Field(default_factory=list)
    sectores: list[str] = Field(default_factory=list)   # "72 - Investigación y desarrollo"
    finalidad: Optional[str] = None
    objetivos: list[str] = Field(default_factory=list)
    fondos: list[str] = Field(default_factory=list)
    reglamento: Optional[str] = None
    resumen: Optional[str] = None
    url_bases: Optional[str] = None
    sede: Optional[str] = None
    url_bdns: Optional[str] = None
    anuncios: list[dict] = Field(default_factory=list)
    documentos_bdns: list[dict] = Field(default_factory=list)
    requisitos: list[Requisito] = Field(default_factory=list)
    criterios_valoracion: list[str] = Field(default_factory=list)
    documentos: list[str] = Field(default_factory=list)
    fuente: str = "bdns"

    def texto_busqueda(self) -> str:
        return " ".join([self.titulo, self.finalidad or "", self.resumen or "", " ".join(self.objetivos),
                         " ".join(self.sectores), " ".join(self.fondos)])


class Estado(str, Enum):
    cumple = "cumple"
    no_cumple = "no_cumple"
    falta_dato = "falta_dato"
    revisar = "revisar"


class Evaluacion(BaseModel):
    requisito: Requisito
    estado: Estado
    explicacion: str


class Encaje(BaseModel):
    puntuacion: float          # 0-1
    banda: str                 # alta | media | baja
    factores: list[str]


class Resultado(BaseModel):
    convocatoria: Convocatoria
    evaluaciones: list[Evaluacion]
    elegible: bool
    faltan_datos: int
    encaje: Encaje
    dias_restantes: Optional[int]
    puntuacion: float
