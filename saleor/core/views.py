import os
import json
from django.template.response import TemplateResponse
from django.http import JsonResponse
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
        data = json.loads(request.body)
        intent = None
        stripe = _get_client()
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
            return JsonResponse({'error': e.user_message}, status=200)

        return generate_response(intent)

def generate_response(intent):
    # Note that if your API version is before 2019-02-11, 'requires_action'
    # appears as 'requires_source_action'.
    if intent.status == 'requires_action' and intent.next_action.type == 'use_stripe_sdk':
        # Tell the client to handle the action
        return JsonResponse({
        'requires_action': True,
        'payment_intent_client_secret': intent.client_secret,
        },status= 200)
    elif intent.status == 'succeeded':
        # The payment didn’t need any additional actions and completed!
        # Handle post-payment fulfillment
        return JsonResponse({'success': True}, status=200)
    else:
        # Invalid status
        return JsonResponse({'error': 'Invalid PaymentIntent status'}, status=500)

def _get_client():
    stripe.api_key = os.environ.get("STRIPE_PRIVATE_KEY")
    return stripe