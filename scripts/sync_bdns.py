"""Sincroniza el catálogo con la BDNS (lo ejecuta la acción diaria de GitHub).

Uso:  python scripts/sync_bdns.py --dias 60 --max 4000
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.bdns import sincronizar  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--dias", type=int, default=60, help="convocatorias registradas en los últimos N días")
ap.add_argument("--max", type=int, default=4000, help="máximo de fichas de detalle a pedir en esta ejecución")
ap.add_argument("--hilos", type=int, default=4)
a = ap.parse_args()
meta = sincronizar(a.dias, a.max, a.hilos)
print(meta)
