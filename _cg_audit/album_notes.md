# 图鉴/档案表分析笔记（AlbumInfo / AlbumResource / AlbumCategory / LiveWallpaper）

数据来源：`E:/test/nikke_extract/staticdata/` 下 4 个单表 mpk，全部为 ASCII token 流，无 EventScene_ 直接引用的表用 token 结构反推。清单数据见 `album_list.json`。

## 结论速览

| 表 | 实际用途 | 是否直接引用 CG 名 |
|---|---|---|
| AlbumCategoryTable | 档案馆分类标签页（主线/突发/活动/支线/小游戏/好感道具…） | 否 |
| AlbumInfoTable | 章节 + 据点建筑的"世界观图鉴"条目（img_album_chapterXX / img_album_structure_*） | 否 |
| AlbumResourceTable | **剧情回放档案**：每行一条可回放的对话组（d_main_* / event_* / sNNN_*…） | 否（引用对话组 ID，不是 CG 名） |
| LiveWallpaperTable | **游戏内 CG 画廊/动态壁纸**：每条 = 一张 EventScene CG + spine 变体 + BGM | 是（333 张 CG） |

也就是说：**"剧情图鉴"（档案馆回放清单）= AlbumResourceTable，按对话组归档；"CG 图鉴"（壁纸画廊）= LiveWallpaperTable，按 EventScene 名归档**。想拿"游戏内认可的 CG 总清单"，应取 LiveWallpaperTable，而不是 Album 三件套。

## AlbumCategoryTable.mpk（28.9KB，579 tokens，193 行）

行结构：`[Locale_System:ALBUM_CATEGORY_NAME_x, Locale_System:ALBUM_CATEGORY_DESC_x, 资源名]`。
193 行按 NAME 后缀分类：EVENT 131、MINIGAME 21、FAVORITEITEM 21、SUBQUEST 10、SIDESTORY 6、SUDDENSTORY 3、MAIN 1。
即档案馆每个活动/小游戏都有自己的分类页，不是简单的三大类。

## AlbumInfoTable.mpk（33KB，807 tokens，248 行）

行结构：`[Locale表名, Locale表名:key, img_album_*]`。
- 51 条章节条目：`Locale_Stage:chapter_name_00..23` + `img_album_chapterNN`（章节 21/22/23 追加在表尾，按版本顺序追加）。
- 197 条据点建筑条目：`Locale_Outpost:outpost_building_name_*` + `img_album_structure_*`（commandcenter、elevator、maidcafe、goddessofvictory…）。

它图鉴的是"章节标题 + 据点建筑"这类资料卡，与 EventScene CG 无关。

## AlbumResourceTable.mpk（452KB，10311 tokens，3437 行）

行结构（完全一致的三元组，无解析噪声）：`[Locale key 1, Locale key 2, 对话组ID]`。
组 ID 前缀分布：event_* 1955、d_main* 771、d_nikke* 349、treasurestory* 124、sNNN_* 94（支线）、d_contents* 61、re* 53、m* 20、1ann* 9、snowfall 1。

**与 6 个 Dialog 族 Group.csv 清单比对（容忍组 ID 尾部粘连的 1 个杂字符 + 去前导零两种变形）：3409/3437 行能对上现有对话组。** 剩 28 行对不上：
- 20 行 `m_subquest_*`（m_subquest_1101_s/_e …）：staticdata 里不存在 m_subquest 命名的 mpk；实际存在的是 `ScenarioDialogTable.d_subquest_*.mpk`（同为不在 Group.csv 的孤儿组），推测是同一批关卡改过名或档案用了旧前缀。
- 8 行 `1ann_mini_ending_*`（一周年小游戏各角色结局）：staticdata 只有 `EventScenarioDialogTable.1ann_mini_prologue.mpk`，ending 各组无 mpk，属于被移除/未随包内容。

注意：组 ID 尾部同样出现 1 字节粘连现象（`d_main_32_01 `、`d_main_N_N+/'/(/-/./*/#` 等），与 dialog mpk 锚点 token 的粘连同源，解析时需容忍。

## LiveWallpaperTable.mpk（100KB，2130 tokens，355 条）

行结构：`[Locale_LiveWallpaper:live_wallpaper_name_N, ...description_N, livewallpaper/<CG名>, <CG名>_mi, <CG名>_si, bgm_*]`。
- 355 条记录；333 条带 `livewallpaper/EventScene_*` 路径；每条带两个 spine 变体（`_mi`/`_si`，即动态壁纸的 spine 模型版本）与一条 BGM。
- 去重后 **333 个不同 CG 名**；其中 332 个同时出现在剧情/配置表的引用里，1 个独有（`EventScene_SnowfallOasis_02`，只在壁纸表中出现且无 path 字段，仅 _mi/_si 变体）。
- 22 条无 path 的记录大多是 700xxxx 段 ID 的占位空记录（仅 name/desc/bgm，无 CG）。
- 这 333 个 CG 名与导出库比对：大部分精确命中；约 910 个壁纸引用的 CG 名在 CG/ 导出库中没有对应静态图（见 missing_refs.csv），因为它们引用的是 spine 动态壁纸模型而非静态 PNG。

## 对建库的建议

1. "游戏内 CG 图鉴"清单 = LiveWallpaperTable 的 333 个 cg stem + 各自 name/desc 本地化 key（zh-CN 在 Locale_LiveWallpaper 表，decrypted 中应有对应 .dec）。
2. 剧情回放档案清单 = AlbumResourceTable 的 3437 行（含每行的本地化 key），可直接当"剧情目录"使用，覆盖面比 6 个 Group.csv 并集略广（多出 d_subquest/m_subquest、1ann_mini 等）。
3. Album 三件套不含任何 CG 级信息，做 CG 索引时不需要解析它们。
