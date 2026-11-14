"""Pre-flight check before extracting after a game update.

Verifies that the client paths still exist, the catalog databases are readable,
and the local caches look sane. Prints exactly which command to run next.

    python scripts/preflight.py
"""
from __future__ import annotations

from pathlib import Path

import config


def fmt_size(n: int) -> str:
    return f"{n/1024**3:.1f} GB" if n >= 1024**3 else f"{n/1024**2:.0f} MB"


def check_file(p: Path, label: str) -> bool:
    ok = p.exists()
    print(f"  [{'OK ' if ok else 'MISS'}] {label}: {p}" + (f"  ({fmt_size(p.stat().st_size)})" if ok else ""))
    return ok


def main() -> None:
    print("== 客户端资源池 ==")
    pool_ok = config.GAME_PATCH.exists()
    print(f"  [{'OK ' if pool_ok else 'MISS'}] patch 根目录: {config.GAME_PATCH}")
    pools = []
    if pool_ok:
        for d in sorted(config.GAME_PATCH.iterdir()):
            if not d.is_dir():
                continue
            cat = d / "catalog.ndb"
            cdb = d / "chunk" / "store.cdb"
            if cat.exists() and cdb.exists():
                pools.append(d.name)
                print(f"        {d.name:<5} catalog {cat.stat().st_size/1024:6.0f} KB   "
                      f"store {fmt_size(cdb.stat().st_size)}")
    if not pools:
        print("        -> 没有找到 catalog.ndb + chunk/store.cdb，请确认游戏已安装且更新完成")

    print("== 客户端静态数据 ==")
    static_ok = check_file(config.STATIC_PACK, "StaticData.pack（启动一次游戏才会生成）")

    print("== 本地缓存 ==")
    salts_ok = check_file(config.DATA_RAW / "_salt1.bin", "salt1") and \
               check_file(config.DATA_RAW / "_salt2.bin", "salt2")
    zip_ok = check_file(config.DATA_RAW / "StaticData.zip", "StaticData.zip")
    n_static = len(list(config.STATIC.glob("*"))) if config.STATIC.exists() else 0
    n_dec = len(list(config.DECRYPTED.glob("*.dec"))) if config.DECRYPTED.exists() else 0
    print(f"  [{'OK ' if n_static else 'MISS'}] staticdata/: {n_static} 个表")
    print(f"  [{'OK ' if n_dec else 'MISS'}] decrypted/: {n_dec} 个 .dec")
    if config.STAGING.exists():
        n_stage = len(list(config.STAGING.rglob("*")))
        print(f"  [INFO] staging/ 里有 {n_stage} 个文件（上次导出尚未并入图库？）")

    print("\n== 建议顺序 ==")
    if static_ok:
        print("  1) python scripts/decrypt.py            # 更新 staticdata/ 与 data_raw/StaticData.zip")
    elif zip_ok:
        print("  1) python scripts/unpack_staticdata.py  # 没有客户端时，用现有 zip 重建 staticdata/")
    if not n_dec or static_ok:
        print("  2) python scripts/decrypt_nkdb_batch.py  # 批量更新 decrypted/")
    print("  3) python scripts/export_mainstory.py   # 主线")
    print("  4) python scripts/export_rest.py        # 活动/支线/个人")
    print("  5) python scripts/export_cg_v2.py       # 静态 CG（写入 CG/，跳过已有动态 CG）")
    print("  6) python scripts/export_spine_cg.py    # 动态 CG -> staging/spine")
    print("  7) python scripts/reorganize_cg.py      # 把 staging 并入 CG/ 并渲染插画")
    print("  8) python scripts/build_cg_index.py && python scripts/build_cg_gallery.py")

    if not pool_ok:
        print("\n提示：路径变了就设环境变量，例如")
        print(r'  set NIKKE_PATCH=D:\Games\NIKKE\...\com.shiftup.patch')


if __name__ == "__main__":
    main()
