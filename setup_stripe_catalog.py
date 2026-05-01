"""
ALM Stripe Catalog Setup Script
Creates MPP Products and Prices in Stripe (SANDBOX/TEST MODE ONLY)

Usage:
  STRIPE_SECRET_KEY=sk_test_... python3 setup_stripe_catalog.py

Output: env vars to add to Railway + Paperclip config
"""

import os
import json
import stripe

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

# Verify we're in test mode
if not stripe.api_key.startswith("sk_test_"):
    print("ERROR: This script must be run with a TEST key (sk_test_...). Aborting.")
    exit(1)

print(f"Running in TEST mode. Account key prefix: {stripe.api_key[:12]}...")
print()


def create_product_and_price(name, description, service_type, amount_cents, recurring=None):
    """Create a Stripe Product and Price with required MPP metadata."""
    print(f"Creating product: {name}...")

    product = stripe.Product.create(
        name=name,
        description=description,
        metadata={
            "service_type": service_type,
            "initiation_type": "agent_mpp",
            "provider": "alma_digital_ai",
        }
    )
    print(f"  Product created: {product.id}")

    price_params = {
        "product": product.id,
        "unit_amount": amount_cents,
        "currency": "usd",
        "metadata": {
            "service_type": service_type,
            "initiation_type": "agent_mpp",
        }
    }
    if recurring:
        price_params["recurring"] = recurring

    price = stripe.Price.create(**price_params)
    print(f"  Price created:   {price.id} (${amount_cents/100:.2f}{'/' + recurring['interval'] if recurring else ''})")
    print()
    return product.id, price.id


def main():
    results = {}

    # 1. Website Build — One-time $500
    prod_id, price_id = create_product_and_price(
        name="ALM Website Build",
        description="Professional AI-assisted website design and development",
        service_type="website_build",
        amount_cents=50000,
        recurring=None,
    )
    results["website_build"] = {"product_id": prod_id, "price_id": price_id}

    # 2. Social Media Management — $300/month recurring
    prod_id, price_id = create_product_and_price(
        name="ALM Social Media Management",
        description="Monthly social media content and management",
        service_type="social_media_management",
        amount_cents=30000,
        recurring={"interval": "month"},
    )
    results["social_media_management"] = {"product_id": prod_id, "price_id": price_id}

    # 3. Full Package — $700/month recurring
    prod_id, price_id = create_product_and_price(
        name="ALM Full Package",
        description="Website build + Social Media Management bundle",
        service_type="full_package",
        amount_cents=70000,
        recurring={"interval": "month"},
    )
    results["full_package"] = {"product_id": prod_id, "price_id": price_id}

    print("=" * 60)
    print("CATALOG SETUP COMPLETE")
    print("=" * 60)
    print()
    print("Add these env vars to Railway AND Paperclip config:")
    print()
    print(f'STRIPE_PRICE_WEBSITE_BUILD={results["website_build"]["price_id"]}')
    print(f'STRIPE_PRICE_SOCIAL_MEDIA={results["social_media_management"]["price_id"]}')
    print(f'STRIPE_PRICE_FULL_PACKAGE={results["full_package"]["price_id"]}')
    print()
    print("Full results JSON:")
    print(json.dumps(results, indent=2))

    # Also write to file for reference
    with open("catalog_ids.json", "w") as f:
        json.dump(results, f, indent=2)
    print()
    print("Results saved to catalog_ids.json")


if __name__ == "__main__":
    main()
