"""Central paths for the NIKKE pipeline.

After a game update these are usually the only things that change. Override
without editing code:

    set NIKKE_PATCH=F:\\NIKKE\\Unity\\com_proximabeta_NIKKE\\com.shiftup.patch
    set NIKKE_STATIC_PACK=C:\\...\\Temp\\com_proximabeta\\NIKKE\\StaticData.pack
"""
from __future__ import annotations

import os
import pathlib

# 工程根目录：默认取 scripts/ 的父目录，clone 到任何位置都能直接跑。
# 需要分开存放代码与数据时，用环境变量 NIKKE_BASE 覆盖。
BASE = pathlib.Path(os.environ.get(
    "NIKKE_BASE",
    pathlib.Path(__file__).resolve().parents[1],
))

# game resource pool (catalog.ndb + chunk/store.cdb)
GAME_PATCH = pathlib.Path(os.environ.get(
    "NIKKE_PATCH",
    r"F:\NIKKE\Unity\com_proximabeta_NIKKE\com.shiftup.patch",
))

# client cache, written by the game on launch
STATIC_PACK = pathlib.Path(os.environ.get(
    "NIKKE_STATIC_PACK",
    pathlib.Path(os.environ.get("LOCALAPPDATA", pathlib.Path.home() / "AppData" / "Local"))
    / "Temp" / "com_proximabeta" / "NIKKE" / "StaticData.pack",
))

STATIC = BASE / "staticdata"
DECRYPTED = BASE / "decrypted"
CATALOGS = BASE / "catalogs"
DATA_RAW = BASE / "data_raw"
STAGING = BASE / "staging"
