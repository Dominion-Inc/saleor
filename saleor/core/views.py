import os

from django.template.response import TemplateResponse
from urllib.parse import unquote
import requests
from .forms import ResetPassword
import logging

logger = logging.getLogger(__name__)

def home(request):
    storefront_url = os.environ.get("STOREFRONT_URL", "")
    dashboard_url = os.environ.get("DASHBOARD_URL", "")
    return TemplateResponse(
        request,
        "home/index.html",
        {"storefront_url": storefront_url, "dashboard_url": dashboard_url},
    )

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
            URL = GRAPHQL_URL
            response = requests.post(url=URL, json=json)
            # The response from server can be empty (in case of timeout)
            try:
                logger.debug("response.json(): %s",response.json())
                # check if there were any errors
                if response.json()["data"]["setPassword"]["accountErrors"]==[]:
                    return TemplateResponse(request, 'forgot_password/password_reset_success.html')
                # render reset fail page if there are errors and display error
                else:
                    error = response.json()["data"]["setPassword"]["accountErrors"][0]["message"]
                    return TemplateResponse(request, 'forgot_password/password_reset_fail.html', {'message': error})
            # if the response from the server is empty then display error message
            except:
                logger.debug("json: : %s",json)
            return TemplateResponse(request, 'forgot_password/password_reset_fail.html', {'message': 'Empty response from server.'})
    else:
        email = unquote(request.GET.get('email'))
        token = request.GET.get('token')
        form = ResetPassword(initial={"email":email,"token":token})

    return TemplateResponse(request, 'forgot_password/reset_password.html', {'form':form})