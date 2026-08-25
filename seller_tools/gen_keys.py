# -*- coding: utf-8 -*-
"""卖家工具①生成 Ed25519 密钥对（只跑一次，私钥只留在你本地）。

用法：
    cd seller_tools
    pip install cryptography
    python gen_keys.py

结果：
    private.pem -> 私钥，只在你手里，绝不放进软件/不提交 git/不发买家
    public.pem  -> 公钥 pem

最后会打印一行 PUBLIC_KEY_B64，把它填进软件里的 licensing/license_manager.py 的 PUBLIC_KEY_B64。
"""
import base64
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

HERE = os.path.dirname(os.path.abspath(__file__))
PRIV = os.path.join(HERE, "private.pem")
PUB = os.path.join(HERE, "public.pem")


def main():
    if os.path.exists(PRIV):
        with open(PUB, "rb") as f:
            pub_pem = f.read()
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        pub = load_pem_public_key(pub_pem)
        raw = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        print("[!] private.pem already exists — not overwriting. Public key:")
        _print_b64(raw)
        return

    private_key = Ed25519PrivateKey.generate()
    priv_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    with open(PRIV, "wb") as f:
        f.write(priv_pem)

    public_key = private_key.public_key()
    pub_pem = public_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    with open(PUB, "wb") as f:
        f.write(pub_pem)

    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    print("[OK] Generated:")
    print("  ", PRIV, "  <- PRIVATE key (never share, never commit to git, back it up)")
    print("  ", PUB, "  <- PUBLIC key pem")
    print()
    print("Fill the value below into  PUBLIC_KEY_B64  in licensing/license_manager.py:")
    _print_b64(raw)


def _print_b64(raw: bytes):
    print("=" * 60)
    print(base64.b64encode(raw).decode("ascii"))
    print("=" * 60)


if __name__ == "__main__":
    main()
