# Dialog mpk 布局笔记：CG token 与行锚点/台词 key 的位置关系（任务6）

样本与全量统计：6 个 Dialog 族全部 8473 个组文件重扫；抽查 7 个代表组（主线×2、活动×2、支线、咨询、个人剧情）。全量统计来自对全部 406 个含 CG 组文件的重解析。

## 结论：转场标记可行，且比现有 build_cg_index.py 的假设更强

1. **CG token 相对台词 key 的位置 100% 稳定**：全量 1756 条含 CG 行中，CG token **全部**位于 `Locale_XXX:台词key` 之后（after=1756 / before=0 / same=0）。也就是说"第几行台词切到哪张 CG"可以直接判定：该行 segment 里 locale key 之后的第一个 `EventScene_*` 即本行 CG。
2. **行号单调**：578 个含 CG 组的 CG 行号全部非递减（含幽灵锚点也无乱序）。行号即可作时间轴。
3. **CG 持续语义成立**：没有 CG token 的行沿用上一张 CG（如 d_main_01_01_s 全场只用 L2 的 `EventScene_Main_01_01_bg`）。1756 行中有 205 行是"连续行重复同一 CG"（相邻两行带相同 CG token），做时间轴时这两类都要处理：带 token=切换点，无 token=延续。
4. 一行最多 2 个不同 CG（1742 行 1 个，14 行 2 个——常见为 `XXX` + `XXX_bg` 同屏：前景立绘 CG + 背景 CG）。

## 行内字段结构（实测序）

```
[组_行号锚点] [组名] [说话人charID(可省)] [charID重复或省略]
[Locale_XXX:台词key]
[左侧立绘ID][表情] [右侧立绘ID][表情]   ← 可重复多组
[背景名]                                 ← 可选
[EventScene_CG名]                        ← 本行的 CG（0-2 个）
[位移/透明度参数]                         ← 如 XS_150、black、none、Low_2
[bgm_*/sfx_*]                            ← 可选，切换 BGM/音效
```

- 台词 key 前缀按族不同：主线/多数活动=`Locale_MainScenario`，部分活动/小游戏文本=`Locale_SubScenario`，支线=`Locale_SideStory`，个人剧情=`Locale_NikkeEpisode`，咨询=`Locale_Counseling`。story_refs.json 1756 行的实际分布：MainScenario 1512、SubScenario 141、SideStory 92、NikkeEpisode 11（咨询 0 行，因其无 CG）。
- 说话人 charID 也可能是 `Monologue`/`Self`（旁白/指挥官），旁白行无立绘字段。
- 立绘 token（如 `marian_event_01_01`、`helm_s`）不是 CG，别混进 CG 列表。

## 锚点格式细节（关键坑）

锚点 token = `<组名>_<行号>`，但有三种变体，**现有 build_cg_index.py 的 `^{group}_(\d+)$` 会漏掉后两种**：
1. **粘连字节**：840 个 EventScenarioDialogTable 文件的锚点尾部粘着 1 个任意可打印字符（`event_bluewaterisland1_04_e_1T`、`..._1q`、`..._1Y`，57 种字符、70864 处，同一文件内字符一致）。应改为 `^{group}_(\d+).?$`。
2. **去前导零**：ScenarioDialogTable 第 26 章等文件的锚点是 `d_main_26_4_1`（组名却是 `d_main_26_04`），台词 key 也用 `d_main_26_4_1`。需同时尝试去零前缀（去零形式无组名冲突，已验证 0 冲突）。
3. **"下一行指针"幽灵锚点**：行记录尾部常带下一行（或自身）的锚点 token，会产生只有 1 个 token 的幽灵 segment；因无 CG/无 locale key 自然被跳过，但解析时不要把"锚点唯一"当作假设。

修复 1+2 后，6 族内**全部** 1940 处 raw EventScene 出现中 1909 处落在行 segment 内（其余 31 处为 raw 正则吃到 Locale key 里的子串，如 `Locale_Event:EventScene_snowfalloasis_01_1`），token 级 CG 与行级提取完全对账（gap=0）。

## 真实样例（截取）

**主线 d_main_01_01_s**（`ScenarioDialogTable.d_main_01_01_s.mpk`）：
```
L1: d_main_01_01_s_1 | d_main_01_01_s | marian | marian | Locale_MainScenario:d_main_01_01_s_1 | none | bgm_prologue
L2: d_main_01_01_s_2 | d_main_01_01_s | marian | marian | Locale_MainScenario:d_main_01_01_s_2 | marian_event_01 | event | idle | EventScene_Main_01_01_bg | marian_event_01_01 | marian_event_01_01 | fx_vn_fire_ptc_01 | fx_vn_fire_ptc_01 | fx_vn_spark | fx_vn_spark
L3: d_main_01_01_s_3 | ... | Locale_MainScenario:d_main_01_01_s_3 | event | idle | marian_event_01_01 | marian_event_01_01     ← 无 CG，沿用 L2 背景
```

**活动 event_seayouagain2_05_s**（粘连锚点 `..._1Y`；CG 出现在第 1 行台词）：
```
L1: event_seayouagain2_05_s_1Y | event_seayouagain2_05_s | neon_s | neon | Locale_MainScenario:event_seayouagain2_05_s_1 | helm_s | idle | anis_s | angry | neon_s | surprise | EventScene_SeaYouAgain_01_1 | XS_150 | bgm_emergency
L2: event_seayouagain2_05_s_2Y | ... | Locale_MainScenario:event_seayouagain2_05_s_2 | idle | angry | surprise | XS_150 | XS_150
```

**支线 s001_01**（背景/立绘/情绪字段齐备）：
```
L1: s001_01_1 | s001_01 | snowwhite | snowwhite | Locale_SideStory:s001_01_1 | snowwhite | pain | rapunzel | hongryeon | marian_p | IceLand_02 | bgm_story_thepilgrimacv
L2: s001_01_2 | s001_01 | hongryeon | hongryeon | Locale_SideStory:s001_01_2 | pain | 1315 | 1315      ← 1315=NPC编号式立绘
```

**咨询 d_counseling_admi_01**（无任何 EventScene CG；结构=背景+好感参数+bgm）：
```
L1: d_counseling_admi_01_1 | d_counseling_admi_01 | admi | admi | Locale_Counseling:d_counseling_admi_01_1 | admi | idle | CommanderRoom | XS_10 | XS_10 | bgm_story_backtonormal
（L3 之后可见幽灵锚点：`d_counseling_admi_01_5` 单独成段，随后才是 L4 真实记录）
```

## 电影/视频引用

- **对话表里没有 .mp4/URL**。6 族全部 token 中电影相关只有 `movieeffect`（2 处，`AttractiveScenarioDialogTable.d_nikke_vesti_04.mpk` 的背景字段位置，语义=该行播放影片特效）。
- **真正的视频表是 `ScenarioMovieTable.mpk`**（单表，1088 tokens）：行=`[key_语言, key, mp4 URL, srt URL]`，按语言（en/ja/ko/zh-TW/zh-CN/de/th/fr/es）×影片列清单，共 279 条 mp4 路径、79 部不同影片（`ch01_end`…`ch49_end` 章末动画、`opening_pv01` 等），全部托管在 `https://cloud.nikke-kr.com/media/...`。主线"章末动画"由此表驱动，与 CG 无关。
- 结论：做"CG 一切"索引时不需要碰视频，除非想给章末动画单独建索引（数据源就是 ScenarioMovieTable）。

## BGM / 音效 / 背景切换 token

- `bgm_*`：6 族共出现 322 种不同 BGM 名，最高频 `bgm_story_backtonormal`（3200 次，咨询默认曲）。bgm token 与台词行同段出现，位置在 CG/参数之后，**可直接当"该行切换 BGM"标记**。
- `sfx_*`：1965 种音效名，同样在行内（如 `sfx_scn_aedshock`、`sfx_scn_groundbreak`）。
- `fx_vn_*`：屏幕特效（`fx_vn_fire_ptc_01`、`fx_vn_spark`），与 ScenarioPositionSettingTable 里的 `fx_EventScene_*`（CG 坐标特效挂点）呼应。
- **背景切换**：不是 `bg_` 前缀，而是直接一个背景资源名 token（`Desert_05`、`IceLand_02`、`CommanderRoom`、`RuinIndoor`、`CountryVillage_d`、`LogHouseIn_d`、`CoinRushMainHall`、`Theater`、`black`（黑屏转场）…），通常位于立绘字段之后、CG 之前；`black | black` 成对出现=淡入淡出转场。
- `XS_10/100/130/150` 等数字对、`Low_1/Low_2`、`none`：行尾参数字段（位移/透明度/层级类），含义未定但位置固定，可整体保留。
- 另有 NPC 立绘用纯数字命名（`1315`）与颜色后缀粘连（`10ffffff`、`black333333`）——同样是字节粘连现象，解析时注意。

## 对 build_cg_index.py 的改进建议（不改现有文件，仅记录）

1. 锚点正则改 `^{group}_(\d+).?$` 并尝试去零前缀 → 可多覆盖 79 个活动组 + 3 个主线 26 章组（约 227 条 CG 台词行）。
2. 或phans：`d_ex_redash_*`（21 个主线组）、29 个活动组、咨询 villain 组 20 个、`scenario_5001_1` 等不在 Group.csv 的 mpk 目前被跳过；本次审计中含 CG 的孤儿组已记录在 dialog_families.csv，可按需并入索引。
3. `AttractiveCounselDialogTable` 与 `SideStorySpotDialogTable` 确认 0 CG 引用，无需纳入 CG 索引（但咨询表结构里 bgm/背景/好感参数齐全，做剧情文本索引时可用同一套解析）。
