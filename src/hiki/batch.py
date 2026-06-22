"""批量产线（`hiki run` 的引擎）：任务驱动(tasks.yaml)或源目录，多本并行跑 produce.run。

并发=DeepSeek 账号上限(~2500flash/500pro);提速=①每本内部高并发 ②多本并行(外层 sem)。
单本失败/拒收**隔离**(一本崩不拖累其余,traceback 落 <out>/<slug>/_crash.txt);
阶段产物存在即**续跑**(B2),--force 从头重跑。汇总 batch_summary.{json,md}。
"""
from __future__ import annotations
import asyncio
import json
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from .produce import run

_KEYS = ("title", "grade", "out_chapters", "final_chars", "暗黑比",
         "deliverable", "交付门", "final_consistent", "cost_cny", "seconds")


@dataclass
class Task:
    slug: str
    source: Path
    out_dir: Path
    n_ch: int = 60
    n_chunks: int = 12
    n_cand: int = 3
    refine_rounds: int = 5
    min_grade: str | None = None
    force: bool = False
    best_of: int = 1


def load_tasks(path: Path, defaults: dict) -> list[Task]:
    """解析 tasks.yaml → [Task]。out_dir = <out>/<slug>(同 out+不同 slug 各自独立目录)。
    per-task 可覆盖 chapters/chunks/candidates/refine_rounds/min_grade/force;缺省取 defaults。"""
    import yaml
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"{path} 解析失败(常见:`out:output/x` 冒号后缺空格,应 `out: output/x`):\n{e}")
    raw = doc.get("tasks")
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{path}: 顶层需 `tasks:` 列表(检查 yaml 缩进/冒号后空格)")
    seen, tasks = set(), []
    for i, t in enumerate(raw):
        if not isinstance(t, dict):
            raise ValueError(f"tasks[{i}] 不是映射——常见是 `out:output/x` 冒号后缺空格,应 `out: output/x`")
        slug = str(t.get("slug") or f"task{i}").strip()
        if slug in seen:
            raise ValueError(f"slug 重复: {slug}(每任务需唯一,它决定输出子目录)")
        seen.add(slug)
        source = t.get("source")
        if not source:
            raise ValueError(f"tasks[{i}]({slug}) 缺 source")
        out = str(t.get("out") or defaults.get("out") or "output").strip()
        tasks.append(Task(
            slug=slug, source=Path(source), out_dir=Path(out) / slug,
            n_ch=int(t.get("chapters", defaults["chapters"])),
            n_chunks=int(t.get("chunks", defaults["chunks"])),
            n_cand=int(t.get("candidates", defaults["candidates"])),
            refine_rounds=int(t.get("refine_rounds", defaults["refine_rounds"])),
            min_grade=t.get("min_grade", defaults["min_grade"]),
            force=bool(t.get("force", defaults["force"])),
            best_of=int(t.get("best_of", defaults.get("best_of", 1))),
        ))
    return tasks


def _should_retry(rep: dict) -> bool:
    """best-of-N:仅"交付门拒"(deliverable is False 且非源头致命)值得重掷——draft随机造死亡那类。
    源头致命(rejected=True:Q/暗黑/低于min-grade)重掷无用;已交付/无信号 不重。"""
    return rep.get("deliverable") is False and not rep.get("rejected")


def _pick(rep: dict) -> dict:
    out = {k: rep[k] for k in _KEYS if k in rep}
    g = rep.get("grade") or {}
    out["grade"] = g.get("grade") if isinstance(g, dict) else g
    out["rejected"] = bool(rep.get("rejected") or rep.get("deliverable") is False)
    return out


async def _one(sem: asyncio.Semaphore, task: Task, run_fn=run) -> dict:
    async with sem:                                   # 外层限并行本数(账号上限内)
        t0 = time.time()
        if not task.source.exists():
            return {"slug": task.slug, "ok": False, "error": f"源不存在: {task.source}"}
        try:
            rep, throws = None, 0
            for attempt in range(1, max(1, task.best_of) + 1):   # best-of-N: 拒收即重掷
                throws = attempt
                rep = await run_fn(task.source, task.n_ch, task.n_chunks, task.n_cand,
                                   task.refine_rounds, min_grade=task.min_grade,
                                   out_dir=task.out_dir, force=(task.force if attempt == 1 else True))
                if not _should_retry(rep):            # 已交付 或 源头致命 → 停(致命重掷无用)
                    break
            return {"slug": task.slug, "ok": True, "out_dir": str(task.out_dir),
                    "throws": throws, **_pick(rep)}
        except Exception as e:                        # 单本失败隔离:落 traceback,不拖累其余
            task.out_dir.mkdir(parents=True, exist_ok=True)
            (task.out_dir / "_crash.txt").write_text(traceback.format_exc(), encoding="utf-8")
            return {"slug": task.slug, "ok": False, "error": f"{type(e).__name__}: {e}"[:200],
                    "seconds": round(time.time() - t0, 1)}


async def run_tasks(tasks: list[Task], parallel: int) -> list[dict]:
    sem = asyncio.Semaphore(parallel)
    return await asyncio.gather(*[_one(sem, t) for t in tasks])


def write_summary(results: list[dict], wall: float, out_dir: Path = Path("output")) -> dict:
    ok = [r for r in results if r.get("ok")]
    fail = [r for r in results if not r.get("ok")]
    delivered = [r for r in ok if not r.get("rejected")]
    cost = round(sum(r.get("cost_cny", 0) or 0 for r in results), 2)
    summary = {"任务数": len(results), "成功": len(ok), "失败": len(fail),
               "可交付": len(delivered), "拒收/不可交付": len(ok) - len(delivered),
               "总成本_cny": cost, "墙钟_秒": wall,
               "均成本_cny": round(cost / max(1, len(ok)), 2), "results": results}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "batch_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# 批量汇总  {len(results)}任务  墙钟{wall}s  总¥{cost}",
             f"可交付 {len(delivered)} | 拒收/不可交付 {len(ok)-len(delivered)} | 失败 {len(fail)}", "",
             "| slug | grade | 章 | 字 | 交付门 | ¥ | 秒 | 输出 |",
             "|---|---|---|---|---|---|---|---|"]
    for r in results:
        if r.get("ok"):
            g = "✓可交付" if not r.get("rejected") else "；".join(r.get("交付门") or ["拦截"])[:28]
            lines.append(f"| {r['slug']} | {r.get('grade')} | {r.get('out_chapters')} | "
                         f"{r.get('final_chars')} | {g} | {r.get('cost_cny')} | {r.get('seconds')} | "
                         f"{r.get('out_dir','')} |")
        else:
            lines.append(f"| {r['slug']} | **失败** | | | {r.get('error','')[:40]} | | {r.get('seconds','')} | |")
    (out_dir / "batch_summary.md").write_text("\n".join(lines), encoding="utf-8")
    return summary
