"""Delete scratch artefacts produced during the NIKKE CG extraction.

Only explicit, regenerable paths are touched. Every path is printed with its
size/count first, so the run leaves an audit trail in _cleanup_log.txt.
"""
from __future__ import annotations

import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]

DIRS = [
    "CG/_未修复残留",
    "CG/_特效素材",
    "CG/玛丽安活动剧情",
    "CG/marian",
    "动态CG/_frames",
    "动态CG/样本",
    "动态CG样本",
    "cg_probe",
    "动态CG/模型",
]

FILES = [
    "CG/抽检拼图.jpg",
    "CG/高分抽检.jpg",
    "CG/条纹疑似抽检.jpg",
    "CG/损坏检测.csv",
    "CG/_preserved_Marian_01.png",
    "动态CG/网格修复对比.png",
    "_alpha_scan.json",
    "catalogs/assembled_marian01.bundle",
    "catalogs/assembled_marian01.png",
    "catalogs/dp_chunk0.bundle",
    "catalogs/saus_chunk0.bin",
    "catalogs/test_texture.png",
    "catalogs/1ef703c16ab7d7257f314ba6bc366bd6.sqlite",
    "catalogs/6a46ed93faa7c6fd01f1aa66253becc7.sqlite",
    "catalogs/46f1f3ecc3dd798a757a9a399802aa00.sqlite",
    "catalogs/29b34a526d77b5636a8e5ab09659f7ca.sqlite",
]

GLOBS = ["动态CG/_*.png", "动态CG/_*.mjs"]


def size_of(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def main() -> None:
    log = []
    freed = 0
    for rel in DIRS + FILES:
        p = BASE / rel
        if not p.exists():
            continue
        try:
            n = size_of(p)
            if p.is_dir():
                count = sum(1 for f in p.rglob("*") if f.is_file())
                shutil.rmtree(p)
                log.append(f"DIR  {rel}  {n/1024/1024:.1f} MB  {count} files")
            else:
                p.unlink()
                log.append(f"FILE {rel}  {n/1024/1024:.2f} MB")
            freed += n
        except Exception as e:
            log.append(f"FAIL {rel}  {type(e).__name__}: {e}")

    for pattern in GLOBS:
        for p in BASE.glob(pattern):
            if p.is_file():
                n = p.stat().st_size
                p.unlink()
                log.append(f"FILE {p.relative_to(BASE)}  {n/1024:.0f} KB")
                freed += n

    text = "\n".join(log)
    (BASE / "_cleanup_log.txt").write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"\nfreed {freed/1024/1024:.1f} MB")


if __name__ == "__main__":
    main()
