"""活动剧情的分组与命名规则。

游戏里活动剧情不是按“段落”展示的，而是「一个活动 + 若干章节」：

  event_overzone1_prologue        -> OVER ZONE · 序章
  event_overzone1_01_s / _01_e    -> OVER ZONE · 第1章（前篇/后篇）
  event_overzone1_intermission_01 -> OVER ZONE · 幕间
  event_overzone2_*               -> 同一个 OVER ZONE 的第2部

官方活动名来自 Locale_System 的 RECORD_EVENT_TITLE / STORY_DUNGEON_TITLE，
章节名来自 Locale_MainScenario 的 <group>_title。这里集中维护「段落 -> 活动 key」
的别名、活动显示名，以及章节标题格式化，避免 export_rest.py 里散落一堆特判。
"""
import re

# 活动 key -> 显示名。未列出的 key 会退化成大写可读形式（2x2love -> 2X2 LOVE）。
EVENT_TITLES = {
    "nocallerid": "NO CALLER ID",
    "hightechtoy": "HIGHTECH TOY",
    "miraclesnow": "MIRACLE SNOW",
    "eternalmemory": "ETERNAL MEMORY",
    "brandnewyear": "BRAND NEW YEAR",
    "d-outsiders": "D-Outsiders",
    "doutsiders": "D-Outsiders",
    "maidinvalentine": "MAID IN VALENTINE",
    "ce01": "BULLET X CHAINSAW",
    "bow-wowparadise": "BOW-WOW PARADISE",
    "bowwowparadise": "BOW-WOW PARADISE",
    "cherryblossom": "CHERRY BLOSSOM",
    "ltk": "L.T.K -License to Kill-",
    "overzone": "OVER ZONE",
    "bunny777": "BUNNY X 777",
    "BunnyX777": "BUNNY X 777",
    "queensorder": "QUEEN'S ORDER",
    "bluewaterisland": "BLUEWATER ISLAND",
    "nya-nyaparadise": "NYA NYA PARADISE",
    "nyanyaparadise": "NYA NYA PARADISE",
    "goldenship": "GOLDEN SHIP",
    "seayouagain": "SEA, YOU, AGAIN",
    "ce002": "OUTER AUTOMATA",
    "schooloflock": "SCHOOL OF LOCK",
    "dazzlingcupid": "耀眼的丘比特",
    "acpufreeze": "A.C.P.U.部队！FREEZE！",
    "freezeacpu": "A.C.P.U.部队！FREEZE！",
    "nonsensered": "NONSENSE RED",
    "outofuniform": "OUT OF UNIFORM",
    "yesmycommander": "YES, MY COMMANDER",
    "chocolateplease": "CHOCOLATE, PLEASE!",
    "mostbeautifulmaid": "MOST BEAUTIFUL MAID",
    "foolmetalpanic": "FOOL METAL PANIC!",
    "foolburstday": "FOOL BURST DAY",
    "liarsend": "LIAR'S END",
    "fullfoolday_end": "FULL FOOL DAY",
    "redash": "RED ASH",
    "alonesurvivor": "ALONE SURVIVOR",
    "neverland": "NEVERLAND",
    "newyearnewsword": "NEW YEAR, NEW SWORD",
    "lionheart": "LION HEART",
    "dirtybackyard": "DIRTY BACKYARD",
    "perfectmaid": "PERFECT MAID",
    "boomsday": "BOOMS DAY",
    "ce003": "RE:ZERO",
    "killthelord": "KILL THE LORD",
    "onemoretime": "ONE MORE TIME",
    "lastkingdom": "LAST KINGDOM",
    "darkhero": "D.ARK HERO",
    "goldencoinrush": "GOLDEN COIN RUSH",
    "claymore": "CLAY, MORE!",
    "beautyfullshot": "BEAUTY FULL SHOT",
    "juveniledays": "JUVENILE DAYS",
    "colorless": "COLORLESS",
    "ce004": "EVANGELION",
    "jinxplayer": "JINX PLAYER",
    "phantomthiefvsdetective": "PHANTOM THIEF VS DETECTIVE",
    "lifeagain": "LIFE AGAIN",
    "oldtales": "OLD TALES",
    "secretgarden": "SECRET GARDEN",
    "icedragonsaga": "ICE DRAGON SAGA",
    "footstepwalkrun": "FOOTSTEP, WALK, RUN",
    "wisdomspring": "WISDOM SPRING",
    "romanticvalentine": "ROMANTIC VALENTINE",
    "ce005": "EVANGELION: WILLE",
    "forrest": "FOR REST",
    "newflavor": "NEW FLAVOR",
    "trueflavor": "TRUE FLAVOR",
    "unbreakablesphere": "UNBREAKABLE SPHERE",
    "arcanearchive": "ARCANE ARCHIVE",
    "lordforjustice": "LORD, FOR JUSTICE",
    "ce006": "STELLAR BLADE",
    "overthehorizon": "OVER THE HORIZON",
    "boomtheghost": "BOOM! THE GHOST!",
    "absolute": "ABSOLUTE",
    "coinsinrush": "COINS IN RUSH",
    "ce007": "RESIDENT EVIL",
    "goninjathief": "GO! NINJA THIEF!",
    "goddessfall": "GODDESS FALL",
    "blankticket": "BLANK TICKET",
    "terminusticket": "TERMINUS TICKET",
    "arkguardian": "ARK GUARDIAN",
    "sineditor": "SIN EDITOR",
    "fatalmaid": "FATAL MAID",
    "ce008": "LYCORIS RECOIL",
    "enterheaven": "ENTER HEAVEN",
    "2x2love": "2X2 LOVE",
    "goodworld": "GOOD WORLD",
    "staranis": "STAR ANIS",
    "bsideidol": "B-SIDE IDOL",
    "bitterspice": "BITTER SPICE",
    "arkranger": "ARK RANGER",
    "wavetoyou": "WAVE TO YOU",
    "projectmatis": "PROJECT MATIS",
    "ce009": "PERSONA",
    "greatvillainunion": "GREAT VILLAIN UNION",
    "coinrushshowdown": "COIN RUSH SHOWDOWN",
    "littlewitchtrick": "LITTLE WITCH TRICK",
    "marian": "MARIAN",
    "skyontherock": "SKY ON THE ROCK",
    # 独立小游戏 / 纪念活动
    "bbqmaster": "BBQ MASTER",
    "2024summer_fishing": "2024 SUMMER · FISHING",
    "2024summer_picture": "2024 SUMMER · PICTURE",
    "bfgcleanup": "BFG! CLEAN UP!",
    "giftfactory": "GIFT FACTORY",
    "islandbreaker": "ISLAND BREAKER",
    "nativeraid": "NATIVE RAID",
    "piratecafe": "PIRATE CAFE",
    "rebuildeden": "REBUILD EDEN",
    "return": "RETURN",
    "threecompanyrumble": "THREE COMPANY RUMBLE",
    "voltroad": "VOLT ROAD",
    "whitememory": "WHITE MEMORY",
    "eden": "EDEN",
    "fightarkranger": "FIGHT ARK RANGER",
    "azxservicetime": "AZX SERVICE TIME",
    "dessertrush": "DESSERT RUSH",
    "madeinrush": "MADE IN RUSH",
    "dungeon_run": "DUNGEON RUN",
    "bubblemarch": "BUBBLE MARCH",
    "snowfall": "SNOWFALL",
    "1ann_mini": "1ST ANNIVERSARY MINI",
    "aniversary": "ANNIVERSARY",
    "1yearalready": "1 YEAR ALREADY",
    "fullfoolday": "FULL FOOL DAY",
    "firstaffection": "FIRST AFFECTION",
    "foolburstday": "FOOL BURST DAY",
    "foolmetalpanic": "FOOL METAL PANIC!",
    "chocolateplease": "CHOCOLATE, PLEASE!",
    "liarsend": "LIAR'S END",
    "mostbeautifulmaid": "MOST BEAUTIFUL MAID",
    "nonsensered": "NONSENSE RED",
    "outofuniform": "OUT OF UNIFORM",
    "yesmycommander": "YES, MY COMMANDER",
}

# 前缀别名，按最长前缀优先匹配。用于合并多部曲、把 EX/小游戏挂到对应活动。
EVENT_ALIASES = [
    # 多部曲
    ("event_miraclesnow", "miraclesnow"),
    ("event_overzone", "overzone"),
    ("event_bluewaterisland", "bluewaterisland"),
    ("event_seayouagain", "seayouagain"),
    ("event_redash", "redash"),
    ("event_neverland", "neverland"),
    ("event_beautyfullshot", "beautyfullshot"),
    ("event_icedragonsaga", "icedragonsaga"),
    ("event_footstepwalkrun", "footstepwalkrun"),
    ("event_unbreakablesphere", "unbreakablesphere"),
    ("event_absolute", "absolute"),
    ("event_arkguardian", "arkguardian"),
    ("event_arkranger", "arkranger"),
    ("event_wavetoyou", "wavetoyou"),
    ("event_projectmatis", "projectmatis"),
    ("event_coinrushshowdown", "coinrushshowdown"),
    ("event_goddessfall", "goddessfall"),
    ("event_boomtheghost", "boomtheghost"),
    ("event_coinsinrush", "coinsinrush"),
    ("event_staranis", "staranis"),
    ("event_terminusticket", "terminusticket"),
    ("event_lastkingdom", "lastkingdom"),
    ("event_goldencoinrush", "goldencoinrush"),
    ("event_oldtales", "oldtales"),
    ("event_marian", "marian"),
    ("event_skyontherock", "skyontherock"),
    # 联动
    ("event_fullfoolday_end", "fullfoolday"),
    ("event_ce_01", "ce01"),
    ("event_ce02", "ce002"),
    ("event_ce002", "ce002"),
    ("re_event_ce02", "ce002"),
    ("re_d_contents_ce002_mini", "ce002"),
    ("d_contents_ce002_mini", "ce002"),
    ("event_ce003", "ce003"),
    ("event_ce004", "ce004"),
    ("event_ce005", "ce005"),
    ("event_ce006", "ce006"),
    ("event_ce007", "ce007"),
    ("event_ce008", "ce008"),
    ("event_ce009", "ce009"),
    # 同一个活动的分支/小游戏
    ("event_twoxtwolove", "2x2love"),
    ("twoxtwolove", "2x2love"),
    ("d_ex_redash", "redash"),
    ("d_ex_seayouagain", "seayouagain"),
    ("d_contents_ce003_mini", "ce003"),
    ("d_contents_ce004_mini", "ce004"),
    ("d_contents_ce009_mini", "ce009"),
    ("d_contents_ce007", "ce007"),
    ("d_contents_bbqmaster", "seayouagain"),
    ("d_contents_2024summer_fishing", "beautyfullshot"),
    ("d_contents_2024summer_picture", "beautyfullshot"),
    ("d_contents_bfgcleanup", "bfgcleanup"),
    ("d_contents_dungeon_run", "dungeon_run"),
    ("d_contents_eden", "eden"),
    ("d_contents_fightarkranger", "arkranger"),
    ("d_contents_giftfactory", "miraclesnow"),
    ("d_contents_islandbreaker", "beautyfullshot"),
    ("d_contents_madeinrush", "goldencoinrush"),
    ("d_contents_nativeraid", "nativeraid"),
    ("d_contents_piratecafe", "goldenship"),
    ("d_contents_rebuildeden", "rebuildeden"),
    ("d_contents_return", "return"),
    ("d_contents_threecompanyrumble", "threecompanyrumble"),
    ("d_contents_voltroad", "voltroad"),
    ("d_contents_whitememory", "miraclesnow"),
    # 雪境小游戏是独立的一整套活动内容，单独成卡，避免 MIRACLE SNOW 被 400+ 段撑爆
    ("snowfall", "snowfall"),
]

_MULTI = re.compile(
    r"^(miraclesnow|overzone|bluewaterisland|seayouagain|redash|neverland|"
    r"beautyfullshot|icedragonsaga|footstepwalkrun|unbreakablesphere|absolute|"
    r"arkguardian|arkranger|wavetoyou|projectmatis|coinrushshowdown|goddessfall|"
    r"boomtheghost|coinsinrush|staranis|terminusticket|lastkingdom|goldencoinrush|"
    r"oldtales|marian|ce003|ce004|ce005|ce006|ce007|ce008|ce009|ce002)[0-9]+$"
)


def event_key_of(group: str) -> str:
    """段落 group_key -> 活动 key。"""
    for prefix, key in EVENT_ALIASES:
        if group.startswith(prefix):
            return key

    g = group
    g = re.sub(r"^(re_event_|d_ex_|d_contents_)", "", g)
    g = re.sub(r"^event_", "", g)
    # 章节后缀：prologue / 01_s / 01_e / intermission_01 / epilogue / b01 ...
    g = re.sub(r"_(prologue|epilogue|intermission_\d+|intermission)(_.*)?$", "", g)
    g = re.sub(r"_b\d+.*$", "", g)
    g = re.sub(r"_\d+_[sem].*$", "", g)
    g = re.sub(r"_\d+$", "", g)
    # 多部曲合并：overzone1/overzone2 -> overzone
    m = _MULTI.match(g)
    if m:
        g = m.group(1)
    return g


def event_title_of(key: str) -> str:
    if key in EVENT_TITLES:
        return EVENT_TITLES[key]
    return re.sub(r"[_\-]+", " ", key).strip().upper()


def chapter_title(group: str, raw_title: str | None) -> str:
    """把 <group>_title 格式化成「序章 / 第N章 / 幕间 / 尾声」。"""
    title = (raw_title or "").strip()
    # 官方章节名常带「：A」「：B」区分前后篇
    base = re.sub(r"[：:]\s*[AB]$", "", title).strip()

    m = re.match(r"^(?P<key>.+?)_(?P<part>prologue|epilogue|intermission_\d+|intermission|\d+_[se]|b\d+.*)$", group)
    if not m:
        return title or group
    part = m.group("part")
    if part == "prologue":
        return f"序章 · {base}" if base else "序章"
    if part == "epilogue":
        return f"尾声 · {base}" if base else "尾声"
    if part.startswith("intermission"):
        return f"幕间 · {base}" if base else "幕间"
    num = re.match(r"^(\d+)_([se])$", part)
    if num:
        # 没有官方 A/B 标题时，用 _s/_e 标出前篇/后篇，避免连续两个「第01章」
        mark = ""
        if re.search(r"[：:]\s*A$", title):
            mark = "（前篇）"
        elif re.search(r"[：:]\s*B$", title):
            mark = "（后篇）"
        elif num.group(2) == "s":
            mark = "（前篇）"
        else:
            mark = "（后篇）"
        return f"第{int(num.group(1)):02d}章 · {base}{mark}" if base else f"第{int(num.group(1)):02d}章{mark}"
    return base or group
