import pathlib

STATIC = pathlib.Path(r"E:\test\nikke_extract\staticdata")
b = (STATIC / "SkillInfoTable.mpk").read_bytes()
start = 637180
seg = b[start:start + 560]
for i in range(0, len(seg), 16):
    c = seg[i:i + 16]
    print(f"{start + i:7d}  " + " ".join(f"{x:02x}" for x in c).ljust(48)
          + "  " + "".join(chr(x) if 32 <= x < 127 else "." for x in c))
