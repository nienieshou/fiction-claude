"""重演精度校准(2026-06-26): 在标注 holdout 上实跑 _plane_check 二段, 验收裁决精度。

门设计(关键): 只对 PLANE_CHECK **实际检出**的 hit 判裁决精度; 标注章未被检出 →
归"一阶召回(检测器是否检出)", 本任务范围外, 只报不判。
- FATAL(致命, 0容忍): must_keep 章被检出却被**全部丢弃** = 误杀真重演(破召回)。
- SOFT(精度未尽, 非致命): must_drop 章被检出却仍保留 = FP 未滤净(偏向召回可接受)。

标注说明: must_keep 用 PLANE_CHECK 原生能检出的真重演(陶马/踹门/邪物逃命/断后);
**不含 CPBXN ch49** —— ch49 的真重演是"漩涡黑影边界重演(距离10→5米)", 属 seam/adj
检测器范畴, PLANE_CHECK 这里命中的是"RPG袭击"事件(不同事件), 跨检测器标注会误判,
故移出本校准。must_drop 用确凿视角转述 FP: ZYGGY ch29(程婉转告宋旸娶亲事)。
用法: PYTHONPATH=src python scripts/reenact_precision_calib.py
"""
import asyncio, json, re, sys
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
from hiki.client import Client
from hiki import produce

ROOT = Path("E:/Project_Python/hiki-fiction-cli/claude")
_HDR = re.compile(r"^# 第\d+章.*$", re.M)
# (final.md, plan.json, 应滤除FP章集(soft), 应保留真重演章集(fatal若误杀))
BOOKS = {
    "CPBXN00188": (ROOT / "output/CPBXN00188开局冰川探墓你管这叫娱乐主播_20260625_full/final.md",
                   ROOT / "output/CPBXN00188开局冰川探墓你管这叫娱乐主播_20260625_full/plan.json",
                   set(), {18, 31}),
    "ZYGGY02252": (ROOT / "output/ZYGGY02252归隐田园：执子手共白头/final.md",
                   ROOT / "output/ZYGGY02252归隐田园：执子手共白头/plan.json",
                   {29}, set()),
}
_CHNO = re.compile(r"第(\d+)章重演")


def split_chapters(md: str) -> list[str]:
    return [b.strip() for b in _HDR.split(md)[1:] if b.strip()]


def chap_nums(hits: list[str]) -> set[int]:
    return {int(m.group(1)) for h in hits if (m := _CHNO.search(h))}


async def main():
    cli = Client()
    ok = True
    for tag, (md_p, plan_p, must_drop, must_keep) in BOOKS.items():
        ch = split_chapters(md_p.read_text(encoding="utf-8"))
        plan = json.loads(plan_p.read_text(encoding="utf-8"))
        kept, filtered = await produce._plane_check(cli, ch, plan)
        kept_n, filt_n = chap_nums(kept), chap_nums(filtered)
        detected = kept_n | filt_n
        print(f"\n[{tag}] 真重演 {len(kept)} 章{sorted(kept_n)} | 视角转述滤除 {len(filtered)} 章{sorted(filt_n)}")

        # FATAL: must_keep 被检出却不在 kept(全丢) = 误杀真重演
        killed = {c for c in must_keep if c in detected and c not in kept_n}
        keep_undet = must_keep - detected
        if killed:
            ok = False
            print(f"   ✗ 致命: 误杀真重演(检出却全丢) {sorted(killed)}")
        if must_keep & kept_n:
            print(f"   ✓ 真重演正确保留 {sorted(must_keep & kept_n)}")
        if keep_undet:
            print(f"   · 一阶未检出(范围外,不判) {sorted(keep_undet)}")

        # SOFT: must_drop 被检出且已滤除=OK; 检出却仍保留=精度未尽(非致命)
        drop_ok = {c for c in must_drop if c in filt_n and c not in kept_n}
        drop_leak = {c for c in must_drop if c in kept_n}
        drop_undet = must_drop - detected
        if drop_ok:
            print(f"   ✓ FP正确滤除 {sorted(drop_ok)}")
        if drop_leak:
            print(f"   ~ FP未滤净(精度未尽,非致命) {sorted(drop_leak)}")
        if drop_undet:
            print(f"   · 一阶未检出(范围外,不判) {sorted(drop_undet)}")
    print(f"\n总 calls={cli.calls}  cost=¥{cli.cost_cny:.2f}  验收={'通过' if ok else '不通过'}(致命=误杀真重演)")


if __name__ == "__main__":
    asyncio.run(main())
