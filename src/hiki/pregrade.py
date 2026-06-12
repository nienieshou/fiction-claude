"""源池预分级：只跑 深挖+分级（人物弧判据+暗黑预扫），不生产。~¥1/本。

用途：起批前一次性绘制全池地图（grade/人物弧/暗黑/题材），小步迭代轮次从已知 A 池
按题材抽源，不浪费轮次配额在被拒源上。跳过 score_scenes（分级用不到，省一调用）。
用法: python -m hiki.pregrade <源目录或多个.txt> [--parallel 8] [--chunks 12]
产出: output/pregrade_map.{json,md}
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from . import mining
from .client import Client
from .ingest import ingest


async def _grade_one(sem: asyncio.Semaphore, src: Path, n_chunks: int) -> dict:
    async with sem:
        t0 = time.time()
        cli = Client(flash_concurrency=64, pro_concurrency=16)   # 每本独立计费
        try:
            out_dir = Path("output") / "_pregrade" / src.stem
            meta = ingest(src, out_dir / "source")
            clean = (out_dir / "source" / "clean.txt").read_text(encoding="utf-8")
            chunks = mining.chunk_by_chapters(clean, n_chunks=n_chunks)
            results, dark = await asyncio.gather(
                mining.map_extract(cli, chunks), mining.dark_prescan(cli, clean))
            all_scenes = mining.merge_scenes(results)
            bible = await mining.reduce_bible(cli, results, all_scenes)
            if not mining._bible_ok(bible):
                return {"src": src.name, "ok": False, "error": "REDUCE失败(厚bible无效,flaky请重跑)",
                        "cost_cny": round(cli.cost_cny, 2), "seconds": round(time.time() - t0, 1)}
            g = await mining.grade_source(cli, bible, dark=dark)
            p = bible.get("protagonist", {})
            row = {"src": src.name, "ok": True, "wan_zi": meta.approx_wan_zi,
                   "grade": g.get("grade"), "mode": g.get("mode"),
                   "protagonist_arc": g.get("protagonist_arc", "?"),
                   "dark_ratio": g.get("source_dark_ratio", 0.0),
                   "content_flag": g.get("content_flag", "无"),
                   "voice": bible.get("voice", ""), "主角": f"{p.get('name','')}({p.get('gender','')})",
                   "central_conflict": (bible.get("central_conflict") or "")[:60],
                   "risk": g.get("risk", ""), "focus": g.get("focus", ""),
                   "reason": g.get("reason", ""), "scenes": len(all_scenes),
                   "cost_cny": round(cli.cost_cny, 2), "seconds": round(time.time() - t0, 1)}
            print(f"  {g.get('grade')}/{g.get('protagonist_arc','?')[:2]} 暗黑{g.get('source_dark_ratio',0)} "
                  f"¥{cli.cost_cny:.2f} {src.name[:30]}")
            return row
        except Exception as e:
            return {"src": src.name, "ok": False, "error": f"{type(e).__name__}: {e}"[:160],
                    "cost_cny": round(cli.cost_cny, 2), "seconds": round(time.time() - t0, 1)}


def _collect(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        pa = Path(p)
        if pa.is_dir():
            out += sorted(pa.glob("*.txt"))
        elif pa.suffix.lower() == ".txt":
            out.append(pa)
    return out


async def run_pool(srcs: list[Path], parallel: int, n_chunks: int) -> list[dict]:
    sem = asyncio.Semaphore(parallel)
    return await asyncio.gather(*[_grade_one(sem, s, n_chunks) for s in srcs])


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="hiki.pregrade")
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--parallel", type=int, default=8)
    ap.add_argument("--chunks", type=int, default=12)
    a = ap.parse_args()
    srcs = _collect(a.sources)
    if not srcs:
        print("未找到 .txt 源"); return
    print(f"预分级: {len(srcs)} 本，并行 {a.parallel} ...")
    t0 = time.time()
    rows = asyncio.run(run_pool(srcs, a.parallel, a.chunks))
    wall = round(time.time() - t0, 1)

    ok = [r for r in rows if r.get("ok")]
    fail = [r for r in rows if not r.get("ok")]
    cost = round(sum(r.get("cost_cny", 0) or 0 for r in rows), 2)
    order = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4, "Q": 5}
    ok.sort(key=lambda r: (order.get(r.get("grade"), 9), -(r.get("wan_zi") or 0)))
    dist = {}
    for r in ok:
        dist[r["grade"]] = dist.get(r["grade"], 0) + 1
    summary = {"本数": len(srcs), "成功": len(ok), "失败": len(fail),
               "分布": dist, "总成本_cny": cost, "墙钟_秒": wall, "rows": ok + fail}
    out_dir = Path("output"); out_dir.mkdir(exist_ok=True)
    (out_dir / "pregrade_map.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# 源池预分级地图  {len(srcs)}本  墙钟{wall}s  总¥{cost}",
             "分布: " + "、".join(f"{g}×{n}" for g, n in sorted(dist.items(), key=lambda kv: order.get(kv[0], 9))), "",
             "| 源 | 档 | 主角弧 | 暗黑 | 题材语域 | 主角 | 风险 | 理由 | ¥ |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in ok:
        lines.append(f"| {r['src'][:26]} | **{r['grade']}** | {r['protagonist_arc'][:6]} | "
                     f"{r['dark_ratio']} | {r['voice'][:14]} | {r['主角']} | {r['risk'][:14]} | "
                     f"{r['reason'][:24]} | {r['cost_cny']} |")
    for r in fail:
        lines.append(f"| {r['src'][:26]} | 失败 | | | | | | {r.get('error','')[:30]} | {r.get('cost_cny')} |")
    (out_dir / "pregrade_map.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n分布: {dist} | 总¥{cost} | 墙钟{wall}s")
    print("地图 → output/pregrade_map.md")


if __name__ == "__main__":
    main()
