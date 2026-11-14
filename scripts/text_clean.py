"""Shared text normalization for every NIKKE scenario export.

The client template `{AccountData.NickName}` is replaced with 指挥官 in all
deliverables (md AND json), so every export script must call clean() when it
writes a zh-CN value.
"""
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
