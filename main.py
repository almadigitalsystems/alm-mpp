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
    version="1.0.0"
)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# Service type constants (must match metadata values)
SERVICE_WEBSITE_BUILD = "website_build"
SERVICE_SOCIAL_MEDIA = "social_media_management"
SERVICE_FULL_PACKAGE = "full_package"

# Populated after Stripe catalog setup (via setup_stripe_catalog.py)
STRIPE_PRICE_IDS = {
    SERVICE_WEBSITE_BUILD: os.getenv("STRIPE_PRICE_WEBSITE_BUILD"),
    SERVICE_SOCIAL_MEDIA: os.getenv("STRIPE_PRICE_SOCIAL_MEDIA"),
    SERVICE_FULL_PACKAGE: os.getenv("STRIPE_PRICE_FULL_PACKAGE"),
}

SERVICE_CATALOG = {
    SERVICE_WEBSITE_BUILD: {
        "name": "ALM Website Build",
        "description": "Professional AI-assisted website design and development. Delivered in 5-7 business days.",
        "type": "one_time",
        "price_usd": 500,
        "currency": "usd",
    },
    SERVICE_SOCIAL_MEDIA: {
        "name": "ALM Social Media Management",
        "description": "Monthly social media content creation and management across Instagram, Facebook, X, TikTok.",
        "type": "recurring_monthly",
        "price_usd": 300,
        "currency": "usd",
    },
    SERVICE_FULL_PACKAGE: {
        "name": "ALM Full Package",
        "description": "Website build + ongoing social media management. Best value bundle.",
        "type": "recurring_monthly",
        "price_usd": 700,
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
        catalog[service_type] = {
            **info,
            "stripe_price_id": STRIPE_PRICE_IDS.get(service_type),
        }

    return {
        "mpp_version": "1.0",
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
    service_type: str          # website_build | social_media_management | full_package
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
    price_id = STRIPE_PRICE_IDS.get(req.service_type)

    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=f"Price not configured for {req.service_type}. Run setup_stripe_catalog.py first."
        )

    # Shared MPP metadata (required for Cody's financial tracking - ALM-3937)
    mpp_metadata = {
        "initiation_type": "agent_mpp",
        "service_type": req.service_type,
        "client_agent_id": req.client_agent_id,
    }

    # Build checkout session params
    session_params = {
        "mode": "payment" if service["type"] == "one_time" else "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "metadata": mpp_metadata,
        "success_url": req.success_url,
        "cancel_url": req.cancel_url,
    }

    # Pre-fill customer info if provided
    if req.client_email:
        session_params["customer_email"] = req.client_email

    try:
        session = stripe.checkout.Session.create(**session_params)
    except stripe.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")

    return {
        "session_id": session.id,
        "payment_url": session.url,
        "service": service["name"],
        "service_type": req.service_type,
        "amount_usd": service["price_usd"],
        "payment_type": service["type"],
        "metadata": mpp_metadata,
        "status": "pending",
    }


@app.post("/mpp/webhook")
async def handle_webhook(request: Request, stripe_signature: str = Header(None, alias="stripe-signature")):
    """
    MPP Webhook Handler.
    Stripe sends payment confirmation events here.
    Filters for agent_mpp events to log agentic revenue separately (ALM-3937).
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
    return {"status": "ok", "service": "alm-mpp", "stripe_configured": bool(stripe.api_key)}
