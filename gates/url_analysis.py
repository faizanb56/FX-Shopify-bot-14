import asyncio
import requests
import re
import urllib.parse
import urllib3

# Suppress insecure SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GATEWAY_PATTERNS = {
    'Stripe': [
        r'js\.stripe\.com', r'checkout\.stripe\.com', r'stripe-elements', r'stripe-js',
        r'__stripe_mid', r'__stripe_sid', r'stripe\.com/js', r'stripe-payment-form',
        r'stripe-key', r'api\.stripe\.com', r'stripe\.js'
    ],
    'Braintree': [
        r'js\.braintreegateway\.com', r'braintree-api', r'braintree-web', r'data-braintree-name',
        r'braintree-dropin', r'braintree-container', r'braintree-hosted-field', r'braintree_merchant_id'
    ],
    'PayPal': [
        r'paypal\.com/sdk/js', r'smart/buttons\.js', r'checkout\.js', r'paypal-objects',
        r'www\.paypalobjects\.com', r'paypal-button', r'paypal-checkout', r'paypal-express',
        r'paypal\.com/cgi-bin', r'paypal_merchant_id', r'paypal-sdk'
    ],
    'Authorize.Net': [
        r'js\.authorize\.net', r'accept\.js', r'accept-sdk', r'authorizenet', r'authnet', r'AcceptSDK'
    ],
    'Adyen': [
        r'adyen\.com', r'adyen-checkout', r'adyen\.js', r'checkout\.adyen\.com', r'adyen-checkout__'
    ],
    'Square': [
        r'js\.squareup\.com', r'squareup\.com/v2/analytics', r'connect\.squareup\.com',
        r'sq-card-number', r'sq-input', r'sq-payment-form'
    ],
    'Mollie': [
        r'js\.mollie\.com', r'mollie\.com', r'api\.mollie\.com', r'mollie-payment'
    ],
    '2Checkout': [
        r'2checkout\.com', r'2co\.com', r'convertplus', r'tco-'
    ],
    'CyberSource': [
        r'cybersource\.com', r'flex\.cybersource\.com', r'microform'
    ],
    'Razorpay': [
        r'checkout\.razorpay\.com', r'razorpay\.com', r'rzp\.js', r'rzp-'
    ],
    'PayU': [
        r'payu\.in', r'payu\.com', r'secure\.payu'
    ],
    'SagePay': [
        r'sagepay', r'opayo'
    ],
    'Worldpay': [
        r'worldpay\.com', r'secure\.worldpay'
    ],
    'eWAY': [
        r'eway\.com', r'eway-payment', r'eway\.com\.au'
    ],
    'Recurly': [
        r'js\.recurly\.com', r'recurly\.com'
    ],
    'Shopify Payments': [
        r'shopify-payment-button', r'shop-pay-button', r'shopify_pay', r'shop_pay'
    ],
    'WooCommerce Payments': [
        r'wc-payments', r'woocommerce-payments'
    ],
    'NMI': [
        r'nmi\.com', r'network merchants', r'nmi-'
    ],
    'Spreedly': [
        r'spreedly'
    ],
    'Clover': [
        r'clover\.com'
    ],
    'Bolt': [
        r'bolt-checkout', r'bolt\.com'
    ],
    'Affirm': [
        r'affirm\.com'
    ],
    'Klarna': [
        r'klarna\.com', r'klarnacdn'
    ],
    'Afterpay': [
        r'afterpay', r'clearpay'
    ],
    'Checkout.com': [
        r'cdn\.checkout\.com', r'checkout\.js', r'checkout\.com'
    ],
    'Bluepay': [
        r'bluepay', r'bluepay\.com'
    ],
    'Skrill': [
        r'skrill\.com', r'skrill'
    ],
    'Apple Pay': [
        r'apple-pay', r'apple_pay', r'applepay'
    ],
    'Google Pay': [
        r'google-pay', r'google_pay', r'googlepay'
    ],
    'Amazon Pay': [
        r'amazon-pay', r'amazonpay'
    ]
}

PLATFORM_PATTERNS = {
    'Shopify': [r'shopify', r'myshopify', r'cdn\.shopify\.com'],
    'WooCommerce': [r'woocommerce', r'wc-cart', r'wc-ajax', r'wp-content/plugins/woocommerce'],
    'Magento': [r'magento', r'mageplaza', r'/static/frontend/'],
    'PrestaShop': [r'prestashop', r'addons\.prestashop'],
    'OpenCart': [r'opencart', r'route=common/home'],
    'BigCommerce': [r'bigcommerce', r'stencil'],
    'WordPress': [r'wordpress', r'wp-content', r'wp-includes'],
    'Drupal': [r'drupal', r'sites/all'],
    'Joomla': [r'joomla', r'index\.php\?option=com_'],
    'Wix': [r'wix\.com', r'wixsite', r'_wix_'],
    'Squarespace': [r'squarespace\.com', r'squarespace-'],
    'Webflow': [r'webflow\.com', r'data-wf-page']
}

CLOUDFLARE_PATTERNS = [
    r'checking your browser', r'cf-ray', r'cloudflare', r'__cfduid',
    r'__cflb', r'__cf_bm', r'cf_clearance', r'cf-browser-verification',
    r'attention required! \| cloudflare', r'challenges\.cloudflare\.com'
]

CAPTCHA_PATTERNS = [
    r'recaptcha', r'g-recaptcha', r'recaptcha/api\.js', r'google\.com/recaptcha',
    r'data-sitekey', r'hcaptcha', r'hcaptcha\.com', r'h-captcha', r'class="h-captcha"',
    r'challenges\.cloudflare\.com/turnstile', r'cf-turnstile', r'turnstile',
    r'funcaptcha', r'arkoselabs', r'arkose', r'geetest', r'gt_holder', r'geetest\.com',
    r'friendly-captcha', r'frc-captcha'
]

GRAPHQL_PATTERNS = [
    r'graphql', r'application/graphql', r'/graphql'
]


def _check_gateway(content_type, headers_str, html, cookies_str, url):
    found = set()
    # Check Gateways
    for gw, patterns in GATEWAY_PATTERNS.items():
        for pat in patterns:
            if (re.search(pat, content_type, re.IGNORECASE) or
                re.search(pat, headers_str, re.IGNORECASE) or
                re.search(pat, html, re.IGNORECASE) or
                re.search(pat, cookies_str, re.IGNORECASE) or
                re.search(pat, url, re.IGNORECASE)):
                found.add(gw)
                break
    return list(found)


def _analyze_site_sync(url):
    """Synchronous URL analysis"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        
        session = requests.Session()
        session.headers.update(headers)
        
        # 1. Fetch homepage
        resp = session.get(url, timeout=15, allow_redirects=True, verify=False)
        http_status = resp.status_code
        html = resp.text
        resp_headers = dict(resp.headers)
        content_type = resp_headers.get('content-type', '').lower()
        headers_str = str(resp_headers)
        cookies_str = str(dict(resp.cookies))
        final_url = resp.url
        
        # Detect initial results
        gateways = _check_gateway(content_type, headers_str, html, cookies_str, final_url)
        
        cloudflare = any(re.search(pat, html, re.IGNORECASE) or 
                        re.search(pat, headers_str, re.IGNORECASE) or 
                        re.search(pat, cookies_str, re.IGNORECASE) for pat in CLOUDFLARE_PATTERNS)
                        
        captcha = any(re.search(pat, html, re.IGNORECASE) for pat in CAPTCHA_PATTERNS)
        
        graphql = any(re.search(pat, html, re.IGNORECASE) or 
                      re.search(pat, final_url, re.IGNORECASE) for pat in GRAPHQL_PATTERNS)
                      
        platform = None
        for pname, patterns in PLATFORM_PATTERNS.items():
            if any(re.search(pat, html, re.IGNORECASE) or re.search(pat, final_url, re.IGNORECASE) for pat in patterns):
                platform = pname
                break
                
        # 2. Try fetching checkout/cart to detect payment gateways initialized on checkout page
        parsed = urllib.parse.urlparse(final_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        checkout_paths = []
        if platform == 'Shopify':
            checkout_paths = ["/checkout", "/cart"]
        elif platform == 'WooCommerce':
            checkout_paths = ["/checkout/", "/cart/"]
        else:
            checkout_paths = ["/checkout", "/cart", "/checkout/"]
            
        gateways_set = set(gateways)
        
        # Only do additional checkout checks if we haven't found many gateways or if platform is identified
        for path in checkout_paths:
            try:
                c_url = base_url + path
                c_resp = session.get(c_url, timeout=10, allow_redirects=True, verify=False)
                c_html = c_resp.text
                c_headers = dict(c_resp.headers)
                c_headers_str = str(c_headers)
                c_cookies_str = str(dict(c_resp.cookies))
                c_final_url = c_resp.url
                
                # Check for gateways on checkout page
                c_gateways = _check_gateway(c_headers.get('content-type', '').lower(), c_headers_str, c_html, c_cookies_str, c_final_url)
                gateways_set.update(c_gateways)
                
                # Update cloudflare, captcha, graphql, and platform if found on checkout
                cloudflare = cloudflare or any(re.search(pat, c_html, re.IGNORECASE) or re.search(pat, c_headers_str, re.IGNORECASE) or re.search(pat, c_cookies_str, re.IGNORECASE) for pat in CLOUDFLARE_PATTERNS)
                captcha = captcha or any(re.search(pat, c_html, re.IGNORECASE) for pat in CAPTCHA_PATTERNS)
                graphql = graphql or any(re.search(pat, c_html, re.IGNORECASE) or re.search(pat, c_final_url, re.IGNORECASE) for pat in GRAPHQL_PATTERNS)
                
                if not platform:
                    for pname, patterns in PLATFORM_PATTERNS.items():
                        if any(re.search(pat, c_html, re.IGNORECASE) or re.search(pat, c_final_url, re.IGNORECASE) for pat in patterns):
                            platform = pname
                            break
            except:
                pass
                
        return {
            'status': http_status,
            'gateways': sorted(list(gateways_set)),
            'cloudflare': cloudflare,
            'captcha': captcha,
            'graphql': graphql,
            'platform': platform,
            'error': None,
        }
    except Exception as e:
        return {
            'status': None,
            'gateways': [],
            'cloudflare': False,
            'captcha': False,
            'graphql': False,
            'platform': None,
            'error': str(e),
        }


async def analyze_url(url: str) -> dict:
    """Async wrapper for URL site analysis"""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _analyze_site_sync, url)
