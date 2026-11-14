"""[已停用 / 仅存档] Batch-render every exported Spine CG into an animated WebP.

2026-11-14 起网站改为直接播放实时 Spine 模型：画质更高、可交互（缩放/拖拽/时间轴/
逐帧导出），离线合成的 640px 动画 WebP 质量更低且三处副本合计约 1.7 GB，已全部下线。
`public/dyn/` 与 `动态CG/动图/` 不再由任何前端代码引用。

本脚本保留是为了日后需要离线动图时可复现；默认执行只打印说明并退出，
必须显式加 --legacy 才会真正渲染。

历史用法（需要 ffmpeg + Node runtime）：
    python scripts/render_all_spine.py --legacy --force
"""
import concurrent.futures as cf
import json
import pathlib
import re
import subprocess
import sys
import time

BASE = pathlib.Path(__file__).resolve().parents[1]
# 模型四件套现在平铺在 CG/<分类>/<事件>/ 下，旧的「动态CG/模型」目录已不存在。
CG_ROOT = BASE / "CG"
OUT = BASE / "动态CG" / "动图"
WEB_DYN = pathlib.Path(r"E:\test\nikke-web\public\dyn")
RUNTIME = BASE / "动态CG" / "runtime"
FFMPEG = pathlib.Path(r"E:\test\ffmpeg\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe")
NODE = "node"
FPS = 20
SIZE = 640
QUALITY = 72


def render_one(model_dir: pathlib.Path, name: str, force: bool = False):
    out = OUT / (name + ".webp")
    if not force and out.exists() and out.stat().st_size > 4096:
        return (name, "skip", out.stat().st_size, 0.0, "")
    t0 = time.time()
    node_cmd = [NODE, "render_spine_stream.mjs", str(model_dir), name, str(FPS), str(SIZE)]
    ff_cmd = [
        str(FFMPEG), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "png", "-i", "-",
        "-c:v", "libwebp_anim", "-lossless", "0", "-q:v", str(QUALITY),
        "-loop", "0", "-an", str(out),
    ]
    try:
        p_node = subprocess.Popen(node_cmd, cwd=str(RUNTIME), stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
        p_ff = subprocess.Popen(ff_cmd, stdin=p_node.stdout,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        p_node.stdout.close()
        _, ff_err = p_ff.communicate(timeout=900)
        node_err = p_node.stderr.read().decode("utf-8", "replace")
        p_node.wait(timeout=60)
        if p_ff.returncode != 0 or not out.exists():
            return (name, "ffmpeg_fail", 0, time.time() - t0, ff_err[-160:].decode("utf-8", "replace"))
        # 网页图鉴的「动态播放」直接读 public/dyn，顺手同步过去
        WEB_DYN.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(out, WEB_DYN / (name + ".webp"))
        info = node_err.strip().splitlines()[-1] if node_err.strip() else ""
        return (name, "ok", out.stat().st_size, time.time() - t0, info)
    except subprocess.TimeoutExpired:
        for p in (p_ff, p_node):
            try:
                p.kill()
            except Exception:
                pass
        return (name, "timeout", 0, time.time() - t0, "")
    except Exception as e:
        return (name, "error", 0, time.time() - t0, str(e)[:160])


def main():
    if "--legacy" not in sys.argv:
        print("离线合成动画 WebP 已停用：网站现在直接播放实时 Spine 模型。")
        print("生成物 public/dyn/ 与 动态CG/动图/ 已清理；如需复现请加 --legacy。")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    WEB_DYN.mkdir(parents=True, exist_ok=True)
    force = "--force" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    # 每个 .atlas 对应一个模型，目录名是事件名，模型名取 atlas 文件名
    models = sorted(
        [(p.parent, p.stem) for p in CG_ROOT.rglob("*.atlas")],
        key=lambda x: x[1],
    )
    if args:
        models = [m for m in models if re.search(args[0], m[1], re.I)]
    pending = models if force else [
        m for m in models
        if not ((OUT / (m[1] + ".webp")).exists()
                and (OUT / (m[1] + ".webp")).stat().st_size > 4096)]
    print(f"models {len(models)}  pending {len(pending)}  fps={FPS} size={SIZE} q={QUALITY}",
          flush=True)

    started = time.time()
    results = []
    with cf.ThreadPoolExecutor(max_workers=3) as pool:
        for n, res in enumerate(pool.map(lambda m: render_one(m[0], m[1], force), pending), 1):
            results.append(res)
            size = f"{res[2]/1024:.0f}KB" if res[2] else "-"
            print(f"  [{n}/{len(pending)}] {res[0]:<40} {res[1]:<11} {size:>7} {res[3]:.0f}s", flush=True)
            # 即使增量跳过也要保证 public/dyn 有最新文件
            if res[1] == "skip":
                import shutil
                src = OUT / (res[0] + ".webp")
                dst = WEB_DYN / (res[0] + ".webp")
                if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                    shutil.copy2(src, dst)

    ok = [r for r in results if r[1] == "ok"]
    print(f"\nok {len(ok)} / {len(results)}   "
          f"{sum(r[2] for r in ok)/1024/1024:.1f} MB   {time.time()-started:.0f}s")
    for r in results:
        if r[1] not in ("ok", "skip"):
            print("  FAIL", r)


if __name__ == "__main__":
    main()
