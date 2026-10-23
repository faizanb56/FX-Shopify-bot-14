"""
Backward compatibility shim for shopify_auto.
Main implementation is in gates.checkout_engine.
"""
from .checkout_engine import shopify_auto_check, fetch_products

__all__ = ["shopify_auto_check", "fetch_products"]
