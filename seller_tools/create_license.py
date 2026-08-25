# -*- coding: utf-8 -*-
"""卖家工具②给买家生成激活码（私钥只在你手里，本地运行）。

用法：
    # 绑定到某台电脑(推荐, 防共享):先让买家把激活框里显示的“机器码”发给你
    python create_license.py --name "买家A" --order 12345 --machine "买家机器码"

    # 不预绑定机器(对应软件里 BIND_MODE="self"):买家的这一台在首次激活时自绑定
    python create_license.py --name "买家A" --order 12345

    # 指定产品名 / 有效期(0=永久买断)
    python create_license.py --name "买家A" --order 12345 --product StockScreenerPro --exp 0

输出：一段激活码(整段复制发给买家)。
"""
import argparse
import base64
import datetime
import json
import os
import secrets
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PRIV = os.path.join(HERE, "private.pem")


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def make_license(private_key, name, order, product, machine, exp):
    payload = {
        "sub": "ln_%s_%s" % (order or "x", secrets.token_hex(3)),
        "name": name,
        "product": product,
        "iat": int(time.time()),
        "exp": int(exp),
        "machine": machine or "",
        "perpetual": True if int(exp) <= 0 else False,
    }
    payload_b64 = _b64u(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    sig = private_key.sign(payload_b64.encode("ascii"))
    return payload_b64 + "." + _b64u(sig)


def main():
    ap = argparse.ArgumentParser(description="生成 Stock Screener Pro 离线激活码")
    ap.add_argument("--name", default="", help="买家名字/备注")
    ap.add_argument("--order", default="", help="订单/单号")
    ap.add_argument("--product", default="StockScreenerPro", help="产品名(与软件端 PRODUCT_ID 一致)")
    ap.add_argument("--machine", default="", help="推荐:买家激活框显示的机器码")
    ap.add_argument("--exp", default=0, type=int, help="到期 unix 秒;0=永久买断")
    ap.add_argument("--trial", default=0, type=int, help="试用天数,自动算 N 天后到期(与 --exp 二选一,优先用 --trial)")
    ap.add_argument("--priv", default=DEFAULT_PRIV, help="私钥文件路径")
    args = ap.parse_args()

    if not os.path.exists(args.priv):
        print("[!] 找不到私钥 %s" % args.priv)
        print("    请先运行: python seller_tools/gen_keys.py  生成密钥对。")
        return

    with open(args.priv, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    # 计算到期时间：--trial 优先（今天 + N 天），否则用 --exp；0 = 永久
    exp = args.exp
    if args.trial and args.trial > 0:
        exp = int(time.time()) + args.trial * 86400
        trial_days = args.trial
    else:
        trial_days = 0

    token = make_license(
        private_key=private_key,
        name=args.name,
        order=args.order,
        product=args.product,
        machine=args.machine,
        exp=exp,
    )

    print()
    print("=" * 60)
    print("LICENSE KEY (copy the whole line below and send it to the buyer):")
    print("=" * 60)
    print(token)
    print("=" * 60)
    print("Buyer:%s  |  Order:%s  |  Product:%s" % (args.name or "-", args.order or "-", args.product))
    if trial_days > 0:
        print("Type:%d-day TRIAL  |  Expires:%s" % (
            trial_days, datetime.datetime.fromtimestamp(exp, tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")))
    elif exp and exp > 0:
        print("Expires:%s" % datetime.datetime.fromtimestamp(exp, tz=datetime.timezone.utc).isoformat())
    else:
        print("Expires:Perpetual (one-time purchase)")
    print("Pre-bound machine:%s" % (args.machine or "none (BIND_MODE=self, binds on first activation)"))


if __name__ == "__main__":
    main()
