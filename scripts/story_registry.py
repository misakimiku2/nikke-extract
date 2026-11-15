"""妮姬个人剧情 / 支线剧情 / 外传与前哨基地日常 的分组与命名规则。

这三类的 group_key 都是「单元 slug + 章节号」，但界面上应该显示成
「一个角色 / 地点 / 支线任务 + 若干章节」。这里集中维护：

  - 外传地点 slug -> Locale_Outpost 的 outpost_building_name_*
  - 支线内容（d_contents_*）的中文名
  - 个人剧情卡标题（角色名 + 皮肤）：优先用咨询会话标题反推角色名
  - 支线任务（d_subquest_*）的卡标题与章节标题：来自 Locale_SubQuest 的
    sub_quest_description_<code>（形如「【第2章】调查红辣椒所说的地区」）
"""
import re

# 外传地点 slug 与 Locale_Outpost 的 key 不完全一致
OUTPOST_ALIASES = {
    "cafe": "caffe",
    "clothingstore": "clothesstore",
    "command": "commandcenter",
    "maidcafe": "maidcaffe",
    "police": "policestation",
    "shopping": "shoppingmall",
    # 无线电塔的剧情 key 就叫 tower
    "tower": "radiotower",
}

# 支线内容没有统一的 <group>_title，这里给中文名
CONTENTS_TITLES = {
    "arcade": "游戏中心",
    "arena": "Arena",
    "elysiontower": "极乐净土之塔",
    "missilystower": "米西利斯之塔",
    "pilgrimtower": "朝圣者之塔",
    "tetratower": "泰特拉之塔",
    "tribetower": "无限之塔",
    "overspectower": "朝圣者／超标准之塔",
    "explore": "地面探索",
    "favorite": "珍视之物",
    "liberation": "更生馆",
    "lostsector": "迷失地区",
    "simulationroom": "模拟室",
    "surface_beta_guide": "地面β：指南",
    "surface_beta_trial": "地面β：试炼",
    "tracingthestars": "Tracing the Stars",
    "mog2": "传奇游戏",
}

# 咨询标题里没有、但个人剧情确实存在的皮肤后缀
SKIN_TITLES = {
    "fortunemate": "Fortunemate",
    "boomandshock": "BOOM & SHOCK",
    "ultimatehero": "究极英雄",
    "baygoddess": "海湾女神",
}

# 联动个人剧情加作品前缀，避免和同名本家角色撞标题
COLLAB_TITLES = {
    "2": "NieR AUTOMATA",
    "3": "RE:ZERO",
    "4": "EVANGELION",
    "5": "EVANGELION: WILLE",
    "6": "STELLAR BLADE",
    "7": "RESIDENT EVIL",
    "8": "LYCORIS RECOIL",
    "9": "PERSONA",
}
COLLAB_KEY = re.compile(r"^ce_?0*(\d+)_\d+$")

# 咨询标题格式不标准的（皮肤名里多了「的」等），单独兜底
MANUAL_COUNSEL = {
    "littlemermaid": ("小美人鱼", None),
    "mast_romanticmaid": ("马斯特", "浪漫的女仆"),
}

# 「与爱德：特工兔女郎的咨询：01」
COUNSEL_TITLE = re.compile(r"^(?:与)?([^：]+?)(?:[：:](.+?))?的?(?:咨询|追忆|回忆)[：:]\d+$")


def prettify(slug: str) -> str:
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", slug or "")
    s = s.replace("_", " ").strip()
    return s[:1].upper() + s[1:] if s else s


def counsel_index(titles: dict) -> dict:
    """{slug: (角色名, 皮肤名)}；titles 为 Locale_Counseling 的 <group>_title。"""
    out = dict(MANUAL_COUNSEL)
    for slug, t in titles.items():
        m = COUNSEL_TITLE.match((t or "").strip())
        if not m:
            continue
        char, skin = m.group(1), m.group(2)
        if skin:
            skin = re.sub(r"的$", "", skin).strip() or None
        out[slug] = (char, skin)
    return out


def nikke_title(slug: str, counsel: dict, dominant: str | None = None) -> str:
    """个人剧情卡标题。优先咨询映射，其次「基础角色 + 皮肤后缀」，再次剧情里
    说话最多的人。联动单元额外加作品名前缀。"""
    char = skin = None
    if slug in counsel:
        char, skin = counsel[slug]
    else:
        def char_of(key):
            hit = counsel.get(key.lower())
            return hit[0] if hit else None

        base, _, sfx = slug.partition("_")
        if sfx:
            skin = SKIN_TITLES.get(sfx.replace("_", "").lower())
            if skin:
                char = char_of(base) or dominant
            elif char_of(base):
                char = char_of(base)
                skin = prettify(sfx)
        if not skin:
            # 没有下划线的情况：按已知皮肤后缀切一刀（eleggboomandshock）
            for key in sorted(SKIN_TITLES, key=len, reverse=True):
                if slug.lower().endswith(key) and len(slug) > len(key):
                    stem = slug[:-len(key)]
                    skin = SKIN_TITLES[key]
                    char = char_of(stem) or dominant or prettify(stem)
                    break
        if not char:
            char = dominant or prettify(slug)
    name = f"{char}：{skin}" if skin else char

    m = COLLAB_KEY.match(slug)
    collab = COLLAB_TITLES.get(str(int(m.group(1)))) if m else None
    return f"{collab} · {name}" if collab else name


def outpost_title(slug: str, get) -> str:
    key = "outpost_building_name_" + OUTPOST_ALIASES.get(slug, slug)
    return get("Locale_Outpost", key) or prettify(slug)


def contents_title(bucket: str, raw: str | None = None) -> str:
    slug = bucket[len("d_contents_"):] if bucket.startswith("d_contents_") else bucket
    return CONTENTS_TITLES.get(slug) or raw or prettify(slug)


def series_title(raw: str | None, fallback: str) -> str:
    """支线故事的卷名：「第二种情感：1」->「第二种情感」，「MUDFISH : 1」->「MUDFISH」。"""
    if not raw:
        return fallback
    t = re.sub(r"\s*[：:]\s*(?:\d+|尾声|[A-Z])\s*$", "", raw).strip()
    return t or raw


SUB_KEY = re.compile(r"^d_subquest_(\d{3})(\d)(?:_\d+)?(?:_([se]))?$")


def subquest_code(group: str):
    """d_subquest_1011 -> (family '101', code '1011', 's'/'e'/None)"""
    m = SUB_KEY.match(group)
    if not m:
        return None
    fam, last, se = m.group(1), m.group(2), m.group(3)
    return fam, fam + last, se


def subquest_desc(fam: str, get) -> str | None:
    for i in range(10):
        v = get("Locale_SubQuest", f"sub_quest_description_{fam}{i}")
        if v:
            return v
    return None


def desc_action(desc: str | None) -> str:
    return re.sub(r"^【第\d+章】\s*", "", (desc or "").strip()).strip()


def subquest_title(fam: str, get) -> str:
    desc = subquest_desc(fam, get)
    action = desc_action(desc)
    return f"支线任务 · {action}" if action else f"支线任务 {fam}"


def subquest_chapter(group: str, get) -> str | None:
    """章节标题：「第02章 · 调查红辣椒所说的地区」；_s/_e 再标前篇/后篇。"""
    parsed = subquest_code(group)
    if not parsed:
        return None
    _fam, code, se = parsed
    desc = get("Locale_SubQuest", f"sub_quest_description_{code}")
    if not desc:
        return None
    m = re.match(r"^【第(\d+)章】\s*(.*)$", desc.strip())
    if m:
        title = f"第{int(m.group(1)):02d}章 · {m.group(2).strip()}"
    else:
        title = desc.strip()
    if se == "s":
        title += "（前篇）"
    elif se == "e":
        title += "（后篇）"
    return title
