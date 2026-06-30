# E3 验证块 B 档 + PreDraft Review v0 校准结果

> 2026-07-01 · B 档(2 本鲜书:反派记忆曝光=玄幻仙侠,冷战三年=现代言情)于 #1 引擎,折入 PreDraft Review v0 首次校准。
> 协议 60章/refine3/best_of1/--spine。原始产物 `output/validation/`(gitignored)。B jury 4 行已入 `assets/hfl.jsonl`(72→76)。

## 门判
| 本 | deliverable | grade | 拒因 |
|---|---|---|---|
| 反派记忆曝光 | False | A | 死人复活1 + 残缝10 |
| 冷战三年 | False | A | 残缝12 |
A+B 五本**全部门拒** → P(门放行)=0 → go/no-go=`low_power`(仍 0 本放行,假阳率无法测;门在这 5 本上全拒)。

## 双评委(B)
| 本 | Opus 总分 | GPT5.5 总分 | Δ | 承重 O/G |
|---|---|---|---|---|
| 反派记忆曝光 | 43.4 | 30.5 | 12.9 | 21/5 |
| 冷战三年 | 68.8 | 37.2 | **31.6** | 50/12 |
A+B 累积:偏置 opus−gpt55=**+25.2**,**deliver 同判率=100%**(5本两评委全 no),分歧桶 4/5。

## 🎯 PreDraft Review v0 首次校准(predraft_tabulate,n=2)

### ① DeepSeek 自审 vs 跨族(关键消融)
- **DeepSeek 自审召回近零**:两本只命中 `境界乱序`1 类(反派),冷战 `[]` 全漏。成本 ¥0.49。
- 跨族(Opus/GPT5.5)高召回。
- → **同族盲点坐实:DeepSeek 看不出自己 bible/plan 的结构硬伤 → 跨族审核必需。**

### ② 各 reviewer hard 精度/召回(n=2,方向性)
| reviewer | 画像 |
|---|---|
| **det** | 精度 1.0 / 窄召回(只 `章节复制`,靠 source_scene_index 重叠;P=1.0 R=0.5)= 最可靠硬拦源 |
| **deepseek** | 召回近零(只 `境界乱序`) |
| **opus(hard)** | `境界乱序` P=1.0;但 `修为倒退`/`DNA身世` 判 hard 却 jury 未兑现(P=0,误报) |
| **gpt55(hard)** | `境界乱序` P=1.0、`人设崩` P=1.0、`死人复活` P=0.5;`DNA身世`/`修为倒退` P=0(误报) |
| **crossfamily** | 同上(opus∪gpt55) |

### ③ block-precise 候选(codex 的"哪些 finding 精到可拦")
- **可作硬拦(B 向)**:`章节复制`(det,P=1.0)、`境界乱序`(全 reviewer P=1.0)、`人设崩`(gpt55 P=1.0)。
- **暂只配 warn 不 hard**:`DNA/身世`、`修为倒退`(跨族判 hard 却 jury 未兑现,过度硬拦)。

## 失败模式(A+B n=5)
**混名/认亲 + 章节复制 = 100%(5/5 全现)= 头号高频**,人设崩 80%,境界/复活 40%,性别错/DNA/现代腔 20%。

## 诚实边界
- **n=2(累积 5)→ 方向性,非精度阈值。** `DNA/身世`、`修为倒退` 的"误报"可能是**反事实盲**(jury 抽样漏看,非真假阳),需 C/D 累积区分。
- AI-only 无人锚;门仍 0 放行 → 假阳率/门-质量分离度 仍待门放行书。
- `validation_tabulate` 的"上游可拦率"在 B 是陈旧伪值(读 A 的 upstream/ 文件 vs A+B observed,口径错配);B 上游分析以 predraft_tabulate 为准。

## 指向
- v0 校准飞轮跑通,首批 block-precise 方向已出(章节复制/境界乱序 精,DNA身世/修为倒退 暂 warn)。
- 跨族必需已坐实(DeepSeek 自审不够)。
- 续 C 档(n=8):坐实精度 + 争取门放行书测假阳;精度够后 → PreDraft v1(候选工件→过审才起草)另立 spec。
