"""Copiloto de subvenciones — app Streamlit.   streamlit run streamlit_app.py"""
from __future__ import annotations

import io
from datetime import date, datetime

import pandas as pd
import streamlit as st

from core import bases, bdns, demo, llm
from core.borrador import generar
from core.cnae import DIVISIONES, descripcion
from core.elegibilidad import evaluar
from core.encaje import Indice
from core.models import Estado, Perfil
from core.motor import analizar
from core.perfil import desde_cif, validar_cif
from core.territorio import COMUNIDADES, PROVINCIAS

st.set_page_config(page_title="Copiloto de subvenciones", page_icon="💶", layout="wide")

ICONO = {Estado.cumple: "✅", Estado.no_cumple: "❌", Estado.falta_dato: "❓", Estado.revisar: "🟣"}
ETQ = {Estado.cumple: "Cumple", Estado.no_cumple: "No cumple", Estado.falta_dato: "Falta dato", Estado.revisar: "Revisar"}
BANDA = {"alta": "🟢 Encaje alto", "media": "🟡 Encaje medio", "baja": "🔴 Encaje bajo"}


def eur(v) -> str:
    return "—" if v is None else f"{v:,.0f} €".replace(",", ".")


# --------------------------------------------------------------------------- catálogo

@st.cache_data(show_spinner=False)
def _catalogo_real(_mtime: float):
    convs, meta = bdns.cargar_catalogo()
    return convs, meta


@st.cache_resource(show_spinner=False)
def _indice(ids: tuple, _convs):
    return Indice(_convs)


def catalogo(usar_demo: bool):
    if usar_demo:
        convs, meta = demo.cargar(), {"actualizado": "catálogo de ejemplo", "abiertas": 11}
    else:
        mt = bdns.CATALOGO.stat().st_mtime if bdns.CATALOGO.exists() else 0.0
        convs, meta = _catalogo_real(mt)
    return convs, meta, _indice(tuple(c.id for c in convs), convs)


# --------------------------------------------------------------------------- barra lateral

with st.sidebar:
    st.title("💶 Copiloto de subvenciones")
    usar_demo = st.toggle("Usar catálogo de ejemplo", value=False,
                          help="Convocatorias ficticias para enseñar la app sin conexión.")
    convs, meta, indice = catalogo(usar_demo)
    if convs:
        st.success(f"**{len(convs)}** convocatorias abiertas para empresas")
        st.caption(f"Fuente: {'ejemplo' if usar_demo else 'BDNS'} · actualizado: {meta.get('actualizado', '—')}")
    else:
        st.warning("El catálogo está vacío. Descarga las convocatorias recientes de la BDNS.")
    with st.expander("Actualizar desde la BDNS"):
        dias = st.slider("Convocatorias registradas en los últimos… (días)", 3, 90, 14)
        maximo = st.number_input("Máximo de fichas a consultar", 50, 5000, 600, step=50,
                                 help="Cada ficha es una petición a la BDNS. La actualización diaria completa la hace "
                                      "la acción de GitHub (ver README).")
        if st.button("Actualizar ahora", width="stretch", disabled=usar_demo):
            caja = st.empty()
            with st.spinner("Consultando la BDNS…"):
                try:
                    m = bdns.sincronizar(dias=dias, max_detalles=int(maximo), log=lambda s: caja.caption(s))
                    st.success(f"Listo: {m['abiertas']} abiertas ({m['nuevas']} nuevas).")
                    _catalogo_real.clear()
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(f"No se pudo consultar la BDNS: {e}")
    st.divider()
    if llm.disponible():
        st.caption(f"🤖 IA activada: `{llm.modelo()}`")
    else:
        st.caption("🤖 IA desactivada: memorias con plantilla. Añade una clave gratuita de Groq o Gemini en "
                   "*Secrets* para activarla (ver README).")
    st.caption("Datos: [BDNS / SNPSAP](https://www.infosubvenciones.es) · La herramienta prepara; "
               "la gestoría revisa y presenta.")


# --------------------------------------------------------------------------- estado

ss = st.session_state
ss.setdefault("perfil", Perfil())
ss.setdefault("historial", [])
ss.setdefault("enriquecidas", {})   # id -> Convocatoria con bases leídas
ss.setdefault("memorias", {})

tab_buscar, tab_cartera = st.tabs(["🔎 Buscar ayudas para una empresa", "🗂️ Cartera de la gestoría"])


def formulario_perfil(p: Perfil) -> Perfil:
    provs = [""] + sorted(PROVINCIAS)
    cnaes = [""] + [f"{k} - {v}" for k, v in DIVISIONES.items()]
    with st.form("form_perfil"):
        c1, c2, c3 = st.columns(3)
        razon = c1.text_input("Razón social", p.razon_social or "")
        prov = c2.selectbox("Provincia", provs, index=provs.index(p.provincia) if p.provincia in provs else 0)
        com_def = PROVINCIAS[prov][1] if prov else (p.comunidad or "")
        coms = [""] + list(COMUNIDADES)
        com = c3.selectbox("Comunidad autónoma", coms, index=coms.index(com_def) if com_def in coms else 0)
        c1, c2, c3 = st.columns(3)
        cn_idx = next((i for i, x in enumerate(cnaes) if p.cnae and x.startswith(p.cnae[:2])), 0)
        cn_sel = c1.selectbox("Actividad (CNAE, división)", cnaes, index=cn_idx)
        cn4 = c2.text_input("CNAE a 4 dígitos (opcional)", p.cnae if p.cnae and len(p.cnae) > 2 else "")
        fc = c3.date_input("Fecha de constitución", p.fecha_constitucion, min_value=date(1900, 1, 1),
                           max_value=date.today(), format="DD/MM/YYYY")
        c1, c2, c3, c4 = st.columns(4)
        emp = c1.number_input("Empleados", 0, 100000, p.empleados or 0)
        fac = c2.number_input("Facturación anual (€)", 0, 10**10, int(p.facturacion or 0), step=10000)
        inv = c3.number_input("Inversión prevista (€)", 0, 10**9, int(p.inversion_prevista or 0), step=1000)
        mm = c4.number_input("De minimis recibido 3 años (€)", 0, 10**8, int(p.minimis_recibido_3_anios or 0),
                             step=1000, help="Se rellena solo con la BDNS al consultar el CIF.")
        c1, c2 = st.columns(2)
        op = ["Sí", "No", "No lo sé"]
        hac = c1.radio("¿Al corriente con Hacienda?", op, horizontal=True,
                       index={True: 0, False: 1, None: 2}[p.al_corriente_hacienda])
        seg = c2.radio("¿Al corriente con la Seguridad Social?", op, horizontal=True,
                       index={True: 0, False: 1, None: 2}[p.al_corriente_ss])
        proy = st.text_area("¿Qué quiere financiar? (cuanto más concreto, mejor encaje)", p.proyecto or "",
                            placeholder="Ej.: digitalizar la planta con un ERP de producción y sensores en las máquinas")
        enviado = st.form_submit_button("Buscar ayudas", type="primary", width="stretch")
    if enviado:
        a_bool = {"Sí": True, "No": False, "No lo sé": None}
        cnae_v = cn4.strip() or (cn_sel[:2] if cn_sel else None)
        p = p.model_copy(update=dict(
            razon_social=razon or None, provincia=prov or None, comunidad=com or None, cnae=cnae_v,
            fecha_constitucion=fc, empleados=int(emp) if emp else None, facturacion=float(fac) if fac else None,
            inversion_prevista=float(inv) if inv else None, minimis_recibido_3_anios=float(mm),
            al_corriente_hacienda=a_bool[hac], al_corriente_ss=a_bool[seg], proyecto=proy or None))
        ss["perfil"], ss["buscar"] = p, True
    return p


def tarjeta(r, i: int):
    c = ss["enriquecidas"].get(r.convocatoria.id, r.convocatoria)
    dias = r.dias_restantes
    plazo = f"⏰ **cierra en {dias} días**" if dias is not None and dias <= 10 else \
        (f"cierra en {dias} días" if dias is not None else "plazo abierto (ver convocatoria)")
    with st.container(border=True):
        a, b = st.columns([4, 1])
        a.markdown(f"**{c.titulo}**")
        a.caption(" · ".join(x for x in (c.organo, c.nivel1, plazo) if x))
        b.markdown(f"**{BANDA[r.encaje.banda]}**")
        b.caption(f"Presupuesto: {eur(c.presupuesto_total)}")
        with st.expander("Ver requisitos, encaje y preparar la solicitud"):
            evals = evaluar(ss["perfil"], c.requisitos)
            filas = [{"": ICONO[e.estado], "Estado": ETQ[e.estado], "Requisito": e.requisito.texto,
                      "Detalle": e.explicacion} for e in evals]
            st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
            st.markdown("**Por qué este encaje:** " + "; ".join(r.encaje.factores) + ".")
            datos = []
            if c.importe_max:
                datos.append(f"importe máx. {eur(c.importe_max)}")
            if c.intensidad:
                datos.append(f"intensidad {c.intensidad:g} %")
            if c.tipo_convocatoria:
                datos.append(c.tipo_convocatoria)
            if c.finalidad:
                datos.append(f"finalidad: {c.finalidad}")
            if datos:
                st.caption(" · ".join(datos))
            if c.texto_plazo:
                st.caption(f"Plazo según la convocatoria: {c.texto_plazo[:300]}")
            if c.criterios_valoracion:
                st.markdown("**Criterios de valoración:** " + "; ".join(c.criterios_valoracion))
            enlaces = [f"[Ficha BDNS]({c.url_bdns})" if c.url_bdns else "",
                       f"[Bases reguladoras]({c.url_bases})" if c.url_bases else "",
                       f"[Sede electrónica]({c.sede})" if c.sede else ""]
            st.markdown(" · ".join(x for x in enlaces if x))
            k1, k2 = st.columns(2)
            if k1.button("📄 Leer las bases y extraer requisitos", key=f"b{i}{c.id}", width="stretch",
                         disabled=c.fuente != "bdns"):
                with st.spinner("Descargando y leyendo las bases…"):
                    nueva, info = bases.enriquecer(c)
                ss["enriquecidas"][c.id] = nueva
                if info["metodo"] == "sin texto":
                    st.warning("No se pudo leer el texto de las bases (puede ser un PDF escaneado o una web que "
                               "bloquea descargas). Ábrelas desde el enlace.")
                else:
                    st.success(f"Bases leídas con {info['metodo']}: {info.get('requisitos_nuevos', 0)} requisitos "
                               f"nuevos. Fuentes: {', '.join(info['fuentes'])}")
                st.rerun()
            if k2.button("✍️ Preparar borrador de memoria", key=f"m{i}{c.id}", type="primary",
                         width="stretch"):
                texto = st.write_stream(generar(ss["perfil"], c, evals))
                ss["memorias"][c.id] = texto
            if c.id in ss["memorias"]:
                st.download_button("Descargar memoria (.md)", ss["memorias"][c.id], file_name=f"memoria_{c.id}.md",
                                   key=f"d{i}{c.id}")


# --------------------------------------------------------------------------- pestaña: empresa

with tab_buscar:
    st.subheader("1. Empresa")
    c1, c2 = st.columns([3, 1])
    cif = c1.text_input("CIF / NIF", ss["perfil"].cif or "", placeholder="B12345678",
                        label_visibility="collapsed").strip().upper()
    if c2.button("Consultar en la BDNS", width="stretch", disabled=not cif or usar_demo):
        with st.spinner("Buscando ayudas recibidas y de minimis…"):
            p, hist, avisos = desde_cif(cif)
        ss["perfil"], ss["historial"] = p, hist
        for a in avisos:
            st.info(a)
    elif cif and not validar_cif(cif):
        st.caption("⚠️ El CIF no parece válido.")
    if ss["historial"]:
        h = pd.DataFrame([{"Fecha": x.get("fechaConcesion"), "Convocatoria": x.get("convocatoria"),
                           "Órgano": x.get("nivel3"), "Importe (€)": x.get("importe")} for x in ss["historial"]])
        with st.expander(f"Ayudas ya recibidas por esta empresa según la BDNS ({len(h)})"):
            st.dataframe(h, hide_index=True, width="stretch")
    perfil = formulario_perfil(ss["perfil"])

    if ss.get("buscar") and convs:
        st.subheader("2. Ayudas abiertas que encajan")
        res = analizar(perfil, convs, indice, ss["historial"])
        f1, f2, f3 = st.columns(3)
        solo = f1.toggle("Solo las que cumple o le falta algún dato", value=True)
        niveles = sorted({r.convocatoria.nivel1 for r in res if r.convocatoria.nivel1})
        nivel = f2.multiselect("Administración", niveles, default=niveles)
        n = f3.slider("Cuántas mostrar", 5, 50, 10)
        filtr = [r for r in res if (r.elegible or not solo) and (not niveles or r.convocatoria.nivel1 in nivel)]
        eleg = [r for r in res if r.elegible]
        k1, k2, k3 = st.columns(3)
        k1.metric("Convocatorias abiertas analizadas", len(res))
        k2.metric("Encajan con la empresa", len(eleg))
        k3.metric("Presupuesto conjunto de las 10 primeras", eur(sum(r.convocatoria.presupuesto_total or 0
                                                                     for r in eleg[:10])))
        if not filtr:
            st.info("No hay convocatorias abiertas que encajen. Prueba a completar el perfil o a quitar filtros.")
        for i, r in enumerate(filtr[:n]):
            tarjeta(r, i)
    elif not convs:
        st.info("Primero carga el catálogo (barra lateral).")


# --------------------------------------------------------------------------- pestaña: cartera

COLUMNAS = ["cif", "razon_social", "provincia", "comunidad", "cnae", "empleados", "facturacion",
            "fecha_constitucion", "proyecto", "inversion_prevista", "al_corriente_hacienda", "al_corriente_ss"]

with tab_cartera:
    st.subheader("Radar de toda la cartera")
    st.caption("Sube un CSV con tus clientes y verás de golpe qué ayudas abiertas encajan con cada uno.")
    plantilla = pd.DataFrame([{"cif": "B96123450", "razon_social": "Ejemplo SL", "provincia": "Valencia/València",
                               "comunidad": "Comunitat Valenciana", "cnae": "2562", "empleados": 12,
                               "facturacion": 1450000, "fecha_constitucion": "2009-03-12",
                               "proyecto": "ERP de producción y sensores en maquinaria", "inversion_prevista": 85000,
                               "al_corriente_hacienda": True, "al_corriente_ss": True}], columns=COLUMNAS)
    st.download_button("Descargar plantilla CSV", plantilla.to_csv(index=False), "plantilla_clientes.csv")
    subido = st.file_uploader("CSV de clientes", type="csv")
    if subido and convs:
        df = pd.read_csv(subido, dtype={"cif": str, "cnae": str})
        filas = []
        barra = st.progress(0.0)
        for j, fila in enumerate(df.to_dict("records")):
            datos = {k: (None if pd.isna(v) else v) for k, v in fila.items() if k in COLUMNAS}
            if datos.get("fecha_constitucion"):
                datos["fecha_constitucion"] = pd.to_datetime(datos["fecha_constitucion"]).date()
            p = Perfil(**datos)
            rs = [r for r in analizar(p, convs, indice) if r.elegible]
            top = rs[0] if rs else None
            urg = min((r.dias_restantes for r in rs[:10] if r.dias_restantes is not None), default=None)
            filas.append({"Cliente": p.razon_social or p.cif, "CIF": p.cif, "Ayudas que encajan": len(rs),
                          "Encaje alto": sum(r.encaje.banda == "alta" for r in rs),
                          "Mejor oportunidad": top.convocatoria.titulo if top else "—",
                          "BDNS": top.convocatoria.codigo_bdns if top else "",
                          "Cierre más próximo (días)": urg})
            barra.progress((j + 1) / len(df))
        tabla = pd.DataFrame(filas).sort_values(["Encaje alto", "Ayudas que encajan"], ascending=False)
        k1, k2, k3 = st.columns(3)
        k1.metric("Clientes", len(tabla))
        k2.metric("Oportunidades con encaje alto", int(tabla["Encaje alto"].sum()))
        k3.metric("Clientes con alguna ayuda", int((tabla["Ayudas que encajan"] > 0).sum()))
        st.dataframe(tabla, hide_index=True, width="stretch")
        st.download_button("Descargar informe (CSV)", tabla.to_csv(index=False),
                           f"radar_ayudas_{datetime.now():%Y%m%d}.csv")
