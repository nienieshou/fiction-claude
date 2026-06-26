"""重演精度校准(2026-06-26): 在标注 holdout 上实跑 _plane_check 二段, 验收:
ZYGGY02252 ch29/ch38 应被滤除(视角转述FP), CPBXN00188 ch49/ch18 应保留(真重演TP), 0 漏真重演。
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
# (final.md, plan.json, 应被滤除章集, 应保留章集)
BOOKS = {
    "CPBXN00188": (ROOT / "output/CPBXN00188开局冰川探墓你管这叫娱乐主播_20260625_full/final.md",
                   ROOT / "output/CPBXN00188开局冰川探墓你管这叫娱乐主播_20260625_full/plan.json",
                   set(), {49, 18}),
    "ZYGGY02252": (ROOT / "output/ZYGGY02252归隐田园：执子手共白头/final.md",
                   ROOT / "output/ZYGGY02252归隐田园：执子手共白头/plan.json",
                   {29, 38}, set()),
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
        print(f"\n[{tag}] 真重演 {len(kept)} 章{sorted(kept_n)} | 视角转述滤除 {len(filtered)} 章{sorted(filt_n)}")
        # 验收: must_drop 必须在滤除集(不在真重演集); must_keep 必须在真重演集
        drop_fail = must_drop - filt_n
        keep_fail = must_keep - kept_n
        leak = must_drop & kept_n          # 标注FP却被判真重演 = 精度未达(非致命)
        miss = must_keep - kept_n          # 标注真重演却漏 = 0漏门槛违反(致命)
        if drop_fail or keep_fail:
            ok = False
        print(f"   应丢{sorted(must_drop)}→{'OK' if not drop_fail else f'未滤{sorted(drop_fail)}'}"
              f" | 应留{sorted(must_keep)}→{'OK' if not keep_fail else f'漏{sorted(keep_fail)}'}")
        if miss:
            print(f"   ✗ 致命: 漏真重演 {sorted(miss)}")
    print(f"\n总 calls={cli.calls}  cost=¥{cli.cost_cny:.2f}  验收={'通过' if ok else '不通过'}")


if __name__ == "__main__":
    asyncio.run(main())
