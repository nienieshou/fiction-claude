"""标准信号向量(冻结 schema)——测量飞轮的止血带。

背景(相0 标定实证, 2026-06-22): human-eval-5/editor-eval-1/-2 三批人评各记**不同**
机器信号(eval-5 几乎只有 grade;eval-1 有章缝/重演/暗黑;eval-2 才有代入感分),三批
共有信号寥寥→跨批无法合池标定"机器信号→人评质量"的代理。破采集是自伤。

止血: 每本生产 report 落同一套 `signals` 向量;每条 hfl 人评行直接拷 `report["signals"]`。
之后所有批次可合池,质量代理(quality-first 10k 的地基)才能随数据长大。

**冻结纪律**: 新增信号只许**追加新键**(默认 None 占位),严禁改名/删除既有键,否则破合池。
改动既有语义须 bump SIGNAL_SCHEMA_VERSION。
"""

SIGNAL_SCHEMA_VERSION = 1


def build_signal_vector(*, deliverable, grade, immersion_score, reenact_hits,
                        seam_detected, seam_residual, dark_ratio,
                        spine_num_contra, spine_id_contra, ft_revival_residual,
                        too_short_chapters, final_consistent, intra_repeat_chapters,
                        early_repeat=None, opening_overload=None) -> dict:
    """组装冻结信号向量(纯函数, 0 LLM)。kw-only 防调用处错位。

    相0 实测相关(vs 人承重): 章缝检出 r=-0.50(最强), 代入感分 r=+0.45(仅低端可靠),
    控制面重演 r=+0.14(≈0, 不预测)。现有信号弱→early_repeat/opening_overload 两个
    待建检测器是补强方向(既是质量门, 又是代理新特征)。
    """
    return {
        "schema_version": SIGNAL_SCHEMA_VERSION,
        "deliverable": bool(deliverable),
        "grade": grade,                            # S/A/B/C/D/Q/X
        "opening_immersion": immersion_score,      # 代入感分 0-100(None=审计失败)
        "reenact_hits": reenact_hits,              # 控制面重演处数
        "seam_detected": seam_detected,            # 章缝检出(修复前; 最强单预测)
        "seam_residual": seam_residual,            # 残缝(修复后未采用)
        "dark_ratio": dark_ratio,                  # 暗黑饱和比
        "spine_num_contra": spine_num_contra,      # Spine 数值真矛盾
        "spine_id_contra": spine_id_contra,        # Spine 身份真矛盾
        "ft_revival_residual": ft_revival_residual,  # 事实表死人复活残留(verify后)
        "too_short_chapters": too_short_chapters,  # 过短<70% 章数
        "final_consistent": bool(final_consistent),
        "intra_repeat_chapters": intra_repeat_chapters,  # 章内双版本章数
        # —— 待建检测器(相1)占位: 建好填, 否则 None ——
        "early_repeat": early_repeat,              # 早段(ch1-2)重复召回
        "opening_overload": opening_overload,      # 开篇信息过载
    }
