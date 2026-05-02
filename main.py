"""
ALM Machine Payments Protocol (MPP) Endpoint
Stripe Sessions 2026 - Agentic Commerce Infrastructure

Endpoints:
  GET  /.well-known/mpp.json  - Service discovery catalog
  POST /mpp/payment           - Initiate agent payment (creates Checkout Session)
  POST /mpp/webhook           - Stripe webhook handler for payment confirmation
"""

import os
import json
import stripe
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI(
    title="ALM MPP Endpoint",
    description="Alma Digital AI - Machine Payments Protocol Endpoint",
    version="2.0.0"
)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# Service type constants (must match metadata values)
SERVICE_WEBSITE_BUILD_STARTER = "website_build_starter"
SERVICE_WEBSITE_BUILD_GROWTH = "website_build_growth"
SERVICE_WEBSITE_BUILD_PREMIUM = "website_build_premium"
SERVICE_FULL_PRESENCE_BUNDLE = "full_presence_bundle"
SERVICE_ULTIMATE_BUSINESS_LAUNCH = "ultimate_business_launch"
SERVICE_PINNACLE_PACKAGE = "pinnacle_package"

# CEO-approved price IDs (ALM-3949 / ALM-4190)
STRIPE_PRICE_IDS = {
    SERVICE_WEBSITE_BUILD_STARTER: {
        "setup": os.getenv("STRIPE_PRICE_WEBSITE_BUILD_STARTER", "price_1TSSGCAytyJRLR9LCDJtEH9b"),
        "monthly": None,
    },
    SERVICE_WEBSITE_BUILD_STARTER: {
        "name": "Website Build Starter",
        "description": "Professional AI-assisted starter website. Up to 5 pages. Delivered same day.",
        "type": "one_time",
        "setup_usd": 50,
        "monthly_usd": None,
        "currency": "usd",
    },
    SERVICE_WEBSITE_BUILD_GROWTH: {
        "setup": os.getenv("STRIPE_PRICE_WEBSITE_BUILD_GROWTH", "price_1TSPWnAytyJRLR9L2YJvlonU"),
        "monthly": None,
    },
    SERVICE_WEBSITE_BUILD_PREMIUM: {
        "setup": os.getenv("STRIPE_PRICE_WEBSITE_BUILD_PREMIUM", "price_1TSPWoAytyJRLR9LcLtcvgXW"),
        "monthly": None,
    },
    SERVICE_FULL_PRESENCE_BUNDLE: {
        "setup": os.getenv("STRIPE_PRICE_FULL_PRESENCE_BUNDLE", "price_1TSPWoAytyJRLR9Lgw1mmhIU"),
        "monthly": None,
    },
    SERVICE_ULTIMATE_BUSINESS_LAUNCH: {
        "setup": os.getenv("STRIPE_PRICE_ULTIMATE_SETUP", "price_1TSPWpAytyJRLR9LLZtNFv8X"),
        "monthly": os.getenv("STRIPE_PRICE_ULTIMATE_MONTHLY", "price_1TSPWpAytyJRLR9LQDxCBUdH"),
    },
    SERVICE_PINNACLE_PACKAGE: {
        "setup": os.getenv("STRIPE_PRICE_PINNACLE_SETUP", "price_1TSPWpAytyJRLR9LCVog40zk"),
        "monthly": os.getenv("STRIPE_PRICE_PINNACLE_MONTHLY", "price_1TSPWqAytyJRLR9Lc1LK5noJ"),
    },
}

SERVICE_CATALOG = {
    SERVICE_WEBSITE_BUILD_STARTER: {
        "setup": os.getenv("STRIPE_PRICE_WEBSITE_BUILD_STARTER", "price_1TSSGCAytyJRLR9LCDJtEH9b"),
        "monthly": None,
    },
    SERVICE_WEBSITE_BUILD_STARTER: {
        "name": "Website Build Starter",
        "description": "Professional AI-assisted starter website. Up to 5 pages. Delivered same day.",
        "type": "one_time",
        "setup_usd": 50,
        "monthly_usd": None,
        "currency": "usd",
    },
    SERVICE_WEBSITE_BUILD_GROWTH: {
        "name": "Website Build Growth",
        "description": "Professional AI-assisted website design and development. Delivered in 5-7 business days.",
        "type": "one_time",
        "setup_usd": 100,
        "monthly_usd": None,
        "currency": "usd",
    },
    SERVICE_WEBSITE_BUILD_PREMIUM: {
        "name": "Website Build Premium",
        "description": "Premium AI-assisted website design and development with enhanced features.",
        "type": "one_time",
        "setup_usd": 150,
        "monthly_usd": None,
        "currency": "usd",
    },
    SERVICE_FULL_PRESENCE_BUNDLE: {
        "name": "The Full Presence Bundle",
        "description": "Website build + Google Business Profile setup. Complete local business presence.",
        "type": "one_time",
        "setup_usd": 195,
        "monthly_usd": None,
        "currency": "usd",
    },
    SERVICE_ULTIMATE_BUSINESS_LAUNCH: {
        "name": "Ultimate Business Launch",
        "description": "Complete digital presence: website + GBP + ongoing social media management.",
        "type": "subscription_with_setup",
        "setup_usd": 299,
        "monthly_usd": 92,
        "currency": "usd",
    },
    SERVICE_PINNACLE_PACKAGE: {
        "name": "Pinnacle Package",
        "description": "Premium full-service digital presence with dedicated management and premium support.",
        "type": "subscription_with_setup",
        "setup_usd": 328,
        "monthly_usd": 151,
        "currency": "usd",
    },
}


@app.get("/.well-known/mpp.json")
async def service_discovery():
    """
    MPP Service Discovery Endpoint.
    AI agents query this to discover available ALM services and payment terms.
    """
    catalog = {}
    for service_type, info in SERVICE_CATALOG.items():
        price_ids = STRIPE_PRICE_IDS.get(service_type, {})
        catalog[service_type] = {
            **info,
            "stripe_price_id_setup": price_ids.get("setup"),
            "stripe_price_id_monthly": price_ids.get("monthly"),
        }

    return {
        "mpp_version": "2.0",
        "provider": "Alma Digital AI LLC",
        "provider_url": "https://almadigitalservices.com",
        "payment_endpoint": "/mpp/payment",
        "webhook_endpoint": "/mpp/webhook",
        "supported_metadata": {
            "initiation_type": "agent_mpp",
            "service_type": list(SERVICE_CATALOG.keys()),
            "client_agent_id": "agent identifier string",
        },
        "services": catalog,
    }


class PaymentRequest(BaseModel):
    service_type: str          # see SERVICE_CATALOG keys
    client_agent_id: str       # identifier of the calling agent
    success_url: str           # redirect URL on successful payment
    cancel_url: Optional[str] = "https://almadigitalservices.com"
    client_name: Optional[str] = None
    client_email: Optional[str] = None


@app.post("/mpp/payment")
async def initiate_payment(req: PaymentRequest):
    """
    MPP Payment Initiation Endpoint.
    Creates a Stripe Checkout Session for agent-initiated payments.
    Returns a payment URL the agent can deliver to the end customer.
    """
    if req.service_type not in SERVICE_CATALOG:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown service type: {req.service_type}. Valid: {list(SERVICE_CATALOG.keys())}"
        )

    service = SERVICE_CATALOG[req.service_type]
    price_ids = STRIPE_PRICE_IDS.get(req.service_type, {})
    setup_price_id = price_ids.get("setup")
    monthly_price_id = price_ids.get("monthly")

    if not setup_price_id:
        raise HTTPException(
            status_code=503,
            detail=f"Price not configured for {req.service_type}."
        )

    # Shared MPP metadata (required for Cody's financial tracking - ALM-3937/ALM-3946)
    mpp_metadata = {
        "initiation_type": "agent_mpp",
        "service_type": req.service_type,
        "client_agent_id": req.client_agent_id,
    }

    is_subscription = service["type"] == "subscription_with_setup"

    # Create Customer with metadata first (Stripe does NOT auto-propagate session metadata)
    customer_params = {"metadata": mpp_metadata}
    if req.client_name:
        customer_params["name"] = req.client_name
    if req.client_email:
        customer_params["email"] = req.client_email
    try:
        customer = stripe.Customer.create(**customer_params)
    except stripe.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe error creating customer: {str(e)}")

    # Build line items
    # For subscription_with_setup: include both setup (one-time) and monthly (recurring)
    # Stripe Checkout subscription mode supports mixing one-time and recurring line items.
    # The one-time price is charged on the first invoice; recurring continues monthly.
    line_items = [{"price": setup_price_id, "quantity": 1}]
    if is_subscription and monthly_price_id:
        line_items.append({"price": monthly_price_id, "quantity": 1})

    # Build checkout session params
    session_params = {
        "mode": "subscription" if is_subscription else "payment",
        "line_items": line_items,
        "metadata": mpp_metadata,
        "customer": customer.id,
        "success_url": req.success_url,
        "cancel_url": req.cancel_url,
    }

    # Propagate metadata to underlying payment objects (Stripe does NOT auto-inherit from session)
    if is_subscription:
        session_params["subscription_data"] = {"metadata": mpp_metadata}
    else:
        session_params["payment_intent_data"] = {"metadata": mpp_metadata}

    try:
        session = stripe.checkout.Session.create(**session_params)
    except stripe.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")

    return {
        "session_id": session.id,
        "payment_url": session.url,
        "service": service["name"],
        "service_type": req.service_type,
        "setup_usd": service["setup_usd"],
        "monthly_usd": service.get("monthly_usd"),
        "payment_type": service["type"],
        "customer_id": customer.id,
        "metadata": mpp_metadata,
        "status": "pending",
    }


@app.post("/mpp/webhook")
async def handle_webhook(request: Request, stripe_signature: str = Header(None, alias="stripe-signature")):
    """
    MPP Webhook Handler.
    Stripe sends payment confirmation events here.
    Filters for agent_mpp events to log agentic revenue (ALM-3937).
    """
    body = await request.body()

    try:
        event = stripe.Webhook.construct_event(body, stripe_signature, WEBHOOK_SECRET)
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {str(e)}")

    event_type = event["type"]
    obj = event["data"]["object"]
    metadata = obj.get("metadata", {})

    # Only process MPP-initiated events
    if metadata.get("initiation_type") != "agent_mpp":
        return {"status": "ok", "processed": False, "reason": "non-mpp event"}

    service_type = metadata.get("service_type", "unknown")
    client_agent_id = metadata.get("client_agent_id", "unknown")

    if event_type == "payment_intent.succeeded":
        amount = obj.get("amount", 0) / 100
        print(f"[MPP] PaymentIntent succeeded: ${amount:.2f} | service={service_type} | agent={client_agent_id} | id={obj['id']}")

    elif event_type == "checkout.session.completed":
        print(f"[MPP] Checkout completed: service={service_type} | agent={client_agent_id} | session={obj['id']}")

    elif event_type == "customer.subscription.created":
        amount = obj.get("items", {}).get("data", [{}])[0].get("price", {}).get("unit_amount", 0) / 100
        print(f"[MPP] Subscription created: ${amount:.2f}/mo | service={service_type} | agent={client_agent_id} | id={obj['id']}")

    elif event_type == "customer.subscription.deleted":
        print(f"[MPP] Subscription cancelled: service={service_type} | agent={client_agent_id} | id={obj['id']}")

    return {
        "status": "ok",
        "processed": True,
        "event_type": event_type,
        "service_type": service_type,
        "client_agent_id": client_agent_id,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "alm-mpp", "version": "2.0.0", "stripe_configured": bool(stripe.api_key)}
