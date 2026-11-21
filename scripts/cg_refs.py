"""Shared per-line CG extraction for every NIKKE scenario export.

Dialog 表的二进制记录里，台词行可能携带若干 `EventScene_*` token——那就是该行
显示的 CG（差分也直接列在行内）。所有导出脚本（主线 / 其他剧情 / 对照索引）
都用这里同一套逻辑，保证「剧情文本标记」与「CG 索引」口径一致。

口径约定：
  * 一行记录内的 CG token 去重保序后就是该行的 CG 列表；
  * 与前一行的列表相同 = CG 还挂在屏幕上，不算转场，JSON 不写 `cg` 字段；
  * Markdown 在发生变化的行前插入转场标记（图片用 CG/ 成品库相对链接）。
"""
from __future__ import annotations

import re
import struct
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]

TOKEN = re.compile(rb"[ -~]{4,}")
CG_NAME = re.compile(r"^EventScene_[A-Za-z0-9_]+$")
FX_NAME = re.compile(r"^fx_(EventScene_[A-Za-z0-9_]+)$")
_CHAR_KEY = re.compile(r"^Locale_Character:[A-Za-z0-9_]+_name$")
_SLOT_PATH = re.compile(r"^spine/events/(EventScene_[A-Za-z0-9_]+)$")


def iter_tokens(raw: bytes):
    """[(offset, token_str), ...]"""
    return [(m.start(), m.group().decode("ascii", "replace"))
            for m in TOKEN.finditer(raw)]


def collect_cgs(raw: bytes, start: int, end: int) -> tuple[str, ...]:
    """[start, end) 字节区间内的 CG token，去重保序。"""
    cgs = []
    for m in TOKEN.finditer(raw, start, end):
        s = m.group().decode("ascii", "replace")
        if CG_NAME.match(s) and s not in cgs:
            cgs.append(s)
    return tuple(cgs)


def changed(prev: tuple[str, ...] | None, cur: tuple[str, ...]) -> bool:
    """CG 列表是否发生了变化（首行为空 -> 有 CG 也算变化）。"""
    return cur != (prev or ())


# --------------------------------------------------------------------------- #
# 动态 CG 与背景
# --------------------------------------------------------------------------- #
def load_spine_models() -> set[str]:
    """动态 CG（Spine 模型）名集合 = CG/ 下的全部 .atlas 锚名。"""
    return {a.stem for a in (BASE / "CG").rglob("*.atlas")}


def load_bg_names() -> set[str]:
    """纯剧情背景纹理名（CG/06_剧情背景/，导出自 scenariobackground 非 eventscene 组）。"""
    d = BASE / "CG" / "06_剧情背景"
    if not d.exists():
        return set()
    return {f.stem for f in d.glob("*.png")}


def collect_bgs(raw: bytes, start: int, end: int, bg_names: set[str]) -> tuple[str, ...]:
    """[start, end) 内的剧情背景 token（裸资源名，大小写按纹理原名），去重保序。

    背景切换就是游戏里的场景切换信号：`black`＝黑屏转场、`none`＝清空背景。
    """
    if not bg_names:
        return ()
    low = {b.lower(): b for b in bg_names}
    out = []
    for m in TOKEN.finditer(raw, start, end):
        s = m.group().decode("ascii", "replace")
        hit = low.get(s.lower())
        if hit and hit not in out:
            out.append(hit)
    return tuple(out)


def collect_fx(raw: bytes, start: int, end: int) -> tuple[str, ...]:
    """[start, end) 内的特效层命令（`fx_EventScene_*`，如花瓣/血迹/黑烟叠加）。

    fx 不是主画面 CG 转场——它是叠加在当前场景之上的演出特效；名字去掉 `fx_`
    前缀后通常对应一个 spine 模型或差分。此前 script_cg_map 里的「差分覆盖」
    条目（Chap_04_05_blood 等）全部源于这些 token 被误当成 CG。
    """
    out = []
    for m in TOKEN.finditer(raw, start, end):
        s = m.group().decode("ascii", "replace")
        if FX_NAME.match(s) and s not in out:
            out.append(s)
    return tuple(out)


# --------------------------------------------------------------------------- #
# 演出位 id（模型槽位）间接引用
# --------------------------------------------------------------------------- #
# 游戏里相当一部分动态 CG（章节过场 / 活动过场）并不在对话记录里写
# EventScene_* 字面 token，而是只写「演出位 id」（如 rapi_event），由游戏按位
# id 从 ScenarioCharacterSettingTable 取 spine/events/EventScene_X 全屏播放。
# collect_cgs 只认字面 token，因此这批 CG 全部漏采——这正是当初
# EventScene_Chap_04_01「只有背景没有模型」同类问题的根因。

# 源数据损坏的模型（atlas 缺附件，SpinePlayer 加载报错），不作为动态 CG 引用
_BROKEN_MODELS = {"EventScene_Main_01_02"}

_SLOT_CACHE: dict[str, str] | None = None


def load_movie_slots() -> dict[str, str]:
    """解析 ScenarioCharacterSettingTable.mpk → {演出位 id: spine 模型名}。

    表内每条演出设置按字段序存放：
        [位id][Locale_Character:<n>_name][default][spine/events/EventScene_X][服装变体]
    取 Locale_Character 键前一位作位 id、后几位里的 spine 路径作模型名。
    结果进程内缓存（整张表约 200KB，只读一次）。
    """
    global _SLOT_CACHE
    if _SLOT_CACHE is not None:
        return _SLOT_CACHE
    slots: dict[str, str] = {}
    path = BASE / "staticdata" / "ScenarioCharacterSettingTable.mpk"
    if path.exists():
        raw = path.read_bytes()
        toks = [m.group().decode("ascii", "replace") for m in TOKEN.finditer(raw)]
        for i, s in enumerate(toks):
            if not _CHAR_KEY.match(s) or i == 0:
                continue
            sid = toks[i - 1]
            for j in range(i + 1, min(i + 5, len(toks))):
                m = _SLOT_PATH.match(toks[j])
                if m:
                    slots.setdefault(sid, m.group(1))
                    break
    _SLOT_CACHE = slots
    return slots


def _iter_fields(raw: bytes, start: int, end: int):
    """遍历 [start,end) 内的长度前缀字符串字段 (offset, value)。

    mpk 字段结构：[int32 -(len+1)][int32 len][len 字节 ascii]。用强约束
    marker == -(len+1) 逐字节扫描，避免把二进制噪声当成字符串。
    """
    i = start
    while i + 8 <= end:
        marker, length = struct.unpack_from("<ii", raw, i)
        if marker == -(length + 1) and 0 < length <= 300 and i + 8 + length <= end:
            b = raw[i + 8:i + 8 + length]
            if all(32 <= c < 127 for c in b):
                yield i, b.decode("ascii")
                i += 8 + length
                continue
        i += 1


def collect_movie_cgs(raw: bytes, start: int, end: int,
                      slots: dict[str, str] | None = None) -> tuple[str, ...]:
    """[start,end) 内由模型槽位引用的 spine 模型名，去重保序。

    槽位在对话记录里的字节形态（紧跟 Locale key 之后）：
        [位id 字符串][int32 0][槽位种类][动画名]
    槽位种类实测有 "1"、"5"、"event"、"idle"、"snowwhite" 等（早期只认
    "1"/"0"，漏掉了 marian_event_02 → EventScene_Main_01_02 这类用 "event" 的）。
    位 id 后紧跟的 int32 0 + 短种类 token + 动画名把它与说话人/立绘槽位区分开，
    避免 noise / black / dorothy 等与角色 id 撞名的位 id 被误判成模型引用。
    """
    slots = load_movie_slots() if slots is None else slots
    if not slots:
        return ()
    out: list[str] = []
    for off, s in _iter_fields(raw, start, end):
        model = slots.get(s)
        if not model or model in _BROKEN_MODELS:
            continue
        nxt = off + 8 + len(s)
        if nxt + 4 > end or struct.unpack_from("<i", raw, nxt)[0] != 0:
            continue
        after = []
        for _o2, v2 in _iter_fields(raw, nxt + 4, min(end, nxt + 96)):
            after.append(v2)
            if len(after) >= 2:
                break
        # 槽位种类是短 token（"1"/"event"/"idle"…），长度上限挡住路径类噪声
        if len(after) >= 2 and 0 < len(after[0]) <= 12 and model not in out:
            out.append(model)
    return tuple(out)


def merge_cgs(*groups):
    """多组 CG 名去重保序合并（字面 token + 演出位模型名）。"""
    out: list[str] = []
    for g in groups:
        for n in g or ():
            if n not in out:
                out.append(n)
    return tuple(out)


def resolve_dynamic(token: str, spine: set[str], static: dict[str, str],
                    bg_evidence=()) -> tuple[str, str] | None:
    """CG token -> (spine 模型名, 背景板名)；与动态 CG 无关返回 None。

    两种命中形态（与游戏内呈现一致）：
      token == X        且 X 是 spine 模型 -> 模型 X，背景优先 X_bg 板，否则剧情背景证据
      token == X_bg     且 X 是 spine 模型 -> 模型 X，背景板 X_bg（剧情背景证据兜底）
    """
    x = token[:-3] if token.endswith("_bg") else token
    if x not in spine:
        return None
    board = f"{x}_bg"
    bg = board if board.lower() in static else ""
    if not bg and bg_evidence:
        bg = bg_evidence[-1]        # 记录内/持续的背景列表，末位是最终状态
    return x, bg


# --------------------------------------------------------------------------- #
# CG 成品库
# --------------------------------------------------------------------------- #
def load_cg_library() -> tuple[dict[str, str], dict[str, str]]:
    """CG/ 成品扫描：name(lower) -> 相对 BASE 的静态图路径 / 动态 CG 目录。

    静态图排除 .spine.png（那是 Spine 图集贴图，不是插画）；
    动态 CG 以 .atlas 的存在为准（四件套的锚）。
    """
    static: dict[str, str] = {}
    for f in (BASE / "CG").rglob("*.png"):
        if f.name.endswith(".spine.png"):
            continue
        static.setdefault(f.stem.lower(), f.relative_to(BASE).as_posix())
    dynamic: dict[str, str] = {}
    for a in (BASE / "CG").rglob("*.atlas"):
        dynamic.setdefault(a.stem.lower(), a.parent.relative_to(BASE).as_posix())
    return static, dynamic


def resolve_cg(name: str, static: dict[str, str], dynamic: dict[str, str]):
    """精确名 -> 去尾部 _N 差分后缀逐级回退。返回 (静态图, 动态目录, 匹配类型)。"""
    low = name.lower()
    if low in static or low in dynamic:
        return static.get(low), dynamic.get(low), "精确"
    cand, cur = [low], low
    while True:
        m = re.match(r"^(.*)_\d+$", cur)
        if not m:
            break
        cur = m.group(1)
        cand.append(cur)
    for c in cand[1:]:
        if c in static or c in dynamic:
            return static.get(c), dynamic.get(c), "近似"
    return None, None, "缺失"


def scene_marker_md(bgs, fxs, static: dict[str, str] | None = None,
                    up: str = "..") -> list[str]:
    """背景切换 / 特效层 -> Markdown 场景标记（转场、黑屏、清空、特效）。"""
    out = []
    for b in bgs or ():
        low = b.lower()
        if low == "black":
            out += ["", "> 🌑 黑屏转场"]
        elif low == "none":
            out += ["", "> ⬜ 清空背景"]
        else:
            sf = (static or {}).get(low)
            p = f" —— ![bg]({up}/{sf})" if sf else ""
            out += ["", f"> 🎞 背景：`{b}`" + p]
        out.append("")
    for fx in fxs or ():
        out += ["", f"> ✨ 特效：`{fx}`", ""]
    return out


def marker_md(cgs, static: dict[str, str], dynamic: dict[str, str],
              up: str = "..", model: str = "", bg: str = "") -> list[str]:
    """一行 CG 列表 -> Markdown 转场标记行。

    `up` 是 Markdown 文件到工程根的相对前缀（主线/其他剧情一级目录为 ".."，
    其他剧情二级目录如 活动剧情/ 为 "../.."）。文件缺失的 CG 给出 ⚠ 标注。
    `model`/`bg` 是该行动态 CG 的 spine 模型与背景板（resolve_dynamic 结果），
    命中时在标记里显式标出，阅读器/人工都能一眼看清「模型 + 背景」的组合。
    """
    out = ["", "> ---", ""]
    if model:
        line = f"> 🖼 CG（动态）：spine `{model}`"
        if bg:
            line += f" ＋ 背景 `{bg}`"
        if sfile := static.get(bg.lower()):
            line += f" —— ![bg]({up}/{sfile})"
        out.append(line)
        out.append("")
        return out
    for cg in cgs:
        sfile, dmodel, match = resolve_cg(cg, static, dynamic)
        if sfile:
            out.append(f"> 🖼 CG：![{cg}]({up}/{sfile})")
        elif dmodel:
            out.append(f"> 🖼 CG（动态）：`{cg}` —— {up}/{dmodel}/")
        else:
            tag = "近似缺失" if match == "近似" else "未导出"
            out.append(f"> ⚠️ CG（{tag}）：`{cg}`")
        out.append("")
    return out
