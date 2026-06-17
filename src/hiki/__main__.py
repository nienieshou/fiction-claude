"""CLI 入口。
  hiki ingest <src.txt>                      P0 清洗(无需 API key)
  hiki run <src.txt> [--out DIR]             单本复写
  hiki run --tasks-file tasks.yaml           批量复写(tasks: [{slug,source,out}])
  hiki funnel <源目录> [--keep S,A] [--max N] [--dry-run]   漏斗:pregrade→filter→run 一条命令
"""
from __future__ import annotations
import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from .ingest import ingest


def _add_run_opts(p: argparse.ArgumentParser) -> None:
    p.add_argument("--chapters", type=int, default=60, help="目标章数")
    p.add_argument("--chunks", type=int, default=12, help="深挖窗口数")
    p.add_argument("-n", "--candidates", type=int, default=3, help="每场景候选数(成本×质量)")
    p.add_argument("--refine-rounds", type=int, default=3, help="金标精修轮(高潮章;实证2-3轮即够,多轮震荡)")
    p.add_argument("--min-grade", default=None, choices=["S", "A", "B", "C", "D"],
                   help="源分级门槛:低于此档拒收")
    p.add_argument("--parallel", type=int, default=3, help="并行本数(账号限流内,建议≤5)")
    p.add_argument("--spine", action=argparse.BooleanOptionalAction, default=True,
                   help="Fact Spine 事前一致性(质量默认开,HIKI_SPINE=1;--no-spine 关闭)")
    p.add_argument("--force", action="store_true", help="忽略已有阶段产物,从头重跑(默认续跑)")


def _cmd_run(a: argparse.Namespace) -> None:
    from . import batch
    os.environ["HIKI_SPINE"] = "1" if a.spine else "0"   # 复写前置,produce 各阶段读 env(质量默认开)
    defaults = {"out": a.out, "chapters": a.chapters, "chunks": a.chunks,
                "candidates": a.candidates, "refine_rounds": a.refine_rounds,
                "min_grade": a.min_grade, "force": a.force}
    if a.tasks_file:
        tasks = batch.load_tasks(Path(a.tasks_file), defaults)
    elif a.src:
        single_out = Path(a.out) if a.out else Path("output") / (Path(a.src).stem + "_full")
        tasks = [batch.Task(slug=Path(a.src).stem, source=Path(a.src), out_dir=single_out,
                            n_ch=a.chapters, n_chunks=a.chunks, n_cand=a.candidates,
                            refine_rounds=a.refine_rounds, min_grade=a.min_grade, force=a.force)]
    else:
        print("用法: hiki run <src.txt> | hiki run --tasks-file tasks.yaml")
        sys.exit(2)
    print(f"批量: {len(tasks)} 任务，并行 {a.parallel}"
          f"{'，Fact Spine 开' if a.spine else '，Spine 关'}，精修{a.refine_rounds}轮"
          f"{'，--force 重跑' if a.force else '，续跑'} ...")
    t0 = time.time()
    results = asyncio.run(batch.run_tasks(tasks, a.parallel))
    s = batch.write_summary(results, round(time.time() - t0, 1))
    print(f"\n=== 批量汇总 === 可交付 {s['可交付']} | 拒收/不可交付 {s['拒收/不可交付']} | 失败 {s['失败']}")
    print(f"总成本 ¥{s['总成本_cny']} | 均 ¥{s['均成本_cny']}/本 | 墙钟 {s['墙钟_秒']}s → output/batch_summary.md")


def _cmd_funnel(a: argparse.Namespace) -> None:
    from . import funnel, pregrade
    os.environ["HIKI_SPINE"] = "1" if a.spine else "0"   # 质量默认开
    srcs = pregrade._collect(a.sources)
    if not srcs:
        print("未找到 .txt 源（传源目录或多个 .txt）"); sys.exit(2)
    keep = {g.strip().upper() for g in a.keep.split(",") if g.strip()}
    run_opts = {"chapters": a.chapters, "chunks": a.chunks, "candidates": a.candidates,
                "refine_rounds": a.refine_rounds, "force": a.force}
    print(f"漏斗: 入池 {len(srcs)} 本 → pregrade(并行{a.pregrade_parallel}) → 保留[{','.join(sorted(keep))}]"
          f"{f' → 改写前{a.max}本' if a.max else ''}{' [DRY-RUN]' if a.dry_run else f' → 改写(并行{a.parallel})'}"
          f"{'，Spine 开' if a.spine else '，Spine 关'} ...")
    s = asyncio.run(funnel.run_funnel(srcs, Path(a.out), keep, a.pregrade_parallel,
                                      a.parallel, a.max, run_opts, a.dry_run))
    print(f"\n=== 漏斗汇总 === 入池{s['入池']} → pregrade成功{s['pregrade成功']} "
          f"→ 存活[{','.join(s['keep档'])}]{s['存活']} → 改写{s['改写']}"
          + ("" if s["dry_run"] else f" → 可交付{s['可交付']}"))
    print(f"pregrade分布: {s['pregrade分布']}")
    if s["dry_run"]:
        print(f"成本: pregrade ¥{s['pregrade成本_cny']} | 改写估算 ¥{s['改写成本估算_cny']} "
              f"→ 总估 ¥{s['总成本估算_cny']}（未改写，去掉 --dry-run 实跑）")
    else:
        print(f"成本: pregrade ¥{s['pregrade成本_cny']} + 改写 ¥{s['改写成本_cny']} = ¥{s['总成本_cny']} "
              f"| ¥{s['每交付本_cny']}/交付本")
    print(f"→ {a.out}/funnel_report.md")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="hiki", description="小说复写引擎")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("ingest", help="P0 清洗单本源 txt")
    pi.add_argument("src", help="源 .txt 路径")
    pi.add_argument("--out", default=None, help="输出目录（默认 output/<源名>/source）")
    pr = sub.add_parser("run", help="复写:单本(<src.txt>)或批量(--tasks-file)")
    pr.add_argument("src", nargs="?", help="单本源 .txt(批量时省略)")
    pr.add_argument("--tasks-file", default=None, help="批量任务 yaml")
    pr.add_argument("--out", default=None, help="输出(批量=父目录,落 <out>/<slug>/;单本=该目录)")
    _add_run_opts(pr)
    pf = sub.add_parser("funnel", help="漏斗:pregrade→filter→run 一条命令(10k 流水线 pilot)")
    pf.add_argument("sources", nargs="+", help="源目录或多个 .txt")
    pf.add_argument("--out", default="output/funnel", help="批输出父目录(默认 output/funnel)")
    pf.add_argument("--keep", default="S,A", help="保留档位(逗号分隔),默认 S,A")
    pf.add_argument("--pregrade-parallel", type=int, default=8, help="pregrade 并行本数")
    pf.add_argument("--max", type=int, default=None, help="最多改写本数(强源优先,pilot 控成本)")
    pf.add_argument("--dry-run", action="store_true", help="只 pregrade+filter+估成本,不改写")
    _add_run_opts(pf)

    args = ap.parse_args()
    if args.cmd == "ingest":
        src = Path(args.src)
        out = Path(args.out) if args.out else Path("output") / src.stem / "source"
        meta = ingest(src, out)
        print(f"✓ ingest 完成 → {out}")
        print(meta.to_json())
    elif args.cmd == "run":
        _cmd_run(args)
    elif args.cmd == "funnel":
        _cmd_funnel(args)


if __name__ == "__main__":
    main()
