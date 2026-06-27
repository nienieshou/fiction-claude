"""R9 选优点修通道: 对交付门拦截本做引文级外科修复,复检后放行。

A4 公理书级应用: 重跑=重掷方差(第6跑铁证: 重掷不涨分),点修无重掷——修的是已定位点。
输入 out_dir/{final.md, report.json, bible.json, repair_targets.json(可选,评审引文)}。
流程: 收集 per-章 issue → 复活类走已验证的 verify→repair_revivals → 其余 POINT_REPAIR
章级最小重写(采用守卫) → 复检(事实表生死verify/结尾跳空/连续性advisory) → 干净则写
<源ID><新书名>.txt 落 _deliverable/(拒收落 _rejected/) + report 更新为可交付。

用法: PYTHONPATH=src python -m hiki.point_repair <out_dir>
"""
from __future__ import annotations
import asyncio
import json
import re
import sys
from pathlib import Path
from . import prompts, gate, audit, prose_continuity, prose_facts, textnum
from .client import Client
from .slice_validate import _strip_markers
from .produce import _trim_tail, _book_filename, _delivery_path, _safe_filename

def _repair_delivery(out_dir: Path, title: str, body_text: str, deliverable: bool):
    """复检后交付落盘决策(纯,不写盘): 返回 (write_path, stale_rejected_path|None, book_text)。
    与 produce._stage_finalize 同构: 甲格式正文 + 干净交付名 + _deliverable/_rejected 分流。
    deliverable 时 stale = 旧的 _rejected/ 同名件路径,供调用方清掉(本子转可交付)。"""
    safe = _safe_filename(title)
    out_name = _book_filename(out_dir.name, safe)
    write_path = _delivery_path(out_dir, deliverable, out_name)
    stale = _delivery_path(out_dir, False, out_name) if deliverable else None
    book = f"《{title}》\n\n{body_text}" if title else body_text
    return write_path, stale, book


_EDIT_NOTE = re.compile(r"^\s*【[^】]{0,40}】\s*$", re.M)


def _post_process(t: str) -> str:
    """点修章与产线同规后处理: 去标记/编辑痕行 + 章尾句界(星际实测: 点修引入【】痕+断尾)。"""
    t = _strip_markers(t)
    t = _EDIT_NOTE.sub("", t)
    return _trim_tail(t.strip())

_CH_HEAD = textnum.MD_CH_RE
_CH_IN_TEXT = textnum.INLINE_CH_NUM_RE


def _split_keep_headers(final_md: str) -> tuple[str, list[str], list[str]]:
    """final.md → (前言块, 章标题列表, 章正文列表)。点修要写回,标题必须保留。"""
    headers = _CH_HEAD.findall(final_md)
    bodies = [p.strip() for p in _CH_HEAD.split(final_md)[1:]]
    preamble = final_md.split(headers[0])[0] if headers else ""
    return preamble, headers, bodies


def _reassemble(preamble: str, headers: list[str], bodies: list[str]) -> str:
    return (preamble.rstrip() + "\n\n" if preamble.strip() else "") + \
        "\n\n".join(f"{h}\n\n{b}" for h, b in zip(headers, bodies))


async def _verified_revivals(cli: Client, chs: list[str]) -> list[dict]:
    ft = await prose_facts.fact_table_audit(cli, chs)
    cand = [{"who": f["who"], "clue": (f.get("why") or "")[:30], "revive_ch": f["ch_b"] - 1,
             "death_ch": (f["ch_a"] - 1) if isinstance(f.get("ch_a"), int) else None}
            for f in ft["findings"] if f.get("cat") == "生死"
            and isinstance(f.get("ch_b"), int) and 1 <= f["ch_b"] <= len(chs)]
    return await prose_continuity.verify_revivals(cli, chs, cand) if cand else []


async def run(out_dir: Path) -> dict:
    final = (out_dir / "final.md").read_text(encoding="utf-8")
    rep = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    preamble, headers, chs = _split_keep_headers(final)
    cli = Client()

    # 1) 收集章级 issue: repair_targets.json(评审引文) + report advisory(带章号的)
    targets: list[dict] = []
    tf = out_dir / "repair_targets.json"
    if tf.exists():
        targets += [t for t in json.loads(tf.read_text(encoding="utf-8")) if isinstance(t, dict)]
    for a in rep.get("advisory_issues") or []:
        for m in _CH_IN_TEXT.finditer(str(a)):       # 多章issue每章都修(兽世币种ch2/ch3只修ch2的实证bug)
            targets.append({"ch": int(m.group(1)), "issue": str(a)})

    # 2) 复活类: detect→verify→repair **循环至稳定**(抽取有随机性,单轮检出是子集——
    #    团宠实测: 第1轮只见傅礼,复检冒出3人;单次阴性不可信)
    all_revived: list[dict] = []
    for _round in range(3):
        revived = await _verified_revivals(cli, chs)
        if not revived:
            break
        print(f"点修: 死人复活第{_round + 1}轮 {len(revived)} 处 → 位点选择修复: {[r['who'] for r in revived]}")
        chs = await prose_continuity.repair_revivals_smart(cli, chs, revived)
        all_revived += revived
    revived = all_revived

    # 3) 章级点修(同章多 issue 一次修),采用守卫
    by_ch: dict[int, list[str]] = {}
    for t in targets:
        c = t.get("ch")
        if isinstance(c, int) and 1 <= c <= len(chs) and t.get("issue"):
            by_ch.setdefault(c, []).append(str(t["issue"])[:160])
    sys_p, usr_t = prompts.POINT_REPAIR

    async def _fix(c: int, issues: list[str]) -> tuple[int, str]:
        raw = await cli.complete("draft", sys_p,
                                 usr_t.format(issues="；".join(issues), text=chs[c - 1][:14000]),
                                 max_tokens=8000, temperature=0.3)
        return c, (raw or "").strip()

    applied: list[int] = []
    unresolved: list[str] = []
    if by_ch:
        res = await asyncio.gather(*[_fix(c, iss) for c, iss in sorted(by_ch.items())])
        for c, t in res:
            t = _post_process(t)
            if t and len(t) >= len(chs[c - 1]) * 0.7:  # 守卫: 修短过多=烂改写,拒
                chs[c - 1] = t
                applied.append(c)
        # R12 逐项验收(团宠教训: ch32/57重写被'采用'却没消除互斥——采用守卫只查长度):
        # ISSUE_VERIFY 判未解决 → 带"上次未解决"前缀重试一次,仍未解决记残留
        sys_v, usr_v = prompts.ISSUE_VERIFY

        async def _judge(c: int, iss: str) -> bool:
            raw = await cli.complete("chunk_extract", sys_v,
                                     usr_v.format(issue=iss[:160], text=chs[c - 1][:8000]),
                                     json_mode=True, max_tokens=200, temperature=0.1)
            return (gate._safe_json(raw) or {}).get("resolved") is True
        for c in sorted(by_ch):                       # 守卫拒绝的重写=该章issue全部未净(盗墓ch31实证盲区)
            if c not in applied:
                unresolved += [f"第{c}章(重写被守卫拒):{iss[:30]}" for iss in by_ch[c]]
        pairs = [(c, iss) for c in applied for iss in by_ch[c]]
        verdicts = await asyncio.gather(*[_judge(c, iss) for c, iss in pairs])
        retry = [(c, iss) for (c, iss), ok in zip(pairs, verdicts) if not ok]
        if retry:
            re_res = await asyncio.gather(*[
                _fix(c, [f"(上一次修复未解决,这次必须彻底消除) {iss}"]) for c, iss in retry])
            for (c, iss), (_, t) in zip(retry, re_res):
                t = _post_process(t)
                if t and len(t) >= len(chs[c - 1]) * 0.7:
                    chs[c - 1] = t
            v2 = await asyncio.gather(*[_judge(c, iss) for c, iss in retry])
            unresolved = [f"第{c}章:{iss[:30]}" for (c, iss), ok in zip(retry, v2) if not ok]
        print(f"点修: 章级重写 {sorted(by_ch)} → 采用 {applied} → 验收未净 {unresolved or '无'}")

    # 4) 复检: 生死verify残留 / 结尾跳空 / 连续性advisory(fc代理) / 内容暗黑(R12,末世误放教训)
    issues2: list[str] = []
    if unresolved:
        issues2.append(f"点修验收未净{len(unresolved)}处:{unresolved[:2]}")
    rev2 = await _verified_revivals(cli, chs)
    if rev2:
        issues2.append(f"死人复活残留{len(rev2)}处:{[r['who'] for r in rev2]}")
    chs, dark_rep = await prose_continuity.content_filter(cli, chs)   # R12: 复检含内容扫描+净化
    if dark_rep.get("dark_ratio", 0) > 0.15:          # 点修语境收紧(末世0.05漏检了私刑弧的教训→
        issues2.append(f"暗黑残留(比{dark_rep['dark_ratio']})")       # 复检阈值比产线0.25更严)
    sys_ec, usr_ec = prompts.ENDING_CHECK
    prev_tail = chs[-2][-800:] if len(chs) >= 2 else "（无）"
    # 末章头+尾都喂: 点修把补演的对峙加在末章开头,只看尾2500字会误判'仍跳过'(实测FP)
    last = chs[-1]
    tail_blob = last if len(last) <= 4500 else (last[:2000] + "\n……(中略)……\n" + last[-2000:])
    ec = {}
    for t in range(3):
        raw = await cli.complete("chunk_extract", sys_ec,
                                 usr_ec.format(prev_tail=prev_tail, tail=tail_blob),
                                 json_mode=True, max_tokens=400, temperature=0.1 + 0.1 * t)
        ec = gate._safe_json(raw) or {}
        if "ok" in ec:
            break
    if ec.get("skipped") is True:
        issues2.append(f"预告事件仍被跳过({(ec.get('skipped_what') or '').strip()})")
    bible = {}
    bf = out_dir / "bible.json"
    if bf.exists():
        bible = json.loads(bf.read_text(encoding="utf-8"))
    final2 = _reassemble(preamble, headers, chs)
    if bible:
        # R10 复检补洞①: 3窗复检(首/中/尾各60k)——七零59.3误放实证: 只读前60k看不见ch18+的母亲三版
        n = len(final2)
        wins = [final2[:60000]]
        if n > 120000:
            mid = n // 2
            wins += [final2[mid - 30000:mid + 30000], final2[-60000:]]
        conts = await asyncio.gather(*[gate.continuity_check(cli, w, bible) for w in wins])
        from .produce import _verify_advisories      # R11 灰区判读(替代脆弱regex噪声过滤)
        adv_raw = [o for c in conts for o in (c.get("other_issues") or []) if o]
        adv2 = await _verify_advisories(cli, adv_raw, bible)
        if adv2:
            issues2.append(f"连续性advisory残留:{adv2[:3]}")
    # R10 复检补洞②: 原门里 fc 类问题若本次 targets 没覆盖到对应章 → 不放行(七零误放实证:
    # 原advisory'母亲死活矛盾'无章号没被修,浅复检随机通过)
    orig_adv = [a for a in (rep.get("advisory_issues") or []) if a and a != "无"]
    uncovered = []
    for a in orig_adv:
        m = _CH_IN_TEXT.search(str(a))
        if not m or int(m.group(1)) not in applied:
            uncovered.append(str(a)[:40])
    if uncovered and any("final_consistent" in str(s) for s in (rep.get("交付门") or [])):
        issues2.append(f"原advisory未被点修覆盖:{uncovered[:2]}")

    # 5) 写回 + 报告更新
    (out_dir / "final.md").write_text(final2, encoding="utf-8")
    deliverable = not issues2
    title = rep.get("title") or out_dir.name
    write_path, stale, book = _repair_delivery(out_dir, title, final2, deliverable)
    write_path.parent.mkdir(parents=True, exist_ok=True)
    write_path.write_text(book, encoding="utf-8")
    if stale and stale != write_path and stale.exists():   # 转可交付→清掉旧的 _rejected/ 同名件
        stale.unlink()
    rep.update({"deliverable": deliverable, "output_file": str(write_path),
                "交付门": ["点修后通过"] if deliverable else [f"点修后仍拦:{issues2}"],
                "点修": {"复活修复": [r["who"] for r in revived] or ["无"],
                         "章级重写采用": applied or ["无"], "复检残留": issues2 or ["无"],
                         "点修成本¥": round(cli.cost_cny, 2)}})
    (out_dir / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(f"点修复检: {'✅ 通过,已交付 ' + write_path.name if deliverable else '⛔ 仍拦: ' + '；'.join(issues2)}"
          f" | ¥{cli.cost_cny:.2f}")
    return rep


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(run(Path(sys.argv[1])))
