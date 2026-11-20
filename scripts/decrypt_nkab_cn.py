"""NIKKE 国服（WeGame PC 版）NKAB v4 资源 bundle 解密器。

2026-11-20 由 Il2CppDumper + GameAssembly 反汇编逆向，与社区已知国际服 v3 算法
（Razmoth / kiraio-moe Nikke-NKAB-Decrypter）同源但密钥来源与头部布局已改。

头部布局（132 字节 @0x00-0x83）:
    0x00  "NKAB" + u32 version(=4)
    0x08  6 × u16 混淆字段（存储值 = 明文 + obf，obf = 文件末 2 字节的 u16）
          de-obf 后依次:
            blockCount    (>>8=头加密区 256B 组数, &0xFF=尾加密区组数; 0=全文件掩码)
            encryptFlags  (位掩码, 块 idx=组内序号, bit=0x8000>>idx)
            keyIndex      (0-4)
            keyMode       (实测恒 1，未参与解密)
            keyVersion    (对应 KeySets 版本，2026-11 时为 10-14)
            X             (含义未定)
    0x14  32B 文件常量 —— 密钥派生材料
    0x34  16B Salt（字段存在但实测未使用）
    0x44  64B 签名区（未读）
    0x84  payload = 原始 UnityFS bundle（UnityFS 头 v7+ 有 16B 对齐与
          BlockInfoNeedPaddingAtStart 语义，交由 UnityPy 正常解析）
末 2B  obf（同时是 bundle 最后一块的密文一部分——读取 obf 后这 2 字节仍要参与解密）

密钥派生:
    tableKey = KeySets[keyVersion][keyIndex]        （32B，来自客户端 settings.json）
    aesKey   = SHA256( tableKey ‖ file[0x14:0x34] ) （v3 同款拼接哈希）
    AES-256-ECB，逐 16B 块：加密块 P = AES_dec(C)（无 IV/链接）

KeySets 来源: 游戏目录 nikke_Data/StreamingAssets/aa/settings.json 的
m_ExtraInitializationData[0].m_Data（内嵌 JSON 字符串）.KeySets。
游戏更新会追加新 keyVersion（旧版保留），用 --update-keysets 重新提取。

用法:
    python scripts/decrypt_nkab_cn.py <in> <out>          # 单文件
    python scripts/decrypt_nkab_cn.py --update-keysets    # 从客户端刷新密钥表
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import pathlib

from Crypto.Cipher import AES

GAME_ROOT = os.environ.get(
    "NIKKE_CN_GAME",
    r"C:\Program Files\GAME\胜利女神：新的希望(2002017)",
)

# 完整密钥表存放在同目录 cn_keysets_cn.json（2026-11-20 自国服 23.4 客户端提取）。
# 游戏更新追加新 keyVersion 后运行 --update-keysets 刷新。


def _load_embedded_keysets() -> dict[int, list[bytes]]:
    p = pathlib.Path(__file__).with_name("cn_keysets_cn.json")
    if not p.exists():
        raise FileNotFoundError("cn_keysets_cn.json 缺失，请运行 --update-keysets")
    raw = json.loads(p.read_text())
    return {int(v): [bytes.fromhex(k) for k in ks] for v, ks in raw.items()}


def keysets_from_settings(game_root: str = GAME_ROOT) -> dict[int, list[str]]:
    """从客户端 settings.json 提取完整 KeySets（返回 hex 字符串表）"""
    p = pathlib.Path(game_root) / "nikke_Data/StreamingAssets/aa/settings.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    result = []
    for item in d.get("m_ExtraInitializationData", []):
        s = item.get("m_Data", "")
        if "KeySets" in s:
            result.append(json.loads(s))
    if not result:
        raise ValueError("settings.json 中未找到 KeySets（客户端结构可能变化）")
    out: dict[int, list[str]] = {}
    for ks in result[-1]["KeySets"]:  # 取最新一份（可能多份叠加）
        out[ks["version"]] = [bytes(k["Bytes"]).hex().upper() for k in ks["keys"]]
    return out


def read_header(data: bytes) -> dict:
    if data[:4] != b"NKAB":
        raise ValueError(f"not NKAB: {data[:8]!r}")
    version = struct.unpack_from("<I", data, 4)[0]
    obf = struct.unpack_from("<H", data, len(data) - 2)[0]
    fields = [(struct.unpack_from("<H", data, 8 + i * 2)[0] + obf) & 0xFFFF for i in range(6)]
    return dict(
        version=version,
        obf=obf,
        block_count=fields[0],
        encrypt_flags=fields[1],
        key_index=fields[2],
        key_mode=fields[3],
        key_version=fields[4],
        extra=fields[5],
        key_material=data[0x14:0x34],
        salt=data[0x34:0x44],
        payload_offset=0x84,
    )


def is_encrypted(flags: int, index: int) -> bool:
    return (flags & (0x8000 >> index)) != 0


def decrypt(data: bytes, keysets: dict[int, list[bytes]] | None = None) -> tuple[bytes, dict]:
    h = read_header(data)
    if h["version"] != 4:
        raise ValueError(f"unsupported NKAB version {h['version']}")
    ks = keysets or _load_embedded_keysets()
    if h["key_version"] not in ks or h["key_index"] >= len(ks[h["key_version"]]):
        raise ValueError(f"key {h['key_version']}/{h['key_index']} 不在密钥表中，"
                         f"尝试 --update-keysets")
    table_key = ks[h["key_version"]][h["key_index"]]
    aes_key = hashlib.sha256(table_key + h["key_material"]).digest()
    cipher = AES.new(aes_key, AES.MODE_ECB)

    payload = bytearray(data[h["payload_offset"]:])
    flags = h["encrypt_flags"]
    hb, fb = h["block_count"] >> 8, h["block_count"] & 0xFF
    total = len(payload)

    def decrypt_region(start: int, size: int):
        for i in range(start, min(start + size, total - 15), 16):
            if is_encrypted(flags, (i // 16) % 16):
                seg = bytes(payload[i:i + 16])
                if len(seg) < 16:
                    seg += b"\0" * (16 - len(seg))
                payload[i:i + 16] = cipher.decrypt(seg)

    if hb == 0 and fb == 0:
        decrypt_region(0, total)
    else:
        # v3 式头/尾分区：头 hB×256B、尾 fB×256B 为加密区，中间为明文
        head_size = 0x10 * min(hb * 0x10, total // 0x10)
        foot_size = 0x10 * min(fb * 0x10, (total - head_size) // 0x10)
        decrypt_region(0, head_size)
        if foot_size > 0:
            decrypt_region(total - foot_size, foot_size)
    out = bytes(payload)
    # UnityFS size 字段（BE i64 @ payload+0x1E）= bundle 真实长度，裁掉容器尾部
    try:
        size = struct.unpack_from(">q", out, 0x1E)[0]
        if 0 < size <= len(out):
            out = out[:size]
    except struct.error:
        pass
    return out, h


def decrypt_file(src: str | os.PathLike, dst: str | os.PathLike,
                 keysets: dict[int, list[bytes]] | None = None) -> dict:
    raw = pathlib.Path(src).read_bytes()
    out, h = decrypt(raw, keysets)
    pathlib.Path(dst).write_bytes(out)
    return h


def main() -> None:
    if "--update-keysets" in sys.argv:
        ks = keysets_from_settings()
        dst = pathlib.Path(__file__).with_name("cn_keysets_cn.json")
        dst.write_text(json.dumps({str(v): k for v, k in sorted(ks.items())}, indent=1),
                       encoding="utf-8")
        print(f"keysets -> {dst}: versions {sorted(ks)}")
        return
    if len(sys.argv) < 3:
        print(__doc__)
        return
    h = decrypt_file(sys.argv[1], sys.argv[2])
    print(f"{sys.argv[1]}: ver={h['version']} keyver={h['key_version']} "
          f"keyidx={h['key_index']} flags={h['encrypt_flags']:#06x} "
          f"blocks={h['block_count']:#06x}")


if __name__ == "__main__":
    main()
