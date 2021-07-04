import os
import json
from django.template.response import TemplateResponse
import stripe


def home(request):
    storefront_url = os.environ.get("STOREFRONT_URL", "")
    dashboard_url = os.environ.get("DASHBOARD_URL", "")
    return TemplateResponse(
        request,
        "home/index.html",
        {"storefront_url": storefront_url, "dashboard_url": dashboard_url},
    )

def pay(request):
    if request.method == 'POST':
        data = request.get_json()
        intent = None

        try:
            if 'payment_method_id' in data:
                # Create the PaymentIntent
                intent = stripe.PaymentIntent.create(
                    payment_method = data['payment_method_id'],
                    amount = 1099,
                    currency = 'usd',
                    confirmation_method = 'manual',
                    confirm = True,
                )
            elif 'payment_intent_id' in data:
                intent = stripe.PaymentIntent.confirm(data['payment_intent_id'])
        except stripe.error.CardError as e:
            # Display error on client
            return json.dumps({'error': e.user_message}), 200

        return generate_response(intent)

def generate_response(intent):
    # Note that if your API version is before 2019-02-11, 'requires_action'
    # appears as 'requires_source_action'.
    if intent.status == 'requires_action' and intent.next_action.type == 'use_stripe_sdk':
        # Tell the client to handle the action
        return json.dumps({
        'requires_action': True,
        'payment_intent_client_secret': intent.client_secret,
        }), 200
    elif intent.status == 'succeeded':
        # The payment didn’t need any additional actions and completed!
        # Handle post-payment fulfillment
        return json.dumps({'success': True}), 200
    else:
        # Invalid status
        return json.dumps({'error': 'Invalid PaymentIntent status'}), 500