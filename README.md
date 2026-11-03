# Copiloto de subvenciones

Introduces el CIF de una empresa y la app te enseña qué convocatorias **abiertas hoy en la BDNS** puede pedir. Para cada una verás:

- los requisitos, marcados como cumple / no cumple / falta dato;
- por qué encaja con la empresa;
- un botón para leer las bases y extraer requisitos, importe y criterios de valoración;
- un borrador de la memoria técnica.

Además, una gestoría puede subir su cartera de clientes en un CSV y obtener el radar de todos.

**Funciona con datos reales y gratis.** La BDNS es pública y no pide clave, Streamlit Community Cloud y GitHub Actions no cuestan nada, y la IA es opcional y también gratuita (Groq o Gemini).

## Qué es real y qué no

| Parte | Fuente | Estado |
| --- | --- | --- |
| Convocatorias abiertas | API pública de la BDNS (`/convocatorias/busqueda` + `/convocatorias`) | Real, con actualización diaria |
| Ámbito territorial, sector CNAE, tipo de beneficiario, plazo, presupuesto | Ficha de la BDNS | Real |
| Razón social y ayudas ya recibidas por el CIF | `/concesiones/busqueda?nifCif=` | Real |
| Ayudas *de minimis* de los últimos 3 años (tope de 300.000 €) | `/minimis/busqueda?nifCif=` | Real |
| Importe por beneficiario, intensidad, criterios de valoración y requisitos finos | Texto de las bases (anuncio + URL de las bases) leído con IA o heurísticas | Real, pero hay que revisarlo |
| Plantilla, facturación, CNAE y proyecto | Los declara la empresa o la gestoría | Declarado |
| Encaje (alto / medio / bajo) | Similitud de texto + requisitos cumplidos + historial + tipo de procedimiento | Orientativo; no es una probabilidad de concesión |

No existe ningún dato público de solicitudes denegadas, así que la app no muestra una "probabilidad de concesión". Mostrarla sería inventarla.

## Desplegar en Streamlit Community Cloud (unos 15 minutos)

1. **Sube el código a GitHub.** Crea un repositorio, público o privado, con el contenido de esta carpeta.
   ```bash
   git init && git add . && git commit -m "Copiloto de subvenciones"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO/copiloto-subvenciones.git
   git push -u origin main
   ```
2. **Llena el catálogo por primera vez.** En GitHub, ve a **Actions → Sincronizar BDNS → Run workflow**. La primera vez descarga unos 60 días de convocatorias y tarda entre 20 y 60 minutos. Después se ejecuta sola cada día y solo pide las convocatorias nuevas.
   - Si Actions no puede escribir en el repositorio, ve a **Settings → Actions → General → Workflow permissions** y marca **Read and write permissions**.
3. **Despliega la app.** Entra en https://share.streamlit.io, pulsa **Create app** y elige tu repositorio, la rama `main` y el archivo `streamlit_app.py`. Pulsa **Deploy**.
4. **Activa la IA (opcional y gratis).** Saca una clave en https://console.groq.com/keys. Después ve a **App settings → Secrets** y pega esto:
   ```toml
   LLM_BASE_URL = "https://api.groq.com/openai/v1"
   LLM_MODEL = "llama-3.3-70b-versatile"
   LLM_API_KEY = "gsk_..."
   ```
   Con Gemini sería igual; mira `.streamlit/secrets.toml.example`. Si el modelo deja de existir, cambia `LLM_MODEL` por otro de la lista del proveedor.

Cada vez que la acción diaria guarda el catálogo, Streamlit Cloud actualiza la app sola.

> Si todavía no has ejecutado la acción, la app arranca con el catálogo vacío. Puedes usar **Actualizar ahora** en la barra lateral: descarga los últimos días y tarda unos minutos. También puedes activar **Usar catálogo de ejemplo** para enseñarla sin conexión.

### Otras opciones de alojamiento

- **Hugging Face Spaces:** crea un Space de tipo *Streamlit* y sube el repositorio. Las claves van en *Settings → Secrets* como variables de entorno.
- **Tu propio servidor o Render:** `pip install -r requirements.txt && streamlit run streamlit_app.py --server.port $PORT`. Programa `python scripts/sync_bdns.py` con cron una vez al día.

## Ejecutar en local

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python scripts/sync_bdns.py --dias 14 --max 800        # descarga convocatorias reales (unos minutos)
streamlit run streamlit_app.py
pytest -q
```

## Cómo funciona

```
core/
  bdns.py         cliente de la BDNS: listado, detalle, concesiones y minimis por CIF; mapeo a modelo;
                  sincronización incremental (catalogo.json.gz + vistos.json.gz)
  perfil.py       validación de CIF/NIF/NIE y perfil desde la BDNS
  territorio.py   comunidades y provincias con su código NUTS (el que usa la BDNS)
  cnae.py         divisiones CNAE y expansión de secciones (C -> 10..33)
  elegibilidad.py motor determinista con cita: cumple / no cumple / falta dato / revisar
  encaje.py       índice TF-IDF del catálogo y puntuación explicable
  motor.py        orquesta y ordena
  bases.py        descarga las bases (HTML/PDF) y extrae requisitos con IA o heurísticas
  borrador.py     memoria técnica en streaming (IA) o con plantilla
  llm.py          cliente compatible con OpenAI (Groq, Gemini, Ollama)
streamlit_app.py  interfaz
scripts/sync_bdns.py              sincronización (la usa la acción diaria)
.github/workflows/sync-bdns.yml   acción diaria de GitHub
```

**Filtros del catálogo:** solo convocatorias con plazo abierto y dirigidas a empresas o autónomos (tipos de beneficiario "PYME…", "GRAN EMPRESA" o "…que desarrollan actividad económica"). Se descartan las subvenciones nominativas.

**Buen uso de la BDNS:** la API pide que no se hagan sondeos intensivos. La sincronización es incremental, usa 4 hilos con pausas y guarda lo ya consultado para no repetir peticiones. Los datos de la BDNS tienen [condiciones de reutilización](https://www.infosubvenciones.es) que conviene leer.

## Limitaciones

- **Ficha de la BDNS:** muchas convocatorias no traen ni importe por beneficiario ni criterios en la ficha. Para eso está el botón **Leer las bases**. Algunas webs de boletines bloquean descargas o publican PDF escaneados; en esos casos se abre el enlace.
- **Requisitos que extrae la IA:** son una ayuda, no un dictamen. La app siempre cita la fuente y deja a la persona la revisión y la presentación.
- **Cartera de la gestoría:** se procesa en la sesión y no se guarda en ningún servidor. Para guardar clientes y expedientes haría falta una base de datos (Supabase y Neon tienen capa gratuita).
