import os
import json
from django.template.response import TemplateResponse
from django.http import JsonResponse
import stripe
from typing import Set
from urllib.parse import unquote
import requests
from .forms import ResetPassword
import logging
from ..graphql.account.mutations.base import SetPassword
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)
URL = os.environ.get("GRAPHQL_URL", "http://0.0.0.0:8000/graphql/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

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

        order_id = data["order_id"]
        return generate_response(intent,order_id)

def generate_response(intent, order_id):
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

        # Mark the order as paid
        token = login()
        order_mark_paid(order_id, token)
        return JsonResponse({'success': True}, status=200)
    else:
        # Invalid status
        return JsonResponse({'error': 'Invalid PaymentIntent status'}, status=500)

def login():
    query = """
        mutation login($email:String!,$password:String!){
            tokenCreate(email:$email, password:$password){
                token
                user{
                id
                }
            }
        }
    """

    variables = {
    "email": ADMIN_EMAIL,
    "password": ADMIN_PASSWORD
    }

    response = graphql_query(url=URL, query=query, variables=variables)
    
    try:
        token = response["data"]["tokenCreate"]["token"]
    except:
        logger.exception("login failed, response: %s", response)
        logger.debug("EMAIL= %s", ADMIN_EMAIL)
        logger.debug("PASSWORD= %s", ADMIN_PASSWORD)
    customerId = response["data"]["tokenCreate"]["user"]["id"]
    
    return token

def order_mark_paid(order_id, token):
    query = """
    mutation markPaid($id:ID!){
        orderMarkAsPaid(id:$id){
            order{
                isPaid
            }
        }
    }
    """
    variables = {
        "id": order_id
    }

    response = graphql_query(url=URL, query=query, variables=variables, token=token)
    try:    
        is_paid = response["data"]["orderMarkAsPaid"]["order"]["isPaid"]
    except Exception as e:
        print("could not mark as paid")
        print("response: {}, exception: {}".format(response,e))

    return is_paid

def graphql_query(url,query,variables,token=None):
    json = {
        "query": query,
        "variables": variables
    }
    headers=None
    try:
        if token:
            headers = {
                "Authorization" : "JWT {}".format(token)
            }
        response = requests.post(url=URL, json=json, headers=headers)
        json_response = response.json()
        if "error" in response:  # type: ignore
            print("Graphql response contains errors %s", json_response)
            return json_response
    except requests.exceptions.RequestException as e:
        print("Fetching query result failed, url: {}".format(url))
        print("json: {}, headers: {}, exception: {}".format(json, headers, e))
        return {}
    except json.JSONDecodeError:
        content = response.content if response else "Unable to find the response"
        print(
            "Unable to decode the response from graphql. Response: %s", content
        )
        return {}
    return json_response  # type: ignore

def _get_client():
    stripe.api_key = os.environ.get("STRIPE_PRIVATE_KEY")
    return stripe

def confirm_mail(request):
    GRAPHQL_URL = os.environ.get("GRAPHQL_URL", "http://0.0.0.0:8000/graphql/")
    email = unquote(request.GET.get('email'))
    token = request.GET.get('token')

    logger.debug("email: %s", email)
    query = """
    mutation confirmAccount($email:String!,$token:String!){
        confirmAccount(email:$email,token:$token){
            user{
            isActive
            }
            accountErrors{
            message
            }
        }
        }
    """
    URL = GRAPHQL_URL
    json = {
        "query": query,
        "variables": {
            "email": email,
            "token": token
        }
    }
    
    response = requests.post(url=URL, json=json)

    logger.debug("response json: %s", response.json())
    if response.json()["data"]["confirmAccount"]["user"] is None:
        error = response.json()["data"]["confirmAccount"]["accountErrors"][0]["message"]
        message = error
        return TemplateResponse(
            request,
            "confirm_mail/fail.html",
            {"message":message},
        )
    else :
        logger.debug("response isActive= %s", response.json()["data"]["confirmAccount"]["user"]["isActive"])
        message = "Email verified."
        return TemplateResponse(
            request,
            "confirm_mail/success.html",
            {"message":message},
        )

def forgot_password(request):
    if request.method == 'POST':
        form = ResetPassword(request.POST)
        new_password = form.data['new_password']
        confirm_new_password = form.data['confirm_new_password']
        email = form.data['email']
        token = form.data['token']
        
        GRAPHQL_URL = os.environ.get("GRAPHQL_URL", "http://0.0.0.0:8000/graphql/")

        logger.debug("new_password: %s", new_password)
        logger.debug("confirm_new_password: %s", confirm_new_password)

        if form.is_valid():
            logger.debug('email: %s', email)
            logger.debug('password: %s', token)

            query = """
            mutation setPassword($email:String!,$password:String!,$token:String!){
                setPassword(email:$email, password:$password, token:$token){
                    user{
                    email
                    isActive
                    }
                    accountErrors{
                        field
                        message
                    }
                }
            }
            """

            json = {
                "query" : query,
                "variables" : {
                    "email" : email,
                    "password" : new_password,
                    "token" : token
                }
            }
            variables = {
                    "email" : email,
                    "password" : new_password,
                    "token" : token
            }
            

            try:
                SetPassword._set_password_for_user(email,new_password,token)
                return TemplateResponse(request, 'forgot_password/password_reset_success.html')
            except ValidationError as error:
                error_name = list(error.message_dict.keys())[0]
                return TemplateResponse(request, 'forgot_password/password_reset_fail.html', {'message': error.message_dict[error_name][0]})

    else:
        email = unquote(request.GET.get('email'))
        token = request.GET.get('token')
        form = ResetPassword(initial={"email":email,"token":token})

    return TemplateResponse(request, 'forgot_password/reset_password.html', {'form':form})

