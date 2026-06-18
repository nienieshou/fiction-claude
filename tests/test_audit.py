"""audit.py 纯函数:broken_prose 合成用例 + _power_rank/power_order_from_bible。零 API。
(原 scripts/_test_broken_prose.py + _test_r13_units #6 迁入;file-dependent 部分略去保持可移植)"""
from hiki.audit import broken_prose, _power_rank, power_order_from_bible, check_places, enrich_places, reconcile_revival


# ---------- 地点漂移 advisory(Plan-地点槽) ----------
_BIBLE_P = {"places": [{"name": "大王村", "aliases": ["王村"]}, {"name": "青云宗"}]}


def test_check_places_flags_offcanon():
    # 非 canon 地点 → 记一条漂移;canon(含子串/别名)不报
    scenes = [{"location": "大王村村口"},      # canon 子串 → 不报
              {"location": "王村"},             # 别名 → 不报
              {"location": "京城皇宫"},         # 非 canon → 报
              {"location": ""}]                 # 缺失 → 不算漂移
    drift = check_places(_BIBLE_P, scenes)
    assert any("京城皇宫" in d for d in drift)
    assert len(drift) == 1, drift


def test_check_places_empty_when_no_canon():
    # bible 无 places(现言/无明确地理)→ 不报,免整类误杀
    assert check_places({"places": []}, [{"location": "随便哪"}]) == []


def test_check_places_whitelists_nonphysical():
    # (a) 梦境/回忆/幻境等非物理场所不算漂移(它们本不该进地名表)
    scenes = [{"location": "梦境"}, {"location": "回忆中的桑府"}, {"location": "识海"}]
    assert check_places(_BIBLE_P, scenes) == []


def test_enrich_places_adds_recurring_offcanon():
    # (b) plan 发现的、复现≥2 的物理新地名回灌 canon;梦境/canon/单次/过渡串 不收
    bible = {"places": [{"name": "大王村"}]}
    scenes = [{"location": "宝华峰"}, {"location": "宝华峰"},   # 复现物理新地名 → 收
              {"location": "梦境"}, {"location": "梦境"},        # 非物理 → 不收
              {"location": "大王村"},                            # 已 canon → 不收
              {"location": "石山"},                              # 单次 → 不收
              {"location": "孤竹峰→城外密林"}, {"location": "孤竹峰→城外密林"}]  # 过渡串 → 不收
    added = enrich_places(bible, scenes, min_count=2)
    assert added == ["宝华峰"]
    names = [p["name"] for p in bible["places"]]
    assert "宝华峰" in names
    # 回灌后该地名不再被判漂移
    assert check_places(bible, [{"location": "宝华峰祭坛"}]) == []


def test_enrich_places_noop_without_canon():
    # 无 canon 地理体系书不强行造地点
    b = {"places": []}
    assert enrich_places(b, [{"location": "某地"}, {"location": "某地"}]) == []


def test_broken_prose_synthetic():
    chs = ["他抬起手,正要说话,却发现整个广场都安静了下来,所有人的目光都集中在那道身影上,",
           "狼首异/咔嚓!巨响震彻全场。\n正常段落在这里结束。",
           "正常的一章。对话也正常。"]
    hits = broken_prose(chs)
    assert any("段尾残句" in h and "第1章" in h for h in hits), hits
    assert any("斜杠拼接" in h and "第2章" in h for h in hits), hits
    assert not any("第3章" in h for h in hits), hits


def test_power_rank_paren_not_hijacked():
    # R13c 52处钉反根因: 括号内'渡劫'不得把'练气'劫持到 rank10
    assert _power_rank("练气大圆满（渡劫中）") == 1
    assert _power_rank("练气圆满") == 1                # 绞丝旁识别
    assert _power_rank("筑基初期") > _power_rank("练气大圆满（渡劫中）")


def test_power_order_from_bible():
    assert power_order_from_bible({"escalation_ladder": "练气→筑基→金丹，赌注…"}) == ["练气", "筑基", "金丹"]
    assert power_order_from_bible({"escalation_ladder": "瞎写的"}) is None   # 解析不出→退默认梯


def test_reconcile_revival():
    la = {"桑念": {"fate": "dies_returns"}, "袁麟": {"fate": "dies_final"},
          "甲": {"fate": "fake_death"}}
    assert reconcile_revival(la, "桑念") == "advisory"   # 源书确有复活 → 放行(门误杀那类)
    assert reconcile_revival(la, "甲") == "advisory"     # 假死归来 → 放行
    assert reconcile_revival(la, "袁麟") == "gate"        # 源书永久死却被写活 → 仍拦(真矛盾)
    assert reconcile_revival(la, "无名") == "gate"        # 无弧 → 保守拦(沿用现行,绝不放过未知)
    assert reconcile_revival({}, "谁") == "gate"          # 无 life_arcs(老书/抽取失败)→ 保守拦
