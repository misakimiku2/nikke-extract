# NIKKE 剧情 / CG 提取工程

本地离线解包《胜利女神：NIKKE》的剧情文本、静态 CG、Spine 动态 CG，并生成
「剧情 ↔ CG」对照索引。全部数据来自本机客户端，不联网下载。

最后整理：2026-11-21

> **2026-11-21 CG 全量核对版**：静态 CG 对账到 catalog（可重建 HD 1245/1245 全入库），
> 剧情↔CG 索引扩到主线/活动/个人/支线故事全部 4 类 Dialog 族，CG 转场标记直接写进
> 剧情文本（Markdown `🖼 CG` + JSON 行级 `cg` 字段）；新增 `CG剧情档案.csv`、
> `图鉴清单.csv`、`剧情动画清单.csv` 三份衍生索引。详见下方「CG 转场标记」与「已知缺口」。

> **仓库范围**：本仓库只托管工具链代码（`scripts/`）与索引产物（`CG索引/` 下的
> CSV/JSON）。解包得到的游戏素材——CG 图集、剧情文本、静态表、解密数据库，
> 合计约 14 GB——属于游戏版权内容，且远超仓库合理体积，一律不纳入版本控制，
> 具体排除规则见 `.gitignore`。按下方「数据链路」在本机跑一遍即可重新生成。

> **环境要求**：Python 3.10+。脚本会把自身所在的 `scripts/` 父目录当作工程根
> （`BASE`），因此 clone 到任何路径都能直接运行；需要把代码与数据分开放时，
> 用环境变量 `NIKKE_BASE` 指定数据根目录。

## 目录结构

| 目录 | 内容 |
|---|---|
| `CG/` | **成品图库**。按 `01_活动剧情CG / 02_主线剧情CG / 03_支线剧情CG / 04_角色过场 / 05_其他动态CG / 06_剧情背景` 分类；`_清单/` 里是分类汇总与逐张清单 |
| `CG索引/` | 剧情 ↔ CG 对照索引（CSV/JSON）、单文件画廊 `剧情CG索引.html`、`缩略图/`、`图文版/` 样例 |
| `动态CG/` | `runtime/`（Node 渲染栈，静态合成图用）、`查看器.html`（单文件播放器）、模型总表。`动图/` 的离线合成 WebP 已下线（见下） |
| `主线剧情/` | 主线 1–50 章 Markdown + 全量 JSON |
| `其他剧情/` | 活动、支线、个人、咨询等剧情文本（`活动剧情/Marian/` 是最新活动） |
| `scripts/` | 在用的脚本（见下）；`scripts/legacy/` 是被取代的一次性脚本，仅留档 |
| `data_raw/` | 原始输入：`StaticData.zip`、`_salt1.bin`、`_salt2.bin`、`_nikke_packinfo.bin` |
| `staging/` | 角色素材与动态 CG 暂存区（约 3.9 GB）。`spine_stand/` 角色站姿 Spine 模型（777 组）、`char_render/` 站姿渲染的 2048² 透明底图（565 张）、`spine_char/` 角色技能立绘（630 组 `*_skillcut`）——**这三类是网站角色页的唯一数据源，删了要重新解包**；`spine/` 才是动态 CG 暂存，由 `reorganize_cg.py` 并入 `CG/` |
| `staticdata/` | 解密并展开的静态表（约 314 MB） |
| `decrypted/` | 解密后的本地化 SQLite（台词、角色名等，约 409 MB） |
| `catalogs/` | 资源 catalog 解密缓存（导出 CG 时用，约 103 MB，可重建） |

## 数据链路

```
StaticData.pack（客户端缓存）
        │ scripts/decrypt.py
        ├── data_raw/StaticData.zip
        └── staticdata/*.mpk / *.csv
                │ export_mainstory.py / export_rest.py / export_story_v2.py
                │   （行级解析：说话人 + cg 转场字段，cg_refs.py 共用）
                └── 主线剧情/、其他剧情/

com.shiftup.patch（游戏资源池，14.8 GB）
        │ export_cg_v2.py     catalog.ndb + store.cdb → 静态 CG（只补缺不覆盖）
        │ export_spine_cg.py  spineeventscenesgroup → .atlas/.skel/图集
        └── CG/
                │ build_cg_index.py   消费剧情 JSON 的 cg 字段（单一事实源）
                └── CG索引/剧情CG对照索引.csv/json + CG剧情档案.csv
                          + 图鉴清单.csv + 剧情动画清单.csv
```

## 常用命令（在仓库根目录运行）

```bash
python scripts/preflight.py                   # 更新前自检：客户端路径 / catalog / 缓存
python scripts/decrypt.py                     # 解 StaticData.pack → staticdata/
python scripts/decrypt_nkdb_batch.py          # 批量解 NKDB（台词库、catalog）→ decrypted/
python scripts/unpack_staticdata.py           # 只从 data_raw/StaticData.zip 重建 staticdata/（不需要游戏）
python scripts/export_mainstory.py            # 主线 50 章
python scripts/export_rest.py                 # 活动/支线/个人/咨询
python scripts/export_char_stats.py           # 角色基础属性（HP/ATK/DEF）→ staging/
python scripts/export_story_v2.py             # 最新活动（玛丽安）文本
python scripts/export_fadingaffection.py      # FIRST AFFECTION 小游戏分支图（EventTextAdvPlus 静态表）→ staging/ + nikke-web/public/data/
python scripts/export_movies.py               # ScenarioMovieTable → CG索引/剧情动画清单.csv
python scripts/export_bg.py                   # 纯剧情背景（scenariobackground 非 eventscene）→ CG/06_剧情背景/
python scripts/export_bg_map.py               # 动态CG↔背景对照表 → CG索引/动态CG背景对照.csv
python scripts/export_cg_v2.py                # 静态 CG（直接写入 CG/<分类>/；幂等：已有成品跳过，只补缺失）
python scripts/export_spine_cg.py             # Spine 动态 CG → staging/spine
python scripts/reorganize_cg.py               # staging → CG/，改名图集并渲染插画
python scripts/build_cg_index.py              # 重建剧情↔CG 索引（加 --stats 只看统计）
python scripts/build_cg_gallery.py            # 重建缩略图与单文件画廊
python scripts/build_spine_viewer.py          # 重建动态 CG 查看器
python build/build_images.py                # 重转网页三档图片（CG/ 改动后跑）
python build/build_spine_models.py --force  # 重建网页实时模型图集（atlas/skel/贴图）
python scripts/reorganize_cg.py --dry-run     # 预览 CG 目录重排（正常情况不需要再跑）
```

## 角色基础属性表（2026-11-17 逆向）

角色三围（HP / 攻击 / 防御）来自下面两张表，都是**定长二进制记录**、无字段名，
字段顺序靠逆向确定：

| 表 | 记录布局 | 作用 |
|---|---|---|
| `CharacterStatTable.mpk` | `4B 记录数 + 每条 41B`（`1B flag=0x09` + 10×int32） | 54 个模板 × 1400 级的数值曲线 |
| `CharacterTable.mpk` | 变长：`rowid` + name/desc 字符串字段 + 32 个 int32 + cv | 每个角色的稀有度、职业、武器 → 模板键 |

`CharacterStatTable` 每行：`[0]=组合ID [1]=模板键 [2]=等级 [3]=HP [4]=保留 [5]=ATK [6]=DEF`。

**模板键编码**：`稀有度×1000 + 职业×100 + 武器`

- 稀有度：`1=R`、`3=SR`、`5=SSR`
- 职业：`1=火力型`、`2=防御型`、`3=辅助型`
- 武器：`1=ar`、`2=sr`、`3=smg`、`4=sg`、`5=rl`、`6=mg`

例：拉毗 = SR + 火力 + AR → `3101`；爱丽丝 = SSR + 火力 + 狙击 → `5102`。
**武器只影响 DEF，HP 与 ATK 只由稀有度和职业决定**。

`CharacterTable` 的 32 列中，`[0]=角色 id`、`[4]=稀有度`、`[7]=模板键` 是需要的部分；
其余多为技能 id、初始装备、展示参数。字符串字段用负 tag 标记（旧 schema `-25/-23`、
新 schema `-26/-24`，payload 为 `uint32 长度 + utf-8`），解析时跳过即可。

输出（`python scripts/export_char_stats.py`）：

```
staging/char_stats.json    212 个可战斗角色：模板/稀有度/职业/武器 + 16 个关键等级的数值
staging/stat_curves.json   54 模板 × 1400 级完整曲线（数组形式，索引 = 等级-1）
staging/char_stats.csv     同样内容的表格版，方便直接看
```

覆盖：2040 条记录 / 212 个角色（178 SSR、21 SR、13 R）。`characters.json` 里另外
100 个角色没有战斗数据（剧情 NPC）；老角色在表尾部使用旧 schema，同一条解析路径可读。

表中是**裸装基础值**，不含突破、好感、装备、魔方加成。突破按全 SSR 通用公式叠加：
每次升星 `HP×1.02+3000`、`ATK×1.02+20`、`DEF×1.02+100`；核心强化每次再 `×1.02`。

## 魔方（Harmony Cube）表（2026-11-17 逆向）

| 表 | 记录布局 | 作用 |
|---|---|---|
| `ItemHarmonyCubeLevelTable.mpk` | `4B 记录数 + 每条 79B` | 270 条 = 18 魔方 × 15 级 |
| `ItemHarmonyCubeTable.mpk` | 变长（同 CharacterTable 的字符串 tag 结构） | 18 个魔方的 id 与本地化 key |

`ItemHarmonyCubeLevelTable` 每条：`flag(0x09)` + `rowid` + `cubeId` + `level`，
偏移 `32` 是技能 id（`7020001`… 与魔方一一对应）、`40` 是升级信用点、`44` 是插槽数，
**尾部 27 字节是 3 组 `[0x02][key:u32][value:u32]`**，`key 1=ATK、3=DEF、2=HP`。

关键结论：**这 15 级的三围加成对 18 种魔方完全一致**（Lv1 `390/78/11,800` →
Lv15 `2,780/552/83,400`），魔方之间的差异全在各自的技能效果上，而技能数值不在
staticdata 里（`SkillInfoTable` / `StateEffectTable` 中相关条目只有 0/1 开关），
所以 `export_cubes.py` 的技能档位取自社区实测表，规律是：
**Lv1-2 / Lv3-6 / Lv7-15 三档，约为满值的 1/2、3/4、1 倍**。

18 种魔方里只有 `Vigor（最大体力+9.69%）` 与 `Endurance（防御力+48.45%）` 会作用到
三围面板，其余（装弹速度、弹药返还、蓄力速度…）属于战斗属性。

输出（`python scripts/export_cubes.py`）：

```
staging/cube_stats.json   15 级三围加成 + 插槽数 + 18 个魔方的效果档位 + 通用优越代码伤害
```

## 珍藏品 / 收集品（Favorite Item）表（2026-11-18 逆向）

| 表 | 记录布局 | 作用 |
|---|---|---|
| `FavoriteItemTable.mpk` | 变长记录（6 职业 × R/SR 共 12 条主记录） | 珍藏品本体：名称 key、图标 key、职业 |
| `FavoriteItemLevelTable.mpk` | `4B 记录数 + 每条 62B`（255 条） | 每级三围：12 款 × 16 级(0-15) + 21 技能组 × 3 级 |
| `FavoriteItemExpTable.mpk` 等 | 变长 | 升级经验 / 概率 / 任务（数值未用于前端） |

**珍藏品 = 收集品娃娃**：6 职业各有 R 版（`_00`）与 SR 限量版（`_01`），
按武器类型分为步枪/机枪/发射器/霰弹/冲锋/狙击，名称如「料理指挥官娃娃」。
本体记录的 `rowid`（100101、100102…）同时是等级表的关联键 `fid`（偏移 5 的 u32）。

`FavoriteItemLevelTable` 定长 62B，关键字段（`struct.unpack_from('<I', seg, off)`）：
`off 1 = rowid`、`off 5 = fid`、`off 13 = 等级(0-15)`、
**`off 26 = ATK`、`off 35 = DEF`、`off 44 = HP`**。

数值经社区（nikke.gg / gamekee）交叉验证：

| | HP | ATK | DEF |
|---|---|---|---|
| R Lv15 | 147,250 | 4,736 | 1,002 |
| SR Lv0 | 94,000 | 3,029 | 638 |
| SR Lv15 | 301,800 | 9,688 | 2,058 |

R/SR 的 16 级三围曲线一致，仅满值不同。珍藏品的百分比技能效果（SR 的
`防御▲37% / 受伤▼17% / 掩体HP▲30%` 等，按职业而异）是战斗属性，不进入三围面板，
且数值不在 staticdata 里，前端按职业常量单独展示。

图标在 dp 池 `icons-favoriteitem(hd)`：`si_favoriteitem_<职业>_00`（R/SR 共用），
导出用 `python nikke-web/build/export_ui_icons.py "icons-favoriteitem(hd)" --out favoriteicon --only <keys>`。

输出（`python scripts/export_favorites.py`）：

```
staging/favorite_stats.json   12 款珍藏品 × 16 级三围 + 名称/职业/图标 key
```

## FIRST AFFECTION 小游戏（EventTextAdvPlus）2026-11-22 逆向

`event_firstaffection`（FADING AFFECTION）的小游戏本体**不在** `EventScenarioDialog` 里，
而在 `EventTextAdvPlus*.mpk` 八张静态表中。内部路线 3 条：玛丽亚 / 玛丽安 / 7号；
265 个页面、172 个选项、35 个结局（61xx=死亡、62xx、63xx、71xx/72xx=隐藏、8xxx/9xxx=TRUE）。

MPK 记录布局（逆向自字节，通用解析器见 `export_fadingaffection.py`）：

| 部分 | 布局 |
|---|---|
| 文件头 | `u32 记录数` |
| 记录头 | `u8 flag` + `i32 id` + `i32 页号/版本`（因表而异）+ `i32 表常量 83501`（该活动专有） |
| 字段 | 紧密排列：`i32 >= 0` 为整数；`i32 < 0` 为字符串 tag，紧跟 `u32 长度 + UTF-8` |

关键 tag：`-37` 选项文本、`-42` 选项提示、`-34` 页面正文、`-32/-41` 页面 CG、
`-26/-25` BGM、`-20` 日期、`-41/-48/-45` 路线名/介绍。跳转页号以**左移 1~2 字节**
的形式存放（如 `0x17d50000 = 6101<<16`），所以按「每个字节偏移」扫 i32 才能稳定还原。

页面 CG 按结局类型分 tag：`-32` 普通 / `-41` DeathEnd / `-46` CorruptionEnd /
`-42` HiddenEnd / `-40` TrueEnd（只取 `-32` 会丢掉大部分结局 CG）。

`EventTextAdvPlusLootItemTable.mpk`（flag=0x08，另需单独识别）里的 `saveitem` 就是
死亡后留下的「已储存的记忆」——40 条，名字/描述取自 Locale_Event，与结局按
`61xx -> 记忆 1-xx`、`62xx -> 记忆 2-xx` 对应；选项的 `_hint` 文本正是这些记忆的提示。

状态槽（体力/粮食/侵蚀）初值与上限来自 Manager 表（体力/粮食各 10，侵蚀 0）。
**注意**：选项的状态消耗目前是按选项文本关键词推导的（吃/跑/躲/黑暗等），
属于还原度近似，不是从静态表直接逆向出的数值；界面会明示每次消耗，
并在状态不足时禁用选项。小游戏没有专用背景表，按地点选用 `CG/06_剧情背景` 里
已有的场景板（旧市区=DestroyedStreet、湖=Lake、新市区=City_d）。

输出（`python scripts/export_fadingaffection.py`）：

```
staging/fadingaffection_minigame.json           完整分支图（含 memories / status / backgrounds）
E:/test/nikke-web/public/data/fadingaffection.json   网站消费的紧凑副本
```

网页端已接入 `/game/fadingaffection`：三条路线、状态槽、选项消耗与禁用、
死亡后解锁记忆/提示、结局图鉴、记忆档案、本地进度。

## CG 命名约定

动态 CG 的文件夹里是四件套，平铺存放：

```
EventScene_xxx.png         完整插画（2048²，透明底）
EventScene_xxx.spine.png   Spine 图集贴图（角色部件摊平）
EventScene_xxx.atlas       图集描述
EventScene_xxx.skel        二进制骨架
```

`.atlas` 第一行写的是**图集贴图的文件名**，改名时必须同步改这一行。查看器与渲染脚本
都按第一行解析贴图，不再假设它叫 `<名称>.png`。

静态 CG（无动态模型）只有 `<名称>.png`。

## 游戏更新后的提取流程

版本更新后客户端路径通常不变，按顺序跑即可；路径变了用环境变量覆盖，不必改代码：

```bat
set NIKKE_PATCH=D://Games//NIKKE//Unity//com_proximabeta_NIKKE//com.shiftup.patch
set NIKKE_STATIC_PACK=C://...//Temp//com_proximabeta//NIKKE//StaticData.pack
```

```bash
python scripts/preflight.py             # 1. 确认资源池/静态包都在，并列出池子大小
python scripts/decrypt.py               # 2. 新版本 StaticData → staticdata/ + data_raw/StaticData.zip
python scripts/decrypt_nkdb_batch.py    # 3. 刷新台词库与 catalog → decrypted/（文件名=内容hash，会变！）
python scripts/export_mainstory.py      # 4. 主线文本（含 cg 转场）
python scripts/export_rest.py           # 5. 活动/支线/个人文本（含 cg 转场）
python scripts/export_cg_v2.py          # 6. 新静态 CG（幂等只补缺，HD 优先）
python scripts/export_bg.py             # 6b. 纯剧情背景 → CG/06_剧情背景/
python scripts/export_spine_cg.py       # 7. 新动态 CG → staging/spine
python scripts/reorganize_cg.py         # 8. 并入 CG/（自动分类、改名图集、渲染插画）
python scripts/export_story_v2.py       # 9. 玛丽安活动（如有新活动改 PREFIX），同步到 其他剧情/活动剧情/Marian/
python scripts/build_cg_index.py        # 10. 重建对照索引（消费剧情 JSON，单源）
python scripts/export_bg_map.py         # 10b. 动态CG↔背景对照表（可选）
python scripts/export_movies.py         # 11. 章末动画清单（可选）
python scripts/build_cg_gallery.py      # 12. 重建缩略图与画廊（注意先处理旧「动态版」链接）
```

> Locale 库定位：导出脚本用 `locale_db.find("Locale_XXX")` 按表名扫描 decrypted/，
> hash 文件名变了也不受影响；新脚本不要再硬编码 hash 路径。

`export_spine_cg.py` 只写 `staging/spine/<名称>/`，不会直接动 `CG/`；第 8 步才合并，
所以中途失败不会把现有图库搞乱。第 6 步对动态 CG 做了保护：发现同名 `.spine.png` 就跳过，
不会用图集覆盖已经渲染好的插画。

## 离线合成动图已下线（2026-11-14）

网站改为直接播放实时 Spine 模型，画质更高且支持缩放 / 拖拽 / 时间轴 / 保存当前帧。
原先 `动态CG/动图/` + `nikke-web/public/dyn/` + `nikke-web/dist/dyn/` 三份 640px 合成
动画 WebP（合计约 1.7 GB）已全部清理，前端与数据导出脚本都不再引用它们。
`scripts/render_all_spine.py` 保留为存档，默认执行会直接退出；确需离线动图时加 `--legacy --force`。
注意 `CG索引/剧情CG索引.html` 是更早生成的离线单文件画廊，里面「动态版」链接仍指向已删除的
`动图/*.webp`；重跑 `build_cg_gallery.py` 前需先把这列改成网站查看页链接或直接去掉。

动态 CG 的判定现在统一走 `nikke-web/public/data/spine_models.json`（`export_cg.py` 的
`d=1`、`export_story.py` 的 `d` 字段都从这里取），不再依赖某个文件是否存在。

## 哪些数据要留

| 目录 | 作用 | 能否重建 | 建议 |
|---|---|---|---|
| `CG/` | 静态与动态 CG 图库（约 6.8 GB，2022 个文件） | 需游戏资源池（14.8 GB）重跑 `export_cg_v2.py` / `export_spine_cg.py` | **必须留** |
| `staging/` | 角色站姿模型、立绘渲染图、技能立绘（约 3.9 GB） | 需游戏资源池重跑 `export_char_standing.py` / `export_char_cutins.py` | **必须留**，网站角色页的唯一数据源 |
| `主线剧情/`、`其他剧情/` | 剧情文本（约 150 MB） | 由 `staticdata/` 重跑 `export_mainstory.py` / `export_rest.py` | 建议留 |
| `decrypted/` | 台词 / 角色名 / 章节名的 SQLite（76 个） | 需要游戏资源池里的 NKDB 源文件（`saus/raw`、`dp/raw` 等），用 `python scripts/nkdb.py <文件>` 逐个解 | **必须留**，删了要重装/重下游戏资源 |
| `staticdata/` | 9820 张静态表（`.mpk/.csv`） | `python scripts/unpack_staticdata.py`，只依赖 `data_raw/StaticData.zip` | 建议留；真要腾空间可删，重建约 10 秒 |
| `catalogs/` | 各资源池的 `catalog.ndb` 解密缓存 | `export_cg_v2.py` 发现缺失会自己解密（需要游戏 patch） | 可删，重跑自动生成 |
| `data_raw/` | 原始包与 salt | 无法重建（需客户端缓存） | **必须留** |

当前数据对应客户端版本 `qa-261029-10b / 579369`。游戏大版本更新后，`staticdata/` 与
`decrypted/` 都会变成旧版本，需要按上面的顺序重新解密，而不是继续用旧缓存。

## CG 转场标记（2026-11-21 起）

Dialog 表每条记录可能携带 `EventScene_*` token = 该行显示的 CG。所有导出脚本
（`export_mainstory.py` / `export_rest.py` / `export_story_v2.py`）经 `cg_refs.py`
按同一套口径落盘：

* **JSON**：行内 `cg` 字段，**只在 CG 发生变化的行上**（首现、切换、切回都算）；
  同一张 CG 持续显示的后续行不重复标注。
* **Markdown**：变化行前插入
  `> 🖼 CG：![EventScene_xxx](../CG/...)`（成品图相对链接）；文件缺失时给
  `> ⚠️ CG（未导出/近似缺失）` 警示，不链接。
* **索引**：`build_cg_index.py` 直接消费剧情 JSON 的 `cg` 字段（单一事实源），
  输出 `剧情CG对照索引.csv/json`（旧版只扫主线+活动且把 A→B→A 回归去重，现已保留完整转场序列），
  另有 `CG剧情档案.csv`（每张 CG 的剧情出处汇总）。

覆盖范围：主线 `ScenarioDialogTable`、活动 `EventScenarioDialogTable`、
妮姬个人 `AttractiveScenarioDialogTable`、支线故事 `SideStoryScenarioDialogTable`。
咨询（Counseling）与 Spot 表经全量扫描确认不含 CG token。
Marian 活动（`export_story_v2.py`，根目录结构化 JSON）与 SKY ON THE ROCK
（`export_skyontherock.py`，确认无 CG 引用）也走同一口径。

相关新增：`scripts/cg_refs.py`（共用的 token 提取 / 成品库解析 / 标记渲染）、
`scripts/locale_db.py`（**按表名动态定位 Locale 库**——NKDB 解密文件名是内容 hash，
游戏更新就换名，2026-11-19 刷新时旧 hash 全部失效过一次）、
`scripts/export_movies.py`（`ScenarioMovieTable` → `CG索引/剧情动画清单.csv`，31 部章末动画/PV 的 CDN mp4+srt）。

## 动态 CG 的背景（2026-11-21 补全）

Spine 动态 CG 在游戏里是「背景层 + 模型层」合成显示，背景本身是独立资产，
共三类（详见 `CG索引/动态CG背景对照.csv`，118 个动态 CG 逐个标注）：

1. **纯剧情背景**：`scenariobackground(hd)` 组里不带 `eventscene_` 前缀的 472 个
   bundle（`BigHotSpring_d`、`Desert_05`、`black` 黑场、`none` 等场景板），
   由 `export_bg.py` 提取到 **`CG/06_剧情背景/`**，文件名 = 游戏内纹理原名，
   与剧情表里的背景 token 直接对应；清单在 `CG/06_剧情背景/_清单/剧情背景清单.csv`。
2. **X_bg 背景板**：`EventScene_X_bg.png`（X 为动态 CG 时即其专属背景板，
   命名约定配对；X 为静态时是背景板当 CG 用），一直在 CG 库里，现已在对照表里标出。
3. **模型自带 bg region**：96/118 个 atlas 自带 bg 区域，自包含无需外挂。

行级数据（剧情 JSON）随转场新增两个字段（只落在 CG 变化行）：
* `cgd` —— 该行动态 CG 的 **spine 模型名**（CG token 是模型名或其 `X_bg` 板时解析）；
* `cgb` —— 该行应铺的**背景资产名**（优先 X_bg 板，否则剧情表同记录/持续的背景 token）。

### 场景切换与特效层（2026-11-21 二轮补充）

Dialog 记录里的背景 token 本身就是**场景切换命令**，与 CG 转场独立计时。剧情 JSON
行级因此再有两个字段（各自只在**发生变化的行**落）：

* `bg` —— 背景切换列表，按记录内出现顺序去重：`black`=黑屏转场、`none`=清空背景、
  其余为场景板名（对应 `CG/06_剧情背景/` 的同名文件）。web 端用它做精确 CG 显示
  区间（CG 在下一个 `black`/`none` 处切断）与阅读器场景背景层。
  全库共 28584 处（咨询对话 6990、活动 10966、主线 2882…）。
* `fx` —— 特效层命令 `fx_EventScene_*`（叠加在场景上的 spine 演出特效：花瓣、
  血迹、黑烟、光环等）。**不是主画面 CG 转场**——旧 `script_cg_map.json` 里
  Chap_04_05_blood / Chap_07_02_smoke / Chap_22_02_aura 等九条「差分覆盖」与
  cherryblossom_06_e → CherryBlossom_01 全部源于这些 fx token 被人工误当 CG
  （如 `event_cherryblossom_06_e` 行 69 的 `fx_EventScene_CherryBlossom_01`
  = 吻别场景的樱花特效）。全库共 11 处。web 端可按需渲染为叠加层；不要进 cg_links。

Markdown 同步加了场景标记：`🌑 黑屏转场`、`⬜ 清空背景`、`🎞 背景：X`、`✨ 特效：fx_X`。

**web 端消费方式**：剧情阅读器事件项改成
`{h: hash(cgb 或原token), n: cgb 或原token, d: cgd}` 即可「背景图 + spine 模型」
完整呈现（此前 `X_bg` 行查不到模型导致只显示背景板）；CG 显示区间在行级 `bg`
出现 `black`/`none` 时切断；`CG索引/动态CG背景对照.csv` 的 `建议背景` 列可直接
自动填充 `spine_overrides.json` 的 `background` 字段。无任何背景证据的 16 个模型
（动态壁纸/角色演出模型，剧情表不引用）铺透明底即可。

`scripts/export_bg_map.py` 生成对照表；重新生成背景库与对照表的顺序：
`export_bg.py`（背景图）→ 剧情导出（行级 cgd/cgb/bg/fx）→ `export_bg_map.py`（对照表）。

## 已知缺口

- `EventScene_Chap_22_06`：2026-11-21 已从 `scenariobackground(hd)` bundle 补出插画
  （1024²，骨架缺 sequence region 的问题只影响 Spine 动态播放，不影响静态图）。
- `EventScene_oldtales_05_cinderella / _05_abe / _05_hansel / _05_redshoes / _03_1_cinderella / _03_1_redshoes`：
  Old Tales 活动差分，剧情表仍引用，但**所有资源池都没有对应 bundle**（客户端按需从 CDN 拉取，
  本机未下载），索引按“缺失”标注，共 6 名 11 处引用。
- `EventScene_icedragonsaga_*` 有 17 个差分名在客户端只有 SD 没有 HD（SD chunk 本机全缺），
  索引按“近似”落到基础图。
- SnowFall 活动 `snowfall_episode_noirblanc_08`：mpk 残表还在 staticdata，但台词 key 在
  全部 Locale 库中已被清除，无法生成文本行；其引用的 2 张 CG（`EventScene_snowfalloasis_01_1/_2`）
  在库中正常存在。
- 图鉴（`LiveWallpaperTable`，337 个基础 CG）里 247 个只以壁纸 spine 模型存在，本机
  `livewallpaperprefabs` bundle 只有 Timeline 预制体与 fx 贴图（spine 模型按需下载），
  静态原图与剧情 CG 共用的部分已全部入库；清单见 `CG索引/图鉴清单.csv`。
- 影像/过场动画本体（mp4）不下载；CDN 地址已整理进 `CG索引/剧情动画清单.csv`。
- `CG索引/剧情CG索引.html` 是更早生成的离线单文件画廊，「动态版」链接指向已删除的
  `动图/*.webp`；重跑 `build_cg_gallery.py` 前需先改掉该列（见「离线合成动图已下线」）。

## 备注

- 游戏大版本更新后：重跑 `decrypt.py` → 文本导出 → `export_cg_v2.py` / `export_spine_cg.py`
  （资源池 catalog 会变，旧的 `catalogs/` 缓存需要重建）。
- `scripts/legacy/` 里的脚本依赖旧目录结构，不再保证可运行，仅作历史参考。
