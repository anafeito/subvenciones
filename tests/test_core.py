"""Tests con respuestas que reproducen la estructura real de la API de la BDNS (nov. 2026)."""
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from core import bdns, bases
from core.elegibilidad import evaluar
from core.encaje import Indice
from core.models import Estado, Perfil
from core.motor import analizar
from core.perfil import desde_cif, validar_cif
from core.territorio import cubre, nuts_perfil

FIX = Path(__file__).parent / "fixtures"
DET = json.loads((FIX / "detalle_935315.json").read_text(encoding="utf-8"))


@pytest.fixture
def api_falsa(monkeypatch):
    """Sustituye la red por las respuestas de ejemplo."""
    def manejador(req: httpx.Request):
        p = req.url.path
        if p.endswith("/convocatorias/busqueda"):
            return httpx.Response(200, json=json.loads((FIX / "busqueda.json").read_text()))
        if p.endswith("/convocatorias"):
            d = dict(DET, fechaFinSolicitud="2099-12-31", abierto=True)
            return httpx.Response(200, json=d)
        if p.endswith("/concesiones/busqueda"):
            return httpx.Response(200, json=json.loads((FIX / "concesiones_nif.json").read_text()))
        if p.endswith("/minimis/busqueda"):
            return httpx.Response(200, json={"content": [{"fechaConcesion": str(date.today()), "ayudaEquivalente": 12000}]})
        return httpx.Response(404)
    monkeypatch.setattr(bdns, "_cliente", httpx.Client(base_url=bdns.BASE, transport=httpx.MockTransport(manejador)))
    yield


def test_mapeo_real():
    c = bdns.mapear(DET)
    assert c.codigo_bdns == "935315" and c.presupuesto_total == 1440000
    assert c.regiones == ["ES53"]
    assert c.concurrencia_competitiva is True
    assert c.fecha_fin == date(2026, 6, 28) and c.abierto is False
    ids = {r.id for r in c.requisitos}
    assert "territorio" in ids and "cnae" in ids and "pyme" not in ids  # pyme y gran empresa: sin límite de tamaño
    cn = next(r for r in c.requisitos if r.id == "cnae").valor
    assert "72" in cn and "382" in cn and "25" in cn  # 'C' se expande a 10-33
    assert bdns.relevante(c)
    assert not bdns.abierta(c, date(2026, 11, 3))


def test_territorio():
    assert nuts_perfil("Valencia", None) == "ES523"
    assert nuts_perfil(None, "Illes Balears") == "ES53"
    assert cubre(["ES53"], "ES53") is True
    assert cubre(["ES52"], "ES523") is True
    assert cubre(["ES523"], "ES52") is None
    assert cubre(["ES53"], "ES300") is False


def test_elegibilidad_territorial():
    c = bdns.mapear(DET)
    p = Perfil(provincia="Madrid", cnae="2562", al_corriente_hacienda=True, al_corriente_ss=True)
    est = {e.requisito.id: e.estado for e in evaluar(p, c.requisitos)}
    assert est["territorio"] == Estado.no_cumple and est["cnae"] == Estado.cumple
    p.provincia, p.comunidad = None, "Illes Balears"
    assert {e.requisito.id: e.estado for e in evaluar(p, c.requisitos)}["territorio"] == Estado.cumple


def test_no_empresas():
    assert not bdns.es_para_empresas(["PERSONAS FÍSICAS QUE NO DESARROLLAN ACTIVIDAD ECONÓMICA"])
    assert bdns.es_para_empresas(["PYME Y PERSONAS FÍSICAS QUE DESARROLLAN ACTIVIDAD ECONÓMICA"])


def test_cif():
    assert validar_cif("G26478453") and validar_cif("B96123450") and not validar_cif("B96123451")
    assert validar_cif("12345678Z")


def test_perfil_desde_cif(api_falsa):
    p, hist, avisos = desde_cif("G26478453")
    assert p.razon_social == "GRUPO LUX" and p.comunidad == "La Rioja"
    assert p.minimis_recibido_3_anios == 12000 and len(hist) == 1


def test_sincronizar(api_falsa, tmp_path, monkeypatch):
    monkeypatch.setattr(bdns, "CATALOGO", tmp_path / "c.json.gz")
    monkeypatch.setattr(bdns, "VISTOS", tmp_path / "v.json.gz")
    meta = bdns.sincronizar(dias=30, log=lambda *_: None)
    convs, m = bdns.cargar_catalogo()
    assert meta["abiertas"] == 1 and convs[0].id == "935315"   # la nominativa se descarta
    assert bdns._leer(bdns.VISTOS, {})["939617"] == "nominativa"


def test_ranking_encaje():
    c = bdns.mapear(dict(DET, fechaFinSolicitud="2099-12-31"))
    p = Perfil(comunidad="Illes Balears", cnae="3821", empleados=20, al_corriente_hacienda=True, al_corriente_ss=True,
               proyecto="Planta de valorización de residuos y economía circular con descarbonización")
    r = analizar(p, [c], Indice([c]))
    assert r and r[0].elegible and r[0].encaje.banda in ("alta", "media")


def test_heuristica_bases():
    t = bases._html_a_texto(DET["anuncios"][0]["texto"])
    d = bases.extraer_heuristico(t)
    assert d.get("importe_max") == 200000
