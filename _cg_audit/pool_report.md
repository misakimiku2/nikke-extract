# NIKKE CG 资源池盘点报告

生成时间: 2026-11-21 04:40:16  
范围: dp + core 池 catalog 中所有含 `eventscene` 的 bundle key（en/ja/ko/fd/saus 池已复核，均无 eventscene key）

## 1. 各池 bundle / 纹理统计

| 池 | 组 | 画质 | bundle 数 | 现可重建 |
|---|---|---|---|---|
| dp | scenariobackground | hd | 1237 | 1237 |
| dp | scenariobackground | sd | 1237 | 0 |
| dp | spineeventgame-voltroad（16 个异常前缀的真相） | hd | 8 | 8 |
| dp | spineeventgame-voltroad | sd | 8 | 0 |
| core | livewallpaperprefabs | 无 | 333 | 333 |
| core | spineeventscenesgroup | 无 | 113 | 113 |
| core | spineeventscenesgroup/eventtitle | 无 | 5 | 5 |

- **16 个异常前缀已查明**：`spineeventgame-voltroad(hd/sd)_assets_eventscene_voltroad_sd_01_XX_<32hex>.bundle`，是 VOLTROAD 活动小游戏的 spine CG（8 张），HD 8 张全部可重建，纹理名 `EventScene_voltroad_SD_01_XX`（1024x1024），8 张在 CG/ 中已全部存在。
- dp 池另有 **472 对不含 eventscene 的 scenariobackground(hd/sd)**（如 `assets_2025foolsday`、`assets_cherryblossom`），抽查 6 个确认内容是场景底图（`DiningRoom_n`、`Backstreet` 等，无 `EventScene_*` 纹理），不属于 CG 范畴，已排除。
- core 的 5 个 `eventtitle_*` 是活动标题 spine 动画（`EventTitle_*` 纹理），因组名含 `eventscene` 子串而被匹配，非 CG。
- **livewallpaperprefabs 333 个 bundle 内没有任何 `EventScene_*` 纹理**（全部是 `fx_*` 特效贴图），不产生 CG 导出物；其身份与 spine 组重叠 83 个，与 dp 组重叠 6 个，独立身份 244 个。
- 跨池 union：**1584 个 CG 身份**，其中 1245 个同时有 HD 与 SD 两份 bundle（sd-only 为 0）。
- 纹理命名映射（bundle 身份 → `EventScene_<身份>`）经 audit2 按前缀抽样（301 个前缀）+ audit4 全量重建 **1245/1245 全部一致**，无一例外。scenariobackground(hd) 与 voltroad(hd) 每个 bundle 恰好 1 张 EventScene_* 纹理。
- 可重建 HD 纹理尺寸分布：2048x2048 × 946、1024x1024 × 287、900x900 × 3、1024x1023 × 1、1024x1025 × 1、1024x761 × 1、1024x958 × 1、1024x1020 × 1、1024x835 × 1、1024x836 × 1、819x1024 × 1、1024x1115 × 1（共 1245 张）

## 2. HD/SD 覆盖验证结论

**结论：现有 CG 库没有被 SD 覆盖，库内不存在 SD 版本文件；`export_cg_v2.py` 的去重正则 bug 是真实存在的，但在本资源池状态下从未触发过覆盖。**

证据链：

1. **正则 bug 确认**：脚本用 `r"assets_((?:eventscene_).+?)_[0-9a-f]{40}\.bundle"` 匹配 40 位 hex，而实际 key 的尾缀是 **32 位** hex（如 `...absolute_01_1_410bf26bd3873e9b2d876c5c9a2ae69c.bundle`）。正则永不匹配 → 去重失效，HD/SD 全部进入处理队列，且排序 HD 在前、SD 在后——若两者都能重建，SD 必然后写覆盖 HD。
2. **SD 在当前池中完全不可重建**：1237 个 scenariobackground(sd) bundle 中，948 个的 chunk 在本地 store.cdb.idx 中 **0 命中**，289 个只命中一部分（普遍缺 1-4 个 chunk），0 个能完整重建。rebuild() 对缺 chunk 的 bundle 返回 `missing>0`，被 `missing or not bundle.startswith(b"UnityFS")` 拦截，不可能导出任何 SD 纹理。（voltroad(sd) 8 个同样 0 可重建。）
3. **全库尺寸比对（1245 个 HD bundle 全量重建 vs 磁盘 PNG）**：

   | 磁盘 vs HD 纹理 | 数量 | 判定 |
   |---|---|---|
   | 完全一致 | 1236 | 是 HD 版本 |
   | 磁盘更大 | 7 | spine 动态 CG 的 2048 渲染图（来自 spine 管线，不是 SD） |
   | 磁盘更小 | 1 | 见下方唯一例外 |
   | 本次新导出 | 1 | chap_22_06 |

4. **抽样直接证据（audit2，6 个有 HD bundle 对照的身份）**：

   | 身份 | HD bundle 纹理尺寸 | 磁盘 PNG 尺寸 | 同一 SD bundle 现状 |
   |---|---|---|---|
   | absolute_02_1 | 2048x2048 | 2048x2048 | 0/15 chunk 在本地，不可重建 |
   | beautyfullshot_01 | 1024x1024 | 1024x1024 | 12/13 chunk 在本地，不可重建 |
   | bluewaterisland_02 | 1024x1024 | 1024x1024 | 12/13 chunk 在本地，不可重建 |
   | acpufreeze_01_bg | 1024x1024 | 1024x1024 | 11/12 chunk 在本地，不可重建 |
   | voltroad_sd_01_01 | 1024x1024 | 1024x1024 | 0/3 chunk 在本地，不可重建 |
   | chap_02_after_01 | 1024x1024 | 2048x2048 | 8/9 chunk 在本地，不可重建 |

5. **旁证**：catalog 逐文件统计，1237 对 HD/SD 中 SD 的解包后体积全部 ≤ HD（中位数为 HD 的 25.2%，对应纹理 2048→1024），SD 不可能比 HD 大；旧导出清单 `CG/_清单/分类清单.csv`（1347 条）中 **没有任何重复 CG 名**，即当时的导出流程对每个纹理名只成功保存过一次。

6. **`分类清单.csv` 里 280 张 1024x1024 不是 SD**：全量重建证实其中被抽验的 `BeautyFullShot_01`、`BluewaterIsland_02`、`ACPUFreeze_01_bg` 等 HD bundle 纹理本身就是 1024x1024，磁盘文件与 HD 完全一致。

## 3. 缺失数量与分类分布

对比口径：catalog 1245 个可重建 HD 纹理名（+ spine 113 个身份）vs CG/ 全部非 `.spine.png` PNG 文件名（小写比对，共 1770 个 stem；spine 动态 CG 的 `<名>.png` 与 `<名>.spine.png` 均计为存在）。

- **静态 CG（dp scenariobackground hd + voltroad hd）**：发现缺失 1 张 → `EventScene_Chap_22_06`（02_主线剧情CG/第22章；该文件夹此前只有 spine 的 .atlas/.skel/.spine.png，缺渲染/静帧）。已由本次导出补齐，最终缺失 **0**。
- **voltroad 小游戏 CG**：8 张全部已存在，缺失 0。
- **spine 动态 CG**：113 个身份中 112 个已覆盖（CG/ 有 `<名>.png` 或 `.spine.png`），缺失 1 个：`EventScene_lycorisrecoi_minigame`（bundle `spineeventscenesgroup_assets_spine/events/eventscene_lycorisrecoi_minigame_cc8731f1e346eab64f4d23f1bbb7e29c.bundle`，core 池可重建）。**按任务要求未自行处理**，需走动态 CG 专用管线（该 bundle 含 TextAsset atlas/skel + 纹理；注意其 livewallpaper 版本里的纹理叫 `minigameCG` 而非 EventScene_*）。
- `missing_cgs.csv` 记录**发现时的缺口**（1 行：chap_22_06，已由本次导出补齐；若今天重跑比对则为 0 行）。导出明细见 extraction_log.md。

## 4. 提取统计

| 指标 | 数值 |
|---|---|
| 全量重建 HD bundle | 1245 / 1245 |
| 重建失败/不完整 | 0 |
| 纹理读取失败 | 0 |
| 命名映射不一致 | 0 |
| <512px 跳过 | 0 |
| 本次导出 | 1 |
| 因已存在跳过（未覆盖任何文件） | 0 |

导出明细：

| CG 名 | 落盘位置 | 尺寸 | 字节 | 噪声分 |
|---|---|---|---|---|
| EventScene_Chap_22_06 | `CG\02_主线剧情CG\第22章\EventScene_Chap_22_06.png` | 1024x1024 | 1691045 | 39.5 |


## 5. 可疑图清单

- **噪声分可疑（>50）**：无。噪声分按任务口径仅对本次新导出计算（1 张，39.5，正常插图范围 <45）；库内其余文件未重新计算噪声分，但其与 HD 纹理的尺寸一致性已全量核对（见第 2 节）。
- **尺寸可疑**：1 张 —— `CG/01_活动剧情CG/NoCallerID/EventScene_NoCallerID_01_bg.png`，磁盘 512x512，而 dp HD bundle 中同名纹理为 **2048x2048**（bundle `scenariobackground(hd)_assets_eventscene_nocallerid_01_bg_a451b970294fdaa9f497c7b9eb1b4764.bundle`，可重建）。
  辨析：**它不是 SD 版本**。其 SD bundle 解包体积恰为 HD 的 1/4（对应纹理应为 1024x1024 而非 512），且该 SD bundle 现在 0/16 chunk 在本地、无法重建；文件时间戳（Nov 13 18:04）与 `EventScene_NoCallerID_01.spine.png`、`EventScene_NoCallerID_01_ash.png` 同一分钟，是当时 spine 批处理导出的缩放/附属页。噪声分 21.5，内容正常非花屏。
  处理建议（未执行，遵守不覆盖原则）：若需要完整 HD，可用上述 HD bundle 重建后替换该文件。

## 6. 现有 CG 库中疑似 SD 版本的清单（应换成 HD）

**空。** 全库 1245 个 HD bundle 与磁盘一一比对后，1236 张完全一致、7 张是 spine 渲染图（更大属正常）、1 张 NoCallerID_01_bg 如上辨析为 spine 批次副产物（连 SD 的预期尺寸 1024 都不到）。没有发现任何一张文件符合 SD 导出的特征。`export_cg_v2.py` 的正则 bug 若在未来资源池补全 SD chunk 后重跑，会发生 SD 覆盖 HD（HD 排前、SD 排后写盘），建议把正则改为 `[0-9a-f]{32}` 并优先处理 HD 后跳过 SD。

## 附：资源池 chunk 库状态

- dp: store.cdb 14.79 GB / idx 7.32 MB，catalog 登记的 chunk 按 pak 1-16 分段；抽样显示 pak 5/6/11/12/14/16 仅部分在本地（如 pak 11 抽 200 条命中 73），SD 内容基本不在本地，属池内容不全而非索引损坏。
- core: store.cdb 7.32 GB，全部 451 个 eventscene bundle 可重建。
- 中间产物目录 `C:/nikke_temp/`（本次审计实际未产生落地中间文件，全部即时重建+流式读取）。

