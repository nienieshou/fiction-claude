"""漏斗产线（`hiki funnel`）：pregrade → filter → run，一条命令自动 funnel。

10k 流水线的 pilot 薄片：对源池逐本独立预分级，按档过滤，**只放强源进改写**——
省钱全在 filter（弱源不烧改写钱，A4「源是脊柱/提分靠选」）。落 funnel_report.{json,md}。
`--dry-run` 只 pregrade+filter+估成本不改写；`--max N` 强源优先取前 N 本改写（pilot 控成本）。
"""
from __future__ import annotations
import asyncio
import json
import re
import time
from pathlib import Path
from . import pregrade, batch

_GRADE_ORDER = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4, "Q": 5}
_EST_PER_BOOK_CNY = 6.7      # dry-run 改写成本估算锚(实测全流程单本 ¥6.5-7)


def _slug(stem: str, seen: set) -> str:
    """源文件名 → 文件系统安全、唯一的 slug(批输出子目录名)。"""
    s = re.sub(r'[\\/:*?"<>|\s,，。：；、（）()【】]+', "_", stem).strip("_")[:40] or "book"
    base, i = s, 1
    while s in seen:
        i += 1
        s = f"{base[:36]}_{i}"
    seen.add(s)
    return s


def select(rows_with_paths: list[tuple], keep: set, max_books: int | None) -> list[tuple]:
    """过滤+排序:ok 且 grade∈keep → 按档(S>A>..)再字数降序 → 取前 max_books。→ [(Path,row)]。"""
    surv = [(p, r) for p, r in rows_with_paths if r.get("ok") and r.get("grade") in keep]
    surv.sort(key=lambda pr: (_GRADE_ORDER.get(pr[1].get("grade"), 9), -(pr[1].get("wan_zi") or 0)))
    return surv[:max_books] if max_books else surv


def build_tasks(survivors: list[tuple], out: Path, run_opts: dict) -> list[batch.Task]:
    """存活源 → [Task]（slug 自动派生且唯一，out_dir=<out>/<slug>，min_grade=None：filter 已做）。"""
    seen, tasks = set(), []
    for p, _ in survivors:
        slug = _slug(p.stem, seen)
        tasks.append(batch.Task(
            slug=slug, source=p, out_dir=out / slug,
            n_ch=run_opts["chapters"], n_chunks=run_opts["chunks"], n_cand=run_opts["candidates"],
            refine_rounds=run_opts["refine_rounds"], min_grade=None, force=run_opts["force"]))
    return tasks


def _dist(rows: list[dict]) -> dict:
    d: dict = {}
    for r in rows:
        if r.get("ok"):
            d[r.get("grade")] = d.get(r.get("grade"), 0) + 1
    return dict(sorted(d.items(), key=lambda kv: _GRADE_ORDER.get(kv[0], 9)))


def _write_report(out: Path, summary: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "funnel_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    s = summary
    funnel_line = (f"入池 {s['入池']} → pregrade成功 {s['pregrade成功']}(失败{s['pregrade失败']}) "
                   f"→ 存活[{','.join(s['keep档'])}] {s['存活']} → 改写 {s['改写']}")
    if not s["dry_run"]:
        funnel_line += f" → 可交付 {s['可交付']}(拒收{s['拒收']}/失败{s['改写失败']})"
    lines = [f"# 漏斗报告  入池{s['入池']}  墙钟{s['墙钟_秒']}s  {'(DRY-RUN)' if s['dry_run'] else ''}",
             "", funnel_line, "",
             f"**成本**: pregrade ¥{s['pregrade成本_cny']}"
             + (f" + 改写 ¥{s['改写成本_cny']} = ¥{s['总成本_cny']} | ¥{s['每交付本_cny']}/交付本"
                if not s["dry_run"] else f" | 改写估算 ¥{s['改写成本估算_cny']}(未跑) → 总估 ¥{s['总成本估算_cny']}"),
             "", f"pregrade 分布: " + "、".join(f"{g}×{n}" for g, n in s["pregrade分布"].items()),
             "", "| 阶段 | 计数 | 说明 |", "|---|---|---|",
             f"| 入池 | {s['入池']} | 收集到的 .txt 源 |",
             f"| pregrade 成功 | {s['pregrade成功']} | 失败 {s['pregrade失败']}(flaky/损坏) |",
             f"| filter 存活 | {s['存活']} | grade∈[{','.join(s['keep档'])}],其余淘汰省改写¥ |",
             f"| 改写 | {s['改写']} | {'--max 截顶' if s['改写'] < s['存活'] else '全部存活'} |"]
    if not s["dry_run"]:
        lines.append(f"| 可交付 | {s['可交付']} | 拒收{s['拒收']}/失败{s['改写失败']} |")
    (out / "funnel_report.md").write_text("\n".join(lines), encoding="utf-8")


async def run_funnel(srcs: list[Path], out: Path, keep: set, pregrade_parallel: int,
                     rewrite_parallel: int, max_books: int | None, run_opts: dict,
                     dry_run: bool) -> dict:
    """一条龙:pregrade(逐本独立)→ filter(按档)→ build_tasks → run(批量)。→ funnel summary dict。"""
    t0 = time.time()
    pg_rows = await pregrade.run_pool(srcs, pregrade_parallel, run_opts["chunks"])
    rows_with_paths = list(zip(srcs, pg_rows))
    survivors = select(rows_with_paths, keep, None)            # 全部存活(未截顶)
    rewrite_set = survivors[:max_books] if max_books else survivors
    tasks = build_tasks(rewrite_set, out, run_opts)
    pregrade_cost = round(sum(r.get("cost_cny", 0) or 0 for r in pg_rows), 2)
    pg_ok = [r for r in pg_rows if r.get("ok")]

    summary: dict = {
        "入池": len(srcs), "pregrade成功": len(pg_ok), "pregrade失败": len(pg_rows) - len(pg_ok),
        "pregrade分布": _dist(pg_rows), "keep档": sorted(keep, key=lambda g: _GRADE_ORDER.get(g, 9)),
        "存活": len(survivors), "改写": len(tasks), "pregrade成本_cny": pregrade_cost,
        "dry_run": dry_run, "存活源": [p.name for p, _ in survivors],
    }
    if dry_run:
        est = round(len(tasks) * _EST_PER_BOOK_CNY, 2)
        summary.update({"改写成本估算_cny": est, "总成本估算_cny": round(pregrade_cost + est, 2),
                        "墙钟_秒": round(time.time() - t0, 1)})
    else:
        results = await batch.run_tasks(tasks, rewrite_parallel)
        bs = batch.write_summary(results, round(time.time() - t0, 1), out)
        delivered = bs["可交付"]
        total = round(pregrade_cost + bs["总成本_cny"], 2)
        summary.update({"可交付": delivered, "拒收": bs["拒收/不可交付"], "改写失败": bs["失败"],
                        "改写成本_cny": bs["总成本_cny"], "总成本_cny": total,
                        "每交付本_cny": round(total / max(1, delivered), 2),
                        "墙钟_秒": bs["墙钟_秒"], "batch": bs})
    _write_report(out, summary)
    return summary
