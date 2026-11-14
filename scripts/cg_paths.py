"""Shared path rules for CG asset names -> library folders."""
import re

MIN_CG_SIDE = 512


def classify(name: str) -> str:
    """Map an EventScene_* asset name to a folder path inside CG/."""
    tail = name[len("EventScene_"):]
    parts = tail.split("_")
    head = parts[0]
    low = head.lower()

    if low == "chap":
        ch = next((p for p in parts[1:] if p.isdigit()), None)
        return f"02_主线剧情CG/第{int(ch):02d}章" if ch else "02_主线剧情CG/其他章节"
    if low == "side":
        return "03_支线剧情CG"
    if re.fullmatch(r"(c|ce)\d*", low):
        return "04_角色过场"
    if low in ("main", "event"):
        return "02_主线剧情CG/其他章节"
    if low in ("si", "mi", "ps", "at", "as"):
        return "05_其他动态CG"

    merged = re.sub(r"\d+$", "", head) if len(head) >= 5 and not low.startswith("ce") else head
    if merged and len(merged) >= 4:
        head = merged
    return "01_活动剧情CG/" + head
