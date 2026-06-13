"""M1 Spine 跑(指定 out_dir)。用法: HIKI_SPINE=1 PYTHONPATH=src python scripts/m1_run.py <src> <out_dir>"""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.produce import run

asyncio.run(run(Path(sys.argv[1]), out_dir=Path(sys.argv[2])))
