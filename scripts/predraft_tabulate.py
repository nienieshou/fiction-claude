# scripts/predraft_tabulate.py
"""PreDraft Review v0 校准: 读 predraft findings + 实测标注 → 各 reviewer×类目 精度/召回。
不调 API。用法: python scripts/predraft_tabulate.py <vdir> --labels labels.yaml"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

REVIEWERS = ("det", "deepseek", "opus", "gpt55", "crossfamily")


def load_predraft(vdir) -> dict:
    vdir = Path(vdir); pdir = vdir / "predraft"
    out: dict = {}
    if not pdir.is_dir():
        return out
    for p in sorted(pdir.glob("*__*.json")):
        slug, reviewer = p.name[:-5].split("__", 1)
        try:
            findings = json.loads(p.read_text(encoding="utf-8")).get("findings") or []
        except (json.JSONDecodeError, OSError):
            continue
        hard = {f["category"] for f in findings if isinstance(f, dict) and f.get("severity") == "hard" and f.get("category")}
        allc = {f["category"] for f in findings if isinstance(f, dict) and f.get("category")}
        out.setdefault(slug, {})[reviewer] = {"hard": hard, "all": allc}
    return out


def _augment_crossfamily(predraft) -> dict:
    """合成 crossfamily reviewer = opus∪gpt55(per book),供与 deepseek 同口径比 P/R。"""
    out = {}
    for slug, byrev in predraft.items():
        byrev = dict(byrev)
        if "opus" in byrev or "gpt55" in byrev:
            byrev["crossfamily"] = {
                "hard": byrev.get("opus", {}).get("hard", set()) | byrev.get("gpt55", {}).get("hard", set()),
                "all": byrev.get("opus", {}).get("all", set()) | byrev.get("gpt55", {}).get("all", set())}
        out[slug] = byrev
    return out


def precision_recall(predraft, observed) -> dict:
    predraft = _augment_crossfamily(predraft)
    # 收集每 reviewer 出现过的类目
    res: dict = {}
    cats_by_rev: dict = {}
    for slug, byrev in predraft.items():
        for rev, d in byrev.items():
            cats_by_rev.setdefault(rev, set()).update(d["hard"])
            cats_by_rev[rev].update(observed.get(slug, []))
    for rev, cats in cats_by_rev.items():
        res[rev] = {}
        for cat in sorted(cats):
            tp = fp = fn = 0
            for slug, byrev in predraft.items():
                if rev not in byrev:
                    continue
                pred = cat in byrev[rev]["hard"]
                obs = cat in set(observed.get(slug, []))
                if pred and obs: tp += 1
                elif pred and not obs: fp += 1
                elif obs and not pred: fn += 1
            prec = tp / (tp + fp) if (tp + fp) else None
            rec = tp / (tp + fn) if (tp + fn) else None
            res[rev][cat] = {"tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec}
    return res


def format_predraft_report(predraft, observed) -> str:
    pr = precision_recall(predraft, observed)
    L = [f"=== PreDraft Review 校准 (books={len(predraft)}) ==="]
    for rev in REVIEWERS:
        if rev not in pr:
            continue
        L.append(f"[{rev}] 精度/召回 per 类目:")
        for cat, m in sorted(pr[rev].items(), key=lambda kv: -(kv[1]["tp"])):
            if m["tp"] + m["fp"] + m["fn"] == 0:
                continue
            L.append(f"  {cat}: P={m['precision']} R={m['recall']} (tp{m['tp']}/fp{m['fp']}/fn{m['fn']})")
    # DeepSeek 自审 vs 跨族(crossfamily=opus∪gpt55): 按类目 精度/召回 对比(spec 要召回/精度差)
    L.append("[DeepSeek 自审 vs 跨族(opus∪gpt55)] 各类目 精度/召回:")
    ds_pr = pr.get("deepseek", {})
    cf_pr = pr.get("crossfamily", {})
    for c in sorted(set(ds_pr) | set(cf_pr)):
        d = ds_pr.get(c, {}); f = cf_pr.get(c, {})
        L.append(f"  {c}: DeepSeek P={d.get('precision')}/R={d.get('recall')}  跨族 P={f.get('precision')}/R={f.get('recall')}")
    L.append("[诚实边界] n 小→方向非精度阈值; 精度量'预测末态兑现'非'纸面自洽'; hard 拦只认高置信。")
    return "\n".join(L)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("vdir")
    ap.add_argument("--labels", default=None)
    a = ap.parse_args(argv)
    observed = {}
    if a.labels and Path(a.labels).exists():
        import yaml
        observed = yaml.safe_load(Path(a.labels).read_text(encoding="utf-8")) or {}
    print(format_predraft_report(load_predraft(a.vdir), observed))


if __name__ == "__main__":
    main()
