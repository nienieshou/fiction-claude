"""桶B 拆分:对 4 个被生死门拦、但源弧=无弧的角色,做**定向源读**(最大召回),判源书到底有没有这条死人复活弧。
B1 recall-miss = 源书确有死而复生(dies_returns)→ 生产抽漏了 → 杠杆=召回硬化。
B2 真矛盾     = 源书永久死(dies_final)或根本不死(never_dies)→ 复写自造/错复活 → 门判对,杠杆=源池选择。
定向(roster=单角色)+细窗,比生产 pass 更狠地找——若仍找不到=强 B2 信号。零起草。"""
import asyncio, glob, json, sys
from pathlib import Path
sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
import os
os.environ["HIKI_SPINE"] = "1"
from hiki.client import Client
from hiki import mining

CASES = [("ZTGGX02751听说我死后成了反派白月光", "桑念"),
         ("ZTGGY02021摄政王妃", "楚香柳"),
         ("ZTGGY03708穿书后我养了偏执男主", "邵昊炎"),
         ("ZYGGX02936第一符术师", "顾楼兰")]


async def main():
    cli = Client()
    b1 = b2 = 0
    for stem, who in CASES:
        d = next(iter(glob.glob(f"output/{stem}*_full")), None)
        src = next(iter(glob.glob(f"{d}/source/*.txt")), None) if d else None
        if not src:
            print(f"!! 缺源 {stem}"); continue
        clean = Path(src).read_text(encoding="utf-8", errors="ignore")
        n = min(48, max(20, len(clean) // 25000))          # 比生产更细一点,逼召回
        chunks = mining.chunk_by_chapters(clean, n_chunks=n)
        results = await mining.extract_life_events_pass(cli, chunks, roster=who)   # 定向单角色
        arc = mining.collect_life_events(results).get(who, {})
        fate = arc.get("fate", "never_dies/无")
        bucket = "B1·recall-miss(源有复活→召回硬化)" if fate == "dies_returns" else \
                 "B2·真矛盾(源永久死/不死→复写自造→选源)"
        if fate == "dies_returns": b1 += 1
        else: b2 += 1
        freq = clean.count(who)
        print(f"{who}({freq}次,{len(clean)}字/{n}窗) → 源弧={fate} | 桶{bucket}")
        if arc.get("death_q") or arc.get("return_q"):
            print(f"   死:{arc.get('death_q','')!r} 复活:{arc.get('return_q','')!r}")
    print(f"\n=== 桶B 拆分: B1 recall-miss {b1} | B2 真矛盾 {b2} ===")
    if b1 > b2:
        print("→ 多为漏抽 → 杠杆=召回硬化(多趟/集成抽取);项2 待召回稳后")
    elif b2 > b1:
        print("→ 多为真矛盾 → 门判对,杠杆=源池选择(A4 救不动则拒);别投项2/召回去救")
    else:
        print("→ 对半 → 两条腿都要,先做召回硬化解锁 B1,B2 归源池")
    print(f"¥{cli.cost_cny:.2f} | {cli.calls} calls")


asyncio.run(main())
