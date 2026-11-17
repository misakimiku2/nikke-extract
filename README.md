# NIKKE 剧情 / CG 提取工程

本地离线解包《胜利女神：NIKKE》的剧情文本、静态 CG、Spine 动态 CG，并生成
「剧情 ↔ CG」对照索引。全部数据来自本机客户端，不联网下载。

最后整理：2026-11-14

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
| `CG/` | **成品图库**。按 `01_活动剧情CG / 02_主线剧情CG / 03_支线剧情CG / 04_角色过场 / 05_其他动态CG` 分类；`_清单/` 里是分类汇总与逐张清单 |
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
                │ export_mainstory.py / export_rest.py
                └── 主线剧情/、其他剧情/

com.shiftup.patch（游戏资源池，14.8 GB）
        │ export_cg_v2.py     catalog.ndb + store.cdb → 静态 CG
        │ export_spine_cg.py  spineeventscenesgroup → .atlas/.skel/图集
        └── CG/
                │ build_cg_index.py + build_cg_gallery.py
                └── CG索引/
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
python scripts/export_cg_v2.py                # 静态 CG（直接写入 CG/<分类>/；已有 .spine.png 的动态 CG 会跳过，不覆盖渲染插画）
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
python scripts/decrypt_nkdb_batch.py    # 3. 刷新台词库与 catalog → decrypted/
python scripts/export_mainstory.py      # 4. 主线文本
python scripts/export_rest.py           # 5. 活动/支线/个人文本
python scripts/export_cg_v2.py          # 6. 新静态 CG（已有 .spine.png 的会跳过）
python scripts/export_spine_cg.py       # 7. 新动态 CG → staging/spine
python scripts/reorganize_cg.py         # 8. 并入 CG/（自动分类、改名图集、渲染插画）
python scripts/build_cg_index.py        # 9. 重建对照索引
python scripts/build_cg_gallery.py      # 10. 重建缩略图与画廊
```

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

## 已知缺口

- `EventScene_Chap_22_06`：客户端缺 sequence region，骨架无法加载，只有图集与 atlas/skel，无插画。
- `EventScene_icedragonsaga_*` 有 17 个差分名在客户端只有 SD 没有 HD，索引按“近似”标注。
- 影像/过场动画（mp4）未纳入本工程；`ScenarioMovieTable` 里有 CDN 地址。

## 备注

- 游戏大版本更新后：重跑 `decrypt.py` → 文本导出 → `export_cg_v2.py` / `export_spine_cg.py`
  （资源池 catalog 会变，旧的 `catalogs/` 缓存需要重建）。
- `scripts/legacy/` 里的脚本依赖旧目录结构，不再保证可运行，仅作历史参考。
