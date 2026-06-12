"""批量产线：多本源**并行**跑 produce.run，压缩生产周期。

I/O-bound（瓶颈=DeepSeek 账号并发上限 ~2500flash/500pro，非 CPU/线程/内存）。
故"提速"=①每本内部高并发(Client 384flash/110pro) ②**多本并行**(本批=外层并发上限)。
外层 4 本并行时总并发 4×110=440pro / 4×384=1536flash，均安全在账号上限内。
单本失败/拒收不影响其余。汇总产出 batch_summary.{json,md}。

用法: python -m hiki.batch <源目录或多个.txt> [--parallel 4] [--chapters 60] [-n 3]
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from .produce import run

_KEYS = ("title", "grade", "out_chapters", "final_chars", "spotlight_variety",
         "暗黑比", "values_reject(暗黑饱和应拒)", "套话门_重写章数", "章缝_检出", "章缝_修复",
         "deliverable", "交付门", "final_consistent", "cost_cny", "seconds")


async def _one(sem: asyncio.Semaphore, src: Path, n_ch: int, n_chunks: int,
               n_cand: int, refine: int, min_grade: str | None = None) -> dict:
    async with sem:                                   # 外层限并行本数(账号上限内)
        t0 = time.time()
        try:
            rep = await run(src, n_ch, n_chunks, n_cand, refine, min_grade=min_grade)
            out = {"src": src.name, "ok": True}
            for k in _KEYS:
                if k in rep:
                    out[k] = rep[k]
            g = rep.get("grade") or {}
            out["grade"] = g.get("grade") if isinstance(g, dict) else g
            out["rejected"] = bool(rep.get("rejected") or rep.get("values_reject(暗黑饱和应拒)")
                                   or rep.get("deliverable") is False)   # 交付门拦下=不可交付
            return out
        except Exception as e:
            import traceback
            (Path("output") / f"_crash_{src.stem[:24]}.txt").write_text(
                traceback.format_exc(), encoding="utf-8")     # 完整traceback落盘(崩点定位两次靠猜的教训)
            return {"src": src.name, "ok": False, "error": f"{type(e).__name__}: {e}"[:200],
                    "seconds": round(time.time() - t0, 1)}


async def run_batch(srcs: list[Path], parallel: int, n_ch: int, n_chunks: int,
                    n_cand: int, refine: int, min_grade: str | None = None) -> list[dict]:
    sem = asyncio.Semaphore(parallel)
    return await asyncio.gather(*[_one(sem, s, n_ch, n_chunks, n_cand, refine, min_grade)
                                  for s in srcs])


def _collect_sources(paths: list[str]) -> list[Path]:
    out = []
    for p in paths:
        pa = Path(p)
        if pa.is_dir():
            out += sorted(pa.glob("*.txt"))
        elif pa.suffix.lower() == ".txt":
            out.append(pa)
    return out


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="hiki.batch")
    ap.add_argument("sources", nargs="+", help="源目录 或 多个 .txt")
    ap.add_argument("--parallel", type=int, default=4, help="并行本数(账号上限内,建议≤5)")
    ap.add_argument("--chapters", type=int, default=60)
    ap.add_argument("--chunks", type=int, default=12)
    ap.add_argument("-n", "--candidates", type=int, default=3)
    ap.add_argument("--refine-rounds", type=int, default=5)
    ap.add_argument("--min-grade", default=None, choices=["S", "A", "B", "C", "D"],
                    help="源分级门槛:低于此档拒收(如 A=只产S/A好源)")
    a = ap.parse_args()

    srcs = _collect_sources(a.sources)
    if not srcs:
        print("未找到 .txt 源"); return
    print(f"批量: {len(srcs)} 本，并行 {a.parallel}，每本 {a.chapters} 章"
          f"{f'，源门槛≥{a.min_grade}' if a.min_grade else ''} ...")
    t0 = time.time()
    results = asyncio.run(run_batch(srcs, a.parallel, a.chapters, a.chunks,
                                    a.candidates, a.refine_rounds, a.min_grade))
    wall = round(time.time() - t0, 1)

    ok = [r for r in results if r.get("ok")]
    fail = [r for r in results if not r.get("ok")]
    delivered = [r for r in ok if not r.get("rejected")]
    rejected = [r for r in ok if r.get("rejected")]
    cost = round(sum(r.get("cost_cny", 0) or 0 for r in results), 2)
    summary = {
        "本数": len(srcs), "成功": len(ok), "失败": len(fail),
        "可交付": len(delivered), "拒收(暗黑/质量)": len(rejected),
        "总成本_cny": cost, "墙钟_秒": wall,
        "均成本_cny": round(cost / max(1, len(ok)), 2),
        "results": results,
    }
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "batch_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# 批量汇总  {len(srcs)}本/并行{a.parallel}  墙钟{wall}s  总¥{cost}",
             f"可交付 {len(delivered)} | 拒收/不可交付 {len(rejected)} | 失败 {len(fail)}", "",
             "| 源 | grade | 章 | 字 | 暗黑比 | 章缝 | 交付门 | ¥ | 秒 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        if r.get("ok"):
            gate_txt = "✓" if not r.get("rejected") else "；".join(r.get("交付门") or ["拦截"])[:30]
            lines.append(f"| {r['src'][:24]} | {r.get('grade')} | {r.get('out_chapters')} | "
                         f"{r.get('final_chars')} | {r.get('暗黑比')} | {r.get('章缝_检出', '')} | "
                         f"{gate_txt} | {r.get('cost_cny')} | {r.get('seconds')} |")
        else:
            lines.append(f"| {r['src'][:24]} | **失败** | | | | | | {r.get('seconds')} | {r.get('error','')[:40]}")
    (out_dir / "batch_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n=== 批量汇总 ===\n可交付 {len(delivered)} | 拒收 {len(rejected)} | 失败 {len(fail)}")
    print(f"总成本 ¥{cost} | 均 ¥{summary['均成本_cny']}/本 | 墙钟 {wall}s")
    print(f"明细 → output/batch_summary.md")


if __name__ == "__main__":
    main()
