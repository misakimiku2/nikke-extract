## 1. catalog ↔ CG 成品库
- catalog 可重建 bundle：1245，已存在 1244，本次补提 1
- EventScene_* 纹理在库缺失：**0** []
- CG 库内静态插画 1773 张，动态 CG（atlas）118 组

## 2. 独立逐行扫描 ↔ 新索引
- 独立扫描 (台词ID,CG) 对：1768；新索引：1598
- 索引有扫描无：0
- 扫描有索引无：170，其中相邻重复声明（口径豁免）168，**真实差异 2**
  - `snowfall_episode_noirblanc_08_33` → `EventScene_snowfalloasis_01_1`  (EventScenarioDialogTable.snowfall_episode_noirblanc_08.mpk:33)
  - `snowfall_episode_noirblanc_08_70` → `EventScene_snowfalloasis_01_2`  (EventScenarioDialogTable.snowfall_episode_noirblanc_08.mpk:70)

## 3. 引用但客户端无资源的 CG（环境性缺口）
- 共 6 名 / 11 处引用：
  - `EventScene_oldtales_03_1_cinderella` ×1
  - `EventScene_oldtales_03_1_redshoes` ×1
  - `EventScene_oldtales_05_abe` ×2
  - `EventScene_oldtales_05_cinderella` ×3
  - `EventScene_oldtales_05_hansel` ×2
  - `EventScene_oldtales_05_redshoes` ×2
- 近似匹配（差分名落到基础图，icedragonsaga 客户端只有 SD 等）：17 名 / 43 处

## 4. 游戏内图鉴（LiveWallpaperTable）
- 壁纸引用的 CG 名 999 个（含 _mi/_si 变体），解析为基础 CG 337 个 -> CG索引/图鉴清单.csv
- 基础 CG 既无静态图也无动态模型：247 ['EventScene_CE003_01', 'EventScene_CE004_01', 'EventScene_CE005_01', 'EventScene_D', 'EventScene_Dakrhero_01', 'EventScene_NeverLand_06', 'EventScene_SeaYouAgain_04_2', 'EventScene_SnowfallOasis_02', 'EventScene_c010_cutscene', 'EventScene_c011_cutscene']
- core 池无对应壁纸 bundle：3 ['EventScene_D', 'EventScene_NeverLand_06', 'EventScene_SnowfallOasis_02']
- 说明：壁纸的 spine 动态模型（livewallpaperprefabs bundle）本工程未提取，静态原图与剧情 CG 共用已全部入库。

