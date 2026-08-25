# -*- coding: utf-8 -*-
"""Stock Screener Pro — 离线激活（签名 Key）客户端核心。

这是要随软件一起打包的模块，用它来：
  1. 判断本机是否已激活（本地验签 + 机器绑定）。
  2. 首次启动弹出激活框，让用户输入激活码。
  3. 验签通过后把“已激活”记录保存到本机（并绑定到当前机器）。

【卖家部署前必须填的两个地方】
  * PUBLIC_KEY_B64 —— 运行 seller_tools/gen_keys.py 后，把它打印出来的那串公钥值填到这里。
  * PRODUCT_ID      —— 默认 "StockScreenerPro"，与 create_license.py 里 --product 保持一致。

【机器绑定模式 BIND_MODE】
  "pre"   (推荐, 真正绑定单机) —— 激活码必须已预绑定到某台电脑(create_license --machine 生成)，
          只能在该机型上用，防共享。用户在激活框里把“机器码”发给卖家。
  "self"  (更简单)              —— 激活码本身不绑机器，首次激活时绑定到当前电脑；
          缺点:同一激活码可在另一台电脑上再次激活(可被分享)。
  "none"                        —— 不绑机器，任何电脑都能激活(最宽松，最容易被分享)。
"""
import base64
import hashlib
import json
import os
import platform
import sys
import time
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

# ===== 卖家填入 =====
PUBLIC_KEY_B64 = "6ItW7yXyGLh1I8l8tD60JzeR9+4Bqj2ZJd82+lK16ts="              # ★ 运行 seller_tools/gen_keys.py，把打印的 public key 填这里
PRODUCT_ID = "StockScreenerPro"
BIND_MODE = "pre"                # pre | self | none

LICENSE_FILE_NAME = "license.dat"

# 开发便利开关：只有“非打包运行”时，设 SCREENER_SKIP_LICENSE=1 可跳过激活（打包版无效）
def _dev_skip_enabled():
    return (not getattr(sys, "frozen", False)) and os.environ.get("SCREENER_SKIP_LICENSE") == "1"


# ----------------------------- 编解码 -----------------------------
def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _public_key():
    if not PUBLIC_KEY_B64:
        raise ValueError("The software is not configured with a public key. Please contact the seller.")
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY_B64))


# ----------------------------- 机器指纹 -----------------------------
def get_machine_id():
    """计算本机稳定指纹(SHA256)。原始信息不出本机，仅用于比对。"""
    parts = []
    if sys.platform.startswith("win"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
                parts.append(winreg.QueryValueEx(k, "MachineGuid")[0])
        except Exception:
            pass
    elif sys.platform == "darwin":
        try:
            data = os.popen("ioreg -rd1 -c IOPlatformExpertDevice").read()
            for line in data.splitlines():
                if "IOPlatformUUID" in line:
                    parts.append(line.split('"')[-2])
                    break
        except Exception:
            pass
    else:
        for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                with open(p, "r") as f:
                    parts.append(f.read().strip())
                    break
            except Exception:
                pass
    parts.append(platform.node())
    parts.append(str(uuid.getnode()))
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


# ----------------------------- 验签 -----------------------------
def verify_token(token: str, machine_id: str = "", bind_mode: str = None):
    """验签并检查有效性。返回 payload；无效则抛 ValueError。"""
    bind_mode = bind_mode if bind_mode is not None else BIND_MODE
    token = (token or "").strip()
    if "." not in token:
        raise ValueError("Invalid activation code format.")
    payload_b64, sig_b64 = token.rsplit(".", 1)
    _public_key().verify(_b64u_decode(sig_b64), payload_b64.encode("ascii"))
    payload = json.loads(_b64u_decode(payload_b64))

    if payload.get("product") and payload.get("product") != PRODUCT_ID:
        raise ValueError("This activation code does not match this product.")

    exp = int(payload.get("exp", 0))
    if exp > 0 and time.time() > exp:
        raise ValueError("This activation code has expired.")

    # 机器绑定
    if bind_mode == "pre":
        required = payload.get("machine") or ""
        if not required or required != machine_id:
            raise ValueError("This activation code is not bound to this computer.")
    # "self" 与 "none" 不做激活码层面的机器校验(由本机记录承担)。
    return payload


# ----------------------------- 许可证管理 -----------------------------
def _license_dir():
    """持久化的许可证存放目录(可写、随用户走)。"""
    try:
        from utils import cache_dir
        return cache_dir()
    except Exception:
        pass
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "StockScreenerPro")
    else:
        d = os.path.join(os.path.expanduser("~"), ".config", "StockScreenerPro")
    os.makedirs(d, exist_ok=True)
    return d


class LicenseManager:
    def __init__(self, license_path=None, bind_mode=None, product_id=None):
        self.bind_mode = bind_mode or BIND_MODE
        self.product_id = product_id or PRODUCT_ID
        if license_path is None:
            self.license_path = os.path.join(_license_dir(), LICENSE_FILE_NAME)
        else:
            self.license_path = license_path

    def _read_record(self):
        if not os.path.exists(self.license_path):
            return None
        try:
            with open(self.license_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _write_record(self, token, machine_id):
        os.makedirs(os.path.dirname(self.license_path), exist_ok=True)
        data = {"token": token, "machine_id": machine_id, "activated_at": int(time.time())}
        tmp = self.license_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self.license_path)

    def is_activated(self):
        if _dev_skip_enabled():
            return True
        rec = self._read_record()
        if not rec or not rec.get("token"):
            return False
        machine_id = get_machine_id()
        try:
            verify_token(rec["token"], machine_id, self.bind_mode)
            if self.bind_mode == "self" and rec.get("machine_id") != machine_id:
                return False
            return True
        except Exception:
            return False

    def activate(self, token):
        """验证激活码并保存到本机。返回 (ok, msg)。"""
        machine_id = get_machine_id()
        try:
            verify_token(token, machine_id, self.bind_mode)
        except Exception as e:
            return False, str(e)
        self._write_record(token, machine_id)
        return True, "激活成功"

    def get_machine_code(self):
        """本机机器码，供买家发给卖家做“预绑定”用。"""
        return get_machine_id()

    def get_license_info(self):
        """返回授权信息（供界面显示：永久 / 试用到期 / 授权人）。"""
        rec = self._read_record()
        if not rec or not rec.get("token"):
            return {"activated": False, "expired": False, "type": "Not activated", "detail": "", "name": ""}
        try:
            payload = verify_token(rec["token"], get_machine_id(), self.bind_mode)
        except Exception:
            # 尝试区分“试用已到期”与“未激活/无效”
            expired = False
            try:
                payload_b64, _ = rec["token"].rsplit(".", 1)
                p = json.loads(_b64u_decode(payload_b64))
                e = int(p.get("exp", 0))
                if e > 0 and time.time() > e:
                    expired = True
            except Exception:
                pass
            return {"activated": False, "expired": expired,
                    "type": "Trial (expired)" if expired else "Not activated",
                    "detail": "", "name": ""}
        exp = int(payload.get("exp", 0))
        perpetual = bool(payload.get("perpetual")) or exp <= 0
        if perpetual:
            ltype, detail = "Perpetual (Lifetime)", "No expiry — lifetime license"
        else:
            from datetime import datetime, timezone
            ltype = "Trial"
            detail = ("Expires %s UTC" % datetime.fromtimestamp(exp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"))
        return {
            "activated": True,
            "expired": False,
            "name": payload.get("name", ""),
            "product": payload.get("product", ""),
            "type": ltype,
            "detail": detail,
            "perpetual": perpetual,
            "exp": exp,
        }
