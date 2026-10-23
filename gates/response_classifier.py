"""Central gate response classifier — raw gateway text → Charged / Approved / Declined / Error."""


def classify_gate_response(response) -> str:
    """
    Classify any gate raw response string.
    Returns: 'Charged' | 'Approved' | 'Declined' | 'Error'
    """
    if response is None:
        return 'Error'

    text = None
    if isinstance(response, dict):
        text = str(response.get('Response') or response.get('message') or response.get('msg') or response)
    elif isinstance(response, str):
        try:
            import json
            data = json.loads(response)
            if isinstance(data, dict):
                text = str(data.get('Response') or data.get('message') or data.get('msg') or response)
        except Exception:
            pass

    if text is None:
        text = str(response)

    rl = text.lower().strip()
    if not rl or rl == 'none':
        return 'Error'

    # ── CHARGED (actual payment / order success) ──
    _charged = (
        'order_placed', 'order_paid', 'order placed',
        'charged successfully', 'charged $', 'payment successful',
        'payment processed', 'payment authorised', 'payment authorized',
        'purchase confirmed', 'donation successful', 'donation has been',
        'thank you for your donation', 'thank you for your purchase',
        'thank you for', 'succeeded',
        'authorise', 'authorized', 'authorised',
        'donation processed via authorize', 'donation processed via bluepay',
        'donation processed',
    )
    if any(k in rl for k in _charged):
        return 'Charged'
    if rl.startswith('charged'):
        return 'Charged'

    # ── APPROVED / LIVE (card valid, not charged) ──
    _approved = (
        'approved -', 'approved!', 'approved.',
        'card added successfully', 'card added',
        'payment method successfully added', 'payment method added',
        'new payment method added', 'new payment method',
        'nice! new payment method',
        'visa ending in', 'mastercard ending in', 'amex ending in',
        'discover ending in', 'card ending in',
        'insufficient_funds', 'insufficient funds', 'insufficient',
        'incorrect_cvc', 'incorrect cvc', 'invalid_cvc', 'invalid cvc',
        'inv cvv2', 'cvv2 mismatch', 'cvv mismatch', 'inv cvv',
        'incorrect_cvv', 'invalid_cvv', 'invalid cvv', 'incorrect cvv',
        'invalid_security_code', 'security code is invalid',
        'security code is incorrect', 'incorrect security code',
        'incorrect_zip', 'incorrect zip', 'invalid_billing_address',
        'incorrect billing address', 'billing address is incorrect',
        'authentication_required', 'authentication required',
        'requires_action', '3d secure', '3ds required', '3ds_required',
        '3ds challenge', '3ds redirect', '3ds1 required', '3ds2',
        'warning_continue_3ds', 'challenge required', 'challenge shopper',
        'identify shopper', 'redirect shopper',
        'ccn', 'call_issuer', 'limit_exceeded',
        'existing_account_restricted',
        'otp', 'otp required', 'otp_required', 'verify otp', 'verify card',
        'verification required', 'verification_required',
        'sms', 'sms code', 'sms verification', 'authentication required', 'authentication_required',
        # Razorpay live signals
        'do not honor', 'do_not_honor', 'do not honour',
        'card declined (live)', 'issuer declined', 'transaction limit exceeded',
        'card not enabled for online', 'card blocked', 'pick up card',
        'lost or stolen card', 'refer to card issuer', 'incorrect card details',
        '3ds not enrolled',
    )
    if any(k in rl for k in _approved):
        return 'Approved'
    if 'approved' in rl and 'not approved' not in rl:
        return 'Approved'
    if '3ds' in rl and 'not' not in rl[:20]:
        return 'Approved'

    # ── GATE / SITE ERRORS (not a card verdict) ──
    _gate_err = (
        'timeout', 'timed out', 'connection error', 'connection refused',
        'connection reset', 'ssl', 'error:', 'error -', 'gate error',
        'site error:', 'site error',
        'failed to get', 'failed to create', 'failed to extract',
        'failed to tokenize', 'failed to fetch', 'failed to add',
        'no response detected', 'no response from', 'no response',
        'registration failed', 'login failed', 'not logged in',
        'no account in accounts', 'invalid card format',
        'failed to get form', 'failed to get page', 'failed to get login',
        'failed to get payment', 'failed to get client', 'failed to get auth',
        'failed to get session', 'session expired', 'nonce invalid',
        'could not parse response', 'unknown error in response',
        'empty response', 'tokenization failed', 'no products found',
        'captcha required', 'cloudflare', 'access denied',
        'unprocessable_entity',  # only if not card decline context
        'could not determine response', 'unknown response',
        'failed to extract form hash',
        'try_another_site', 'site_config_error',
        'rate_limited', 'session_blocked', 'endpoint_timeout',
        'connection_failed', 'server_error',
        'waf blocked', 'waf', '403', 'all proxies failed',
        'no register nonce', 'no payment nonce', 'no authnet keys',
        'no address nonce', 'no session_token', 'no key_id',
    )
    # Card-decline words inside an error-looking message → still Declined
    _decline_in_err = (
        'declined', 'decline', 'refused', 'do_not_honor', 'do not honor',
        'stolen', 'expired', 'invalid cvc', 'incorrect cvc', 'insufficient',
    )
    if any(k in rl for k in _gate_err):
        if any(d in rl for d in _decline_in_err):
            return 'Declined'
        return 'Error'

    # ── DECLINED ──
    _declined = (
        'declined', 'card_declined', 'card declined', 'card was declined',
        'generic_decline', 'generic error', 'generic_error',
        'do_not_honor', 'do not honor', 'not approved', 'order_not_approved',
        'refused', 'payment declined', 'payment error',
        'stolen_card', 'stolen card', 'lost_card', 'lost card',
        'pickup_card', 'pickup card', 'fraudulent', 'fraud_suspected', 'fraud suspected',
        'expired_card', 'expired card', 'card expired', 'has expired',
        'invalid_number', 'incorrect_number', 'invalid number',
        'card_not_supported', 'not supported', 'restricted_card',
        'transaction_not_allowed', 'card_velocity_exceeded', 'velocity exceeded',
        'not_permitted', 'security_violation', 'processing_error',
        'unknown response', 'invalid account', 'account closed',
        'card brand blocked', 'card_brand_blocked',
        'transaction declined by authorize.net', 'transaction declined by bluepay',
        'transaction declined',
    )
    if any(k in rl for k in _declined):
        return 'Declined'

    # PayU raw category values
    if 'category' in rl and 'success' in rl:
        return 'Charged'
    if rl.startswith('payment declined') or rl.startswith('payment error'):
        return 'Declined'

    # Default: if it looks like a real gateway message, treat as decline
    return 'Declined'


def status_header(status: str, premium_emoji_tag) -> str:
    """Return formatted status header line for bot UI."""
    if status == 'Charged':
        return f"{premium_emoji_tag('🔥')} **Card Charged**"
    if status == 'Approved':
        return f"{premium_emoji_tag('✨')} **Card Approved**"
    if status == 'Error':
        return f"{premium_emoji_tag('⚠️')} **Gate Error**"
    return f"{premium_emoji_tag('❌')} **Card Declined**"


def sanitize_response(response) -> str:
    """Clean response text for Telegram display."""
    text = None
    if isinstance(response, dict):
        text = str(response.get('Response') or response.get('message') or response.get('msg') or response)
    elif isinstance(response, str):
        try:
            import json
            data = json.loads(response)
            if isinstance(data, dict):
                text = str(data.get('Response') or data.get('message') or data.get('msg') or response)
        except Exception:
            pass

    if text is None:
        text = str(response)
    
    rl = text.lower().strip()
    
    # 1. Clean up redirect URLs, HTML responses or raw decline parameters
    if 'card_declined' in rl or 'card-declined' in rl or 'card%20declined' in rl:
        return 'CARD_DECLINED'
    if 'generic_error' in rl or 'generic_decline' in rl or 'generic-decline' in rl:
        return 'CARD_DECLINED'
    if 'do_not_honor' in rl or 'do-not-honor' in rl or 'do not honor' in rl:
        return 'CARD_DECLINED'
    if 'refused' in rl:
        return 'CARD_DECLINED'
    if 'stolen_card' in rl or 'stolen card' in rl:
        return 'Stolen Card'
    if 'lost_card' in rl or 'lost card' in rl:
        return 'Lost Card'
    if 'pickup_card' in rl or 'pickup card' in rl:
        return 'Pickup Card'
    if 'expired_card' in rl or 'expired card' in rl or 'card expired' in rl or 'has expired' in rl:
        return 'Expired Card'
    if 'invalid_number' in rl or 'invalid number' in rl or 'incorrect_number' in rl or 'incorrect number' in rl:
        return 'Invalid Card Number'
    if 'card_not_supported' in rl or 'not supported' in rl or 'not_supported' in rl:
        return 'Card Not Supported'
    if 'restricted_card' in rl or 'restricted card' in rl:
        return 'Restricted Card'
    if 'transaction_not_allowed' in rl or 'transaction not allowed' in rl:
        return 'Transaction Not Allowed'
    if 'card_velocity_exceeded' in rl or 'velocity exceeded' in rl:
        return 'Card Velocity Exceeded'
    if 'processing_error' in rl or 'processing error' in rl:
        return 'Processing Error'
    if 'invalid account' in rl or 'invalid_account' in rl or 'account closed' in rl:
        return 'Invalid Account'
    if 'declined' in rl and 'not declined' not in rl:
        return 'CARD_DECLINED'
    
    # 2. Strip prefixes like "Card declined: " or "Redirect to error: "
    if text.lower().startswith('card declined:'):
        return text[14:].strip().capitalize()
    if text.lower().startswith('card declined'):
        return text[13:].strip().strip(':').strip().capitalize()
    if 'redirect to error:' in rl:
        return 'Card Declined'
    if 'unexpected html response' in rl or 'unexpected html' in rl:
        return 'Card Declined'
        
    safe = text[:200].replace('\n', ' ').replace('\r', '').strip()
    return safe.replace('{{', '{ {').replace('}}', '} }')
