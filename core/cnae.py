"""Divisiones CNAE-2009 (2 dígitos), para describir la actividad y mejorar el encaje de texto."""

DIVISIONES = {
    "01": "Agricultura, ganadería, caza", "02": "Silvicultura y explotación forestal", "03": "Pesca y acuicultura",
    "05": "Extracción de antracita, hulla y lignito", "06": "Extracción de crudo y gas natural",
    "07": "Extracción de minerales metálicos", "08": "Otras industrias extractivas",
    "09": "Actividades de apoyo a las industrias extractivas", "10": "Industria de la alimentación",
    "11": "Fabricación de bebidas", "12": "Industria del tabaco", "13": "Industria textil",
    "14": "Confección de prendas de vestir", "15": "Industria del cuero y del calzado",
    "16": "Industria de la madera y del corcho", "17": "Industria del papel", "18": "Artes gráficas",
    "19": "Coquerías y refino de petróleo", "20": "Industria química", "21": "Fabricación de productos farmacéuticos",
    "22": "Fabricación de productos de caucho y plásticos", "23": "Fabricación de otros productos minerales no metálicos",
    "24": "Metalurgia", "25": "Fabricación de productos metálicos", "26": "Fabricación de productos informáticos y electrónicos",
    "27": "Fabricación de material y equipo eléctrico", "28": "Fabricación de maquinaria y equipo",
    "29": "Fabricación de vehículos de motor", "30": "Fabricación de otro material de transporte",
    "31": "Fabricación de muebles", "32": "Otras industrias manufactureras",
    "33": "Reparación e instalación de maquinaria y equipo", "35": "Suministro de energía eléctrica, gas, vapor",
    "36": "Captación, depuración y distribución de agua", "37": "Recogida y tratamiento de aguas residuales",
    "38": "Recogida, tratamiento y eliminación de residuos; valorización",
    "39": "Descontaminación y gestión de residuos", "41": "Construcción de edificios", "42": "Ingeniería civil",
    "43": "Actividades de construcción especializada", "45": "Venta y reparación de vehículos de motor",
    "46": "Comercio al por mayor", "47": "Comercio al por menor", "49": "Transporte terrestre",
    "50": "Transporte marítimo", "51": "Transporte aéreo", "52": "Almacenamiento y actividades anexas al transporte",
    "53": "Actividades postales y de correos", "55": "Servicios de alojamiento", "56": "Servicios de comidas y bebidas, hostelería",
    "58": "Edición", "59": "Actividades cinematográficas, de vídeo y televisión; música",
    "60": "Programación y emisión de radio y televisión", "61": "Telecomunicaciones",
    "62": "Programación, consultoría informática y software", "63": "Servicios de información",
    "64": "Servicios financieros", "65": "Seguros", "66": "Actividades auxiliares a los servicios financieros",
    "68": "Actividades inmobiliarias", "69": "Actividades jurídicas y de contabilidad",
    "70": "Actividades de las sedes centrales; consultoría de gestión", "71": "Servicios técnicos de arquitectura e ingeniería",
    "72": "Investigación y desarrollo", "73": "Publicidad y estudios de mercado",
    "74": "Otras actividades profesionales, científicas y técnicas", "75": "Actividades veterinarias",
    "77": "Actividades de alquiler", "78": "Actividades relacionadas con el empleo",
    "79": "Agencias de viajes y operadores turísticos", "80": "Actividades de seguridad e investigación",
    "81": "Servicios a edificios y actividades de jardinería", "82": "Actividades administrativas de oficina",
    "84": "Administración pública", "85": "Educación", "86": "Actividades sanitarias",
    "87": "Asistencia en establecimientos residenciales", "88": "Servicios sociales sin alojamiento",
    "90": "Actividades de creación, artísticas y espectáculos", "91": "Bibliotecas, archivos, museos",
    "92": "Actividades de juegos de azar", "93": "Actividades deportivas, recreativas y de entretenimiento",
    "94": "Actividades asociativas", "95": "Reparación de ordenadores y artículos personales",
    "96": "Otros servicios personales", "97": "Hogares como empleadores", "99": "Organismos extraterritoriales",
}

# Secciones (letras) -> divisiones, por si la BDNS usa la letra como código de sector.
SECCIONES = {
    "A": range(1, 4), "B": range(5, 10), "C": range(10, 34), "D": [35], "E": range(36, 40), "F": range(41, 44),
    "G": range(45, 48), "H": range(49, 54), "I": [55, 56], "J": range(58, 64), "K": range(64, 67), "L": [68],
    "M": range(69, 76), "N": range(77, 83), "O": [84], "P": [85], "Q": range(86, 89), "R": range(90, 94),
    "S": range(94, 97), "T": [97, 98], "U": [99],
}


def normalizar(codigo: str) -> list[str]:
    """'38.2' -> ['382'];  'C' -> ['10', ..., '33'];  '0111' -> ['0111']."""
    c = (codigo or "").strip().upper().replace(".", "")
    if c in SECCIONES:
        return [f"{d:02d}" for d in SECCIONES[c]]
    return [c] if c.isdigit() else []


def descripcion(cnae: str | None) -> str:
    return DIVISIONES.get((cnae or "")[:2], "")
