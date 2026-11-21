"""Probe: rebuild a few bundles, list object types and Texture2D name/size."""
import io
import sys

import UnityPy

sys.path.insert(0, r"E:/test/nikke_extract/_cg_audit")
import common  # noqa: E402


def describe(store, fid, key):
    bundle, n, miss = store.rebuild(fid)
    tag = "OK" if bundle and bundle.startswith(b"UnityFS") else "BAD"
    print(f"\n== {key}\n   chunks={n} missing={miss} size={len(bundle) if bundle else 0} {tag}")
    if tag != "OK":
        return
    env = UnityPy.load(io.BytesIO(bundle))
    types = {}
    for o in env.objects:
        types[o.type.name] = types.get(o.type.name, 0) + 1
    print("   types:", types)
    for o in env.objects:
        if o.type.name != "Texture2D":
            continue
        try:
            t = o.read()
            print(f"   TEX {t.m_Name!r} {t.m_Width}x{t.m_Height}")
        except Exception as e:
            print("   TEX <read fail>", e)


def main():
    picks = [
        ("dp", "scenariobackground(hd)_assets_eventscene_absolute_01_1_410bf26bd3873e9b2d876c5c9a2ae69c.bundle"),
        ("dp", "scenariobackground(sd)_assets_eventscene_absolute_01_1_cca52f43331a09c6365763994c0901ac.bundle"),
        ("dp", "spineeventgame-voltroad(hd)_assets_eventscene_voltroad_sd_01_01_405d1566f2a677c838e4bc36b1e4bf24.bundle"),
        ("core", "livewallpaperprefabs_assets_livewallpaper/eventscene_absolute_01_363e8a2a0554ed8f51893142429212d2.bundle"),
        ("core", "spineeventscenesgroup_assets_spine/events/eventscene_absolute_01_54f52fdc9273a4037bf7bd6ae37d98c5.bundle"),
        ("dp", "scenariobackground(hd)_assets_2025foolsday_e0f09d18de365bd7ff99f1937831e110.bundle"),  # non-eventscene control
    ]
    by_pool = {}
    for pool, key in picks:
        by_pool.setdefault(pool, []).append(key)
    for pool, keys in by_pool.items():
        st = common.PoolStore(pool)
        for key in keys:
            row = st.conn.execute("select file_id from files_chunktype where key=?", (key,)).fetchone()
            if not row:
                print("NOT FOUND:", key)
                continue
            describe(st, row[0], key)
        st.close()


if __name__ == "__main__":
    main()
