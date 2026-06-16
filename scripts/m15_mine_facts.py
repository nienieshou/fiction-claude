"""M1.5 ② 廉价门: 只跑 mining,验证 bible.facts 是否把设定数值归并成单值(冲突已裁)。
用法: PYTHONPATH=src python scripts/m15_mine_facts.py <src.txt>"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.client import Client
from hiki import mining


async def main():
    src = Path(sys.argv[1])
    clean = src.read_text(encoding="utf-8")
    cli = Client()
    chunks = mining.chunk_by_chapters(clean, n_chunks=12)
    results = await mining.map_extract(cli, chunks)
    print(f"窗={len(chunks)}  各窗设定数值观察(归并前):")
    print(mining.collect_facts(results))
    bible = await mining.reduce_bible(cli, results, mining.merge_scenes(results))
    facts = bible.get("facts") or []
    print(f"\n=== REDUCE 后 bible.facts(冻结单值) {len(facts)} 项 ===")
    for f in facts:
        if isinstance(f, dict):
            print(f"  {f.get('item')} = {f.get('value')}"
                  + (f"  〔{f.get('rule')}〕" if f.get('rule') else ""))
    Path("output/m15_facts.json").write_text(
        json.dumps({"fact_obs": mining.collect_facts(results), "facts": facts},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n¥{cli.cost_cny:.2f}  → output/m15_facts.json")


if __name__ == "__main__":
    asyncio.run(main())
