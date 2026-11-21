"""Shared helpers for the CG audit scripts.

Read-only with respect to scripts/ and CG/: we import cg_paths for
classify() but never modify anything under scripts/, and callers must
never overwrite existing files in CG/ (checked at call sites).
"""
import io
import re
import sqlite3
import struct
import sys

import zstandard as zstd

sys.path.insert(0, r"E:/test/nikke_extract/scripts")
from cg_paths import classify, MIN_CG_SIDE  # noqa: E402,F401  (re-exported)

import pathlib  # noqa: E402

BASE = pathlib.Path(r"E:/test/nikke_extract")
ROOT = pathlib.Path(r"F:/NIKKE/Unity/com_proximabeta_NIKKE/com.shiftup.patch")
AUDIT = BASE / "_cg_audit"
POOLS = ("dp", "core")
GIB = 4294967296

# bundle key -> (group, identity, quality)  for every flavour seen so far.
# group  = leading pool-side collection tag, e.g. scenariobackground(hd)
# ident  = CG identity WITHOUT the 'eventscene_' marker (may contain '/')
# qual   = 'hd' | 'sd' | ''
KEY_PATTERNS = [
    # scenariobackground(hd)_assets_eventscene_absolute_01_1_<32hex>.bundle
    (re.compile(r"^scenariobackground\((hd|sd)\)_assets_eventscene_(.+)_"
                r"[0-9a-f]{32}\.bundle$", re.I),
     lambda m: ("scenariobackground", m.group(2), m.group(1).lower())),
    # spineeventgame-voltroad(hd)_assets_eventscene_voltroad_sd_01_01_<32hex>.bundle
    (re.compile(r"^spineeventgame-([a-z0-9_\-]+)\((hd|sd)\)_assets_eventscene_(.+)_"
                r"[0-9a-f]{32}\.bundle$", re.I),
     lambda m: ("spineeventgame-" + m.group(1).lower(), m.group(3), m.group(2).lower())),
    # livewallpaperprefabs_assets_livewallpaper/eventscene_absolute_01_<32hex>.bundle
    (re.compile(r"^livewallpaperprefabs_assets_livewallpaper/eventscene_(.+)_"
                r"[0-9a-f]{32}\.bundle$", re.I),
     lambda m: ("livewallpaperprefabs", m.group(1), "")),
    # spineeventscenesgroup_assets_spine/events/eventscene_absolute_01_<32hex>.bundle
    (re.compile(r"^spineeventscenesgroup_assets_spine/events/eventscene_(.+)_"
                r"[0-9a-f]{32}\.bundle$", re.I),
     lambda m: ("spineeventscenesgroup", m.group(1), "")),
    # spineeventscenesgroup_assets_spine/events/eventtitle_ce004_01_<32hex>.bundle
    # (matches the %eventscene% filter only because the GROUP name contains it)
    (re.compile(r"^spineeventscenesgroup_assets_spine/events/(.+)_"
                r"[0-9a-f]{32}\.bundle$", re.I),
     lambda m: ("spineeventscenesgroup/" + m.group(1).split("_", 1)[0], m.group(1), "")),
]


def parse_key(key):
    """Return (group, identity, quality) or None if the key is not recognised."""
    for pat, fn in KEY_PATTERNS:
        m = pat.match(key)
        if m:
            return fn(m)
    return None


def manifest_path(pool):
    return BASE / "catalogs" / f"{pool}_catalog.ndb.dec"


def connect(pool):
    return sqlite3.connect(manifest_path(pool))


def cidx_map(pool):
    """hash12 -> (physical_offset, compressed_size) from store.cdb.idx."""
    idx = (ROOT / pool / "chunk" / "store.cdb.idx").read_bytes()
    n = struct.unpack_from("<I", idx, 8)[0]
    table = {}
    for i in range(n):
        r = idx[16 + i * 28:16 + (i + 1) * 28]
        off, seg, size, _crc = struct.unpack_from("<IIII", r, 12)
        table[r[:12]] = (seg * GIB + off, size)
    return table


class PoolStore:
    """Chunk store access for one pool (seek-based, never loads the cdb)."""

    def __init__(self, pool):
        self.pool = pool
        self.conn = connect(pool)
        self.table = cidx_map(pool)
        self.cdb_path = ROOT / pool / "chunk" / "store.cdb"
        self.cdb_size = self.cdb_path.stat().st_size
        self._fh = None
        self.dec = zstd.ZstdDecompressor()

    def fh(self):
        if self._fh is None:
            self._fh = open(self.cdb_path, "rb")
        return self._fh

    def chunks_of(self, file_id):
        return self.conn.execute(
            """select m.file_offset, k.hash, k.original_size
               from chunk_file_map m join chunks k on k.chunk_id = m.chunk_id
               where m.file_id = ? order by m.file_offset""",
            (file_id,)).fetchall()

    def rebuild(self, file_id):
        """Rebuild a bundle -> (bytes, n_chunks, n_missing). None if no chunks."""
        parts = self.chunks_of(file_id)
        if not parts:
            return None, 0, 0
        buf = bytearray()
        missing = 0
        fh = self.fh()
        for foff, h, _orig in parts:
            entry = self.table.get(h[4:16])
            if entry is None:
                missing += 1
                continue
            real, size = entry
            if size <= 0 or real + size > self.cdb_size:
                missing += 1
                continue
            fh.seek(real)
            data = self.dec.decompressobj().decompress(fh.read(size))
            if foff + len(data) > len(buf):
                buf.extend(b"\x00" * (foff + len(data) - len(buf)))
            buf[foff:foff + len(data)] = data
        return bytes(buf), len(parts), missing

    def close(self):
        if self._fh:
            self._fh.close()
        self.conn.close()


def eventscene_keys(conn):
    return conn.execute(
        "select file_id,key from files_chunktype where lower(key) like '%eventscene%'"
    ).fetchall()


def safe_name(name):
    return re.sub(r"[^\w.-]+", "_", name)
