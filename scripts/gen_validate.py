"""5本泛化验证: 各题材 best-of-3 N=3,验系统能否在陌生题材稳定交付71零硬伤本。
逐本串行(每本内best-of-3并行),避免15路并发撞限流。"""
import asyncio, json, sys, shutil
from pathlib import Path
sys.path.insert(0, "src"); sys.stdout.reconfigure(encoding="utf-8")
from hiki.produce import run

BOOKS = [
    ("玄幻仙侠/灵气复苏：开局无限合成.txt", "玄幻爽文(S源)"),
    ("种田基建文/崽崽惊呆！娘亲她成了逃荒路上的美食供应商.txt", "种田逃荒(S源)"),
    ("末世科幻/全球陆沉：我开超级战舰横扫末世.txt", "末世战舰(A)"),
    ("灵异悬疑惊悚/开局冰川探墓，你管这叫娱乐主播.txt", "盗墓探险娱乐(A)"),
    ("玄幻仙侠/带三只废柴崽崽，携空间称霸兽世！.txt", "兽世养崽(A)"),
]
K = 3

def _issue_score(iss):
    if iss == ["通过"]: return 0
    killer = sum(2 for x in iss if any(k in str(x) for k in ("复活","双版本","暗黑饱和","跳过")))
    return len(iss) + killer

async def best_of(src):
    dirs = [Path("output")/f"{src.stem}_gbok{i}" for i in range(K)]
    reps = await asyncio.gather(*[run(src, out_dir=d) for d in dirs], return_exceptions=True)
    rows = []
    for i,(d,rep) in enumerate(zip(dirs,reps)):
        if isinstance(rep,Exception):
            rows.append((i,9999,[f"崩:{type(rep).__name__}"],0.0,None)); continue
        iss = rep.get("交付门",["?"]); rows.append((i,_issue_score(iss),iss,rep.get("cost_cny",0.0),rep))
    rows.sort(key=lambda x:x[1]); best=rows[0]
    final = Path("output")/f"{src.stem}_full_gen"
    if final.exists(): shutil.rmtree(final)
    if not isinstance(reps[best[0]],Exception): shutil.copytree(dirs[best[0]],final)
    return rows, best

async def main():
    summary=[]
    for fn,genre in BOOKS:
        src=Path("fictions_source")/fn
        print(f"\n===== {genre}: {fn[:20]} =====", flush=True)
        rows,best=await best_of(src)
        g=(rows[best[0]][4] or {}).get("grade",{}) if rows[best[0]][4] else {}
        for i,sc,iss,c,_ in rows:
            print(f"  gbok{i}: 硬伤分={sc} {iss} ¥{c}{' ←选中' if i==best[0] else ''}", flush=True)
        clean = best[1]==0
        summary.append({"源":fn[:24],"题材":genre,"grade":g.get("grade"),
            "best硬伤分":best[1],"裸过门":clean,"选中门":rows[best[0]][2],
            "best_of成本":round(sum(r[3] for r in rows),2)})
        print(f"  → 选gbok{best[0]} 硬伤分{best[1]} {'✓裸过门(零硬伤)' if clean else '⚠有残留'} grade={g.get('grade')}", flush=True)
    Path("output").mkdir(exist_ok=True)
    json.dump(summary,open("output/gen_validate_summary.json","w",encoding="utf-8"),ensure_ascii=False,indent=2)
    print("\n===== 泛化验证汇总 =====", flush=True)
    nclean=sum(1 for s in summary if s["裸过门"])
    for s in summary: print(f"  {s['题材']:<14} grade={s['grade']} best硬伤分{s['best硬伤分']} {'✓裸过' if s['裸过门'] else '⚠'+str(s['选中门'])}", flush=True)
    print(f"\n裸过门(零硬伤可交付): {nclean}/5 | 总成本 ¥{sum(s['best_of成本'] for s in summary):.2f}", flush=True)

asyncio.run(main())
