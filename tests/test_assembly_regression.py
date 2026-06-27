"""E2.1 装配层回归网: fact_table.json 信号计数 ↔ Tier-A 金标夹具一致性。零 API, CI-safe。"""
import json
import pytest
from pathlib import Path
from hiki.prose_facts import signal_counts_from_fact_table

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "assets" / "gold_regression"

SLUGS = [
    "BPBXS00052", "CPBGX00031", "CPBGX00056", "CPBGX00192",
    "CPBXN00188", "ZYGGY02079", "ZYGGY02252",
]


def test_fact_table_count():
    fts = list(GOLD.glob("*/fact_table.json"))
    assert len(fts) >= 7, f"Expected ≥7 fact_table.json, got {len(fts)}"


@pytest.mark.parametrize("slug", SLUGS)
def test_assembly_counts_match_fixture(slug):
    ft_path = GOLD / slug / "fact_table.json"
    fx_path = GOLD / slug / "fixture.json"
    ft = json.loads(ft_path.read_text(encoding="utf-8"))
    fx = json.loads(fx_path.read_text(encoding="utf-8"))
    counts = signal_counts_from_fact_table(ft)
    sv = fx["signals"]
    assert counts["spine_num_contra"] == sv["spine_num_contra"], \
        f"{slug}: spine_num_contra {counts['spine_num_contra']} != {sv['spine_num_contra']}"
    assert counts["spine_id_contra"] == sv.get("spine_id_contra", 0), \
        f"{slug}: spine_id_contra {counts['spine_id_contra']} != {sv.get('spine_id_contra', 0)}"
    assert counts["ft_revival_residual"] == sv["ft_revival_residual"], \
        f"{slug}: ft_revival_residual {counts['ft_revival_residual']} != {sv['ft_revival_residual']}"
