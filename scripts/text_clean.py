"""Shared text normalization for every NIKKE scenario export.

The client template `{AccountData.NickName}` is replaced with 指挥官 in all
deliverables (md AND json), so every export script must call clean() when it
writes a zh-CN value.
"""
import struct

NICKNAME_VAR = "{AccountData.NickName}"
NICKNAME_REPL = "指挥官"


def clean(s):
    if s is None:
        return None
    return s.replace(NICKNAME_VAR, NICKNAME_REPL)


# --- speaker resolution -----------------------------------------------------
# Each dialog record stores [portrait_id, speaker_marker, ...] before its localkey.
# speaker_marker is either a character id (shows a name box), or one of the
# special markers below.
SELF_NAME = "指挥官"
SELF_MARKERS = {"Self", "Choice"}              # player's own lines / choices
NARRATION_MARKERS = {"Narration", "Monologue"}  # narration, no name box


def speaker_of(pre, names):
    """Return (speaker_name, speaker_id) for the tokens before a localkey."""
    chars = [s for s in pre if s in names]
    last = pre[-1] if pre else None
    if last in SELF_MARKERS:
        return SELF_NAME, last
    if len(chars) >= 2:
        return names.get(chars[-1]), chars[-1]
    return None, None


# --- record type -------------------------------------------------------------
# 分组对白表（ScenarioDialogTable.<group>.mpk 等）每条记录在 group 字段之后
# 紧跟两个 int32，第二个是行类型。实测含义：
#   0 = 有名字的角色台词    1 / 2 = 旁白、演出、内心独白
#   4 = 指挥官（玩家）台词  5 = 玩家选项
# 只看「localkey 前有两个角色 ID」无法区分旁白和指挥官——后期章节的指挥官台词
# 只有立绘 ID、没有 Self 标记，会整段丢失说话人。
def record_type(raw, group, group_offset):
    """读取记录类型；越界或格式不符时返回 None。"""
    try:
        return struct.unpack_from("<ii", raw, group_offset + len(group))[1]
    except struct.error:
        return None


def speaker_of_type(typ):
    """类型 → (speaker_name, speaker_id)；返回 None 表示沿用原有判定。

    1 / 2 是旁白、演出、内心独白，显式返回 (None, None) 清掉误判的说话人
    （例如「尼恩拖着沉重的脚步走开了。」这类带立绘 ID 的旁白）。
    """
    if typ == 4:
        return SELF_NAME, "Self"
    if typ == 5:
        return SELF_NAME, "Choice"
    if typ in (1, 2):
        return None, None
    return None
