"""Cliente de la Base de Datos Nacional de Subvenciones (BDNS / SNPSAP).

API pública, sin clave: https://www.infosubvenciones.es/bdnstrans/api
Especificación OpenAPI: https://www.infosubvenciones.es/bdnstrans/estaticos/doc/snpsap-api.json

Endpoints usados (verificados contra la API en noviembre de 2026):
  GET /convocatorias/busqueda   page, pageSize, order, direccion, vpd, fechaDesde/fechaHasta (dd/mm/yyyy)
  GET /convocatorias            numConv (obligatorio), vpd          -> detalle
  GET /concesiones/busqueda     nifCif, page, pageSize, ...          -> ayudas recibidas por una empresa
  GET /minimis/busqueda         nifCif, ...                          -> ayudas de minimis recibidas

La BDNS pide no hacer sondeos intensivos: este cliente limita la concurrencia, hace pausas
y guarda en disco lo ya consultado para no repetir peticiones.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import httpx

from . import cnae
from .models import Convocatoria, Requisito
from .territorio import codigo_region

BASE = os.getenv("BDNS_BASE", "https://www.infosubvenciones.es/bdnstrans/api")
VPD = os.getenv("BDNS_VPD", "GE")
DATA = Path(__file__).resolve().parent.parent / "data"
CATALOGO = DATA / "catalogo.json.gz"
VISTOS = DATA / "vistos.json.gz"
UA = {"Accept": "application/json", "User-Agent": "copiloto-subvenciones/1.0 (+https://github.com)"}

_cliente: Optional[httpx.Client] = None


def cliente() -> httpx.Client:
    global _cliente
    if _cliente is None:
        _cliente = httpx.Client(base_url=BASE, headers=UA, timeout=30)
    return _cliente


def _get(path: str, params: dict, reintentos: int = 3) -> Any:
    for i in range(reintentos):
        try:
            r = cliente().get(path, params=params)
            if r.status_code in (429, 502, 503, 504):
                raise httpx.HTTPStatusError("reintentar", request=r.request, response=r)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            if i == reintentos - 1:
                raise
            time.sleep(2 * (i + 1))


def _fecha(v: Any) -> Optional[date]:
    if not v:
        return None
    s = str(v)[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


# --------------------------------------------------------------------------- consultas

def listar(desde: date, hasta: Optional[date] = None, page: int = 0, size: int = 200) -> dict:
    p = {"vpd": VPD, "page": page, "pageSize": size, "fechaDesde": _dmy(desde),
         "order": "numeroConvocatoria", "direccion": "desc"}
    if hasta:
        p["fechaHasta"] = _dmy(hasta)
    return _get("/convocatorias/busqueda", p)


def listar_todo(desde: date, hasta: Optional[date] = None, size: int = 200, max_paginas: int = 200) -> Iterable[dict]:
    for page in range(max_paginas):
        data = listar(desde, hasta, page, size)
        filas = data.get("content") or []
        yield from filas
        if data.get("last", True) or not filas:
            break
        time.sleep(0.3)


def detalle(num_conv: str) -> dict:
    return _get("/convocatorias", {"numConv": num_conv, "vpd": VPD})


def concesiones_nif(nif: str, size: int = 200) -> list[dict]:
    """Ayudas concedidas a un NIF/CIF (las más recientes primero)."""
    data = _get("/concesiones/busqueda", {"vpd": VPD, "nifCif": nif, "page": 0, "pageSize": size,
                                          "order": "fechaConcesion", "direccion": "desc"})
    return data.get("content") or []


def minimis_nif(nif: str, size: int = 200) -> list[dict]:
    data = _get("/minimis/busqueda", {"vpd": VPD, "nifCif": nif, "page": 0, "pageSize": size,
                                      "order": "fechaConcesion", "direccion": "desc"})
    return data.get("content") or []


def url_publica(codigo: str) -> str:
    return f"https://www.infosubvenciones.es/bdnstrans/GE/es/convocatoria/{codigo}"


# --------------------------------------------------------------------------- mapeo

def _descs(v: Any) -> list[str]:
    return [str(x.get("descripcion", "")).strip() if isinstance(x, dict) else str(x).strip() for x in (v or [])]


def es_para_empresas(beneficiarios: list[str]) -> bool:
    """La BDNS usa tipos como 'PYME Y PERSONAS FÍSICAS QUE DESARROLLAN ACTIVIDAD ECONÓMICA', 'GRAN EMPRESA',
    'PERSONAS JURÍDICAS QUE NO DESARROLLAN ACTIVIDAD ECONÓMICA', 'PERSONAS FÍSICAS QUE NO DESARROLLAN...'."""
    if not beneficiarios:
        return True  # sin dato: no descartamos
    b = " | ".join(beneficiarios).upper()
    return "PYME" in b or "GRAN EMPRESA" in b or re.search(r"(?<!NO )DESARROLLAN ACTIVIDAD ECON", b) is not None


def mapear(d: dict) -> Convocatoria:
    org = d.get("organo") or {}
    codigo = str(d.get("codigoBDNS") or d.get("numeroConvocatoria") or d.get("id"))
    beneficiarios = _descs(d.get("tiposBeneficiarios"))
    regiones_txt = _descs(d.get("regiones"))
    regiones = sorted({c for c in (codigo_region(r) for r in regiones_txt) if c})
    sectores_raw = [s for s in (d.get("sectores") or []) if isinstance(s, dict)]
    sectores = [f"{s.get('codigo')} - {s.get('descripcion', '')}".strip(" -") for s in sectores_raw]
    reglamento = ((d.get("reglamento") or {}).get("descripcion") if isinstance(d.get("reglamento"), dict)
                  else d.get("reglamento"))
    tipo_conv = d.get("tipoConvocatoria") or ""
    cita = f"Ficha BDNS {codigo}"
    reqs: list[Requisito] = []

    bu = " | ".join(beneficiarios).upper()
    pyme, gran = "PYME" in bu, "GRAN EMPRESA" in bu
    if pyme and not gran:
        reqs.append(Requisito(id="pyme", texto="Beneficiarios: pymes y autónomos", campo="tamano", op="<=",
                              valor="mediana", cita=cita))
    elif gran and not pyme:
        reqs.append(Requisito(id="gran", texto="Beneficiarios: gran empresa", campo="tamano", op="==",
                              valor="grande", cita=cita))
    if regiones and "ES" not in regiones:
        reqs.append(Requisito(id="territorio", texto="Ámbito territorial de la convocatoria", campo="ubicacion",
                              op="nuts", valor=regiones, cita=cita))
    codigos = sorted({c for s in sectores_raw for c in cnae.normalizar(str(s.get("codigo") or ""))})
    if codigos and len(codigos) <= 60:
        reqs.append(Requisito(id="cnae", texto="Sector de actividad (CNAE)", campo="cnae", op="prefix_in",
                              valor=codigos, cita=cita))
    regl = (reglamento or "").lower()
    if "minimis" in regl or "2023/2831" in regl or "1407/2013" in regl:
        reqs.append(Requisito(id="minimis", texto="No superar 300.000 € de ayudas de minimis en 3 años",
                              campo="minimis_recibido_3_anios", op="<", valor=300000.0,
                              cita="Reglamento (UE) 2023/2831"))
    elif "1408/2013" in regl or "717/2014" in regl:
        reqs.append(Requisito(id="minimis", texto="Límite de minimis sectorial (agrario o pesquero)",
                              campo="minimis", op="cualitativo", cita=reglamento))
    reqs += [
        Requisito(id="hacienda", texto="Estar al corriente con Hacienda", campo="al_corriente_hacienda",
                  op="true", valor=True, cita="Ley 38/2003, art. 13"),
        Requisito(id="ss", texto="Estar al corriente con la Seguridad Social", campo="al_corriente_ss",
                  op="true", valor=True, cita="Ley 38/2003, art. 13"),
    ]

    tl = tipo_conv.lower()
    competitiva = None
    if "competitiva" in tl:
        competitiva = "no competitiva" not in tl
    elif "directa" in tl:
        competitiva = False

    return Convocatoria(
        id=codigo, codigo_bdns=codigo,
        titulo=(d.get("descripcion") or d.get("descripcionLeng") or "Convocatoria sin título").strip(),
        organo=" · ".join(x for x in (org.get("nivel2"), org.get("nivel3")) if x) or None,
        nivel1=org.get("nivel1"),
        ambito=", ".join(regiones_txt) or None,
        regiones=regiones,
        presupuesto_total=d.get("presupuestoTotal"),
        fecha_recepcion=_fecha(d.get("fechaRecepcion")),
        fecha_inicio=_fecha(d.get("fechaInicioSolicitud")),
        fecha_fin=_fecha(d.get("fechaFinSolicitud")),
        abierto=d.get("abierto"),
        texto_plazo=" ".join(x for x in (d.get("textInicio"), d.get("textFin")) if x) or None,
        tipo_convocatoria=tipo_conv or None,
        concurrencia_competitiva=competitiva,
        minimis=any(r.id == "minimis" for r in reqs),
        beneficiarios=beneficiarios, sectores=sectores,
        finalidad=d.get("descripcionFinalidad"),
        objetivos=_descs(d.get("objetivos")), fondos=_descs(d.get("fondos")),
        reglamento=reglamento,
        resumen=d.get("descripcionBasesReguladoras"),
        url_bases=d.get("urlBasesReguladoras"), sede=d.get("sedeElectronica"),
        url_bdns=url_publica(codigo),
        anuncios=[{**{k: a.get(k) for k in ("titulo", "url", "desDiarioOficial", "datPublicacion")},
                   "texto": (a.get("texto") or "")[:6000]}
                  for a in (d.get("anuncios") or []) if isinstance(a, dict)],
        documentos_bdns=[{k: x.get(k) for k in ("id", "descripcion", "nombreFic")}
                         for x in (d.get("documentos") or []) if isinstance(x, dict)],
        requisitos=reqs,
        documentos=["Solicitud en la sede electrónica del órgano convocante",
                    "Certificado de estar al corriente con la AEAT", "Certificado de estar al corriente con la TGSS",
                    "Memoria del proyecto y presupuesto"] + (["Declaración de ayudas de minimis"]
                                                            if any(r.id == "minimis" for r in reqs) else []),
        fuente="bdns",
    )


def abierta(c: Convocatoria, hoy: Optional[date] = None) -> bool:
    hoy = hoy or date.today()
    if c.fecha_fin:
        return c.fecha_fin >= hoy
    return bool(c.abierto)


def relevante(c: Convocatoria) -> bool:
    t = f"{c.titulo} {c.tipo_convocatoria or ''}".lower()
    if "nominativ" in t:  # concesión directa a un beneficiario concreto: nadie más puede pedirla
        return False
    return es_para_empresas(c.beneficiarios)


# --------------------------------------------------------------------------- almacén

def _leer(ruta: Path, defecto):
    if not ruta.exists():
        return defecto
    with gzip.open(ruta, "rt", encoding="utf-8") as f:
        return json.load(f)


def _escribir(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(ruta)


def cargar_catalogo() -> tuple[list[Convocatoria], dict]:
    datos = _leer(CATALOGO, None)
    if not datos:
        return [], {}
    return [Convocatoria(**c) for c in datos["convocatorias"]], datos.get("meta", {})


def sincronizar(dias: int = 60, max_detalles: int = 3000, hilos: int = 4,
                log: Callable[[str], None] = print) -> dict:
    """Sincronización incremental: solo pide el detalle de las convocatorias nuevas.

    Guarda en data/catalogo.json.gz las abiertas y relevantes para empresas, y en data/vistos.json.gz
    las descartadas (cerradas, nominativas o no dirigidas a empresas) para no volver a pedirlas.
    """
    hoy = date.today()
    previas, _ = cargar_catalogo()
    catalogo = {c.id: c for c in previas if abierta(c, hoy)}
    vistos: dict[str, str] = _leer(VISTOS, {})
    pendientes: list[str] = []
    listadas = 0
    for fila in listar_todo(hoy - timedelta(days=dias)):
        listadas += 1
        num = str(fila.get("numeroConvocatoria") or "")
        titulo = (fila.get("descripcion") or "").lower()
        if not num or num in vistos or num in catalogo:
            continue
        if "nominativ" in titulo:
            vistos[num] = "nominativa"
            continue
        pendientes.append(num)
    pendientes = pendientes[:max_detalles]
    log(f"{listadas} convocatorias listadas; {len(pendientes)} nuevas por consultar")

    def uno(num: str):
        try:
            time.sleep(0.15)
            return num, mapear(detalle(num))
        except Exception as e:  # noqa: BLE001
            return num, e

    nuevas = errores = 0
    with ThreadPoolExecutor(max_workers=hilos) as ex:
        for i, (num, res) in enumerate(ex.map(uno, pendientes), 1):
            if isinstance(res, Exception):
                errores += 1
                continue
            if relevante(res) and abierta(res, hoy):
                catalogo[num] = res
                nuevas += 1
            else:
                vistos[num] = "cerrada" if not abierta(res, hoy) else "no_empresas"
            if i % 200 == 0:
                log(f"  {i}/{len(pendientes)} consultadas")
    # recorta 'vistos' a lo reciente para que el archivo no crezca sin límite
    if len(vistos) > 60000:
        vistos = dict(sorted(vistos.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0)[-40000:])
    meta = {"actualizado": datetime.now().isoformat(timespec="seconds"), "abiertas": len(catalogo),
            "nuevas": nuevas, "errores": errores, "dias": dias}
    _escribir(CATALOGO, {"meta": meta, "convocatorias": [c.model_dump(mode="json") for c in catalogo.values()]})
    _escribir(VISTOS, vistos)
    log(f"Catálogo: {len(catalogo)} convocatorias abiertas para empresas ({nuevas} nuevas, {errores} errores)")
    return meta
