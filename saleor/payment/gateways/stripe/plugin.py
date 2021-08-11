from typing import TYPE_CHECKING, List

from saleor.plugins.base_plugin import BasePlugin, ConfigurationTypeField

from ..utils import get_supported_currencies
from . import (
    GatewayConfig,
    authorize,
    capture,
    list_client_sources,
    process_payment,
    refund,
    void,
)

GATEWAY_NAME = "Stripe"

if TYPE_CHECKING:
    # flake8: noqa
    from . import GatewayResponse, PaymentData
    from ...interface import CustomerSource


def require_active_plugin(fn):
    def wrapped(self, *args, **kwargs):
        previous = kwargs.get("previous_value", None)
        if not self.active:
            return previous
        return fn(self, *args, **kwargs)

    return wrapped


class StripeGatewayPlugin(BasePlugin):
    PLUGIN_NAME = GATEWAY_NAME
    PLUGIN_ID = "mirumee.payments.stripe"
    DEFAULT_CONFIGURATION = [
        {"name": "Public API key", "value": None},
        {"name": "Secret API key", "value": None},
        {"name": "Store customers card", "value": False},
        {"name": "Automatic payment capture", "value": True},
        {"name": "Supported currencies", "value": ""},
    ]

    CONFIG_STRUCTURE = {
        "Public API key": {
            "type": ConfigurationTypeField.SECRET,
            "help_text": "Provide Stripe public API key.",
            "label": "Public API key",
        },
        "Secret API key": {
            "type": ConfigurationTypeField.SECRET,
            "help_text": "Provide Stripe secret API key.",
            "label": "Secret API key",
        },
        "Store customers card": {
            "type": ConfigurationTypeField.BOOLEAN,
            "help_text": "Determines if Saleor should store cards on payments "
            "in Stripe customer.",
            "label": "Store customers card",
        },
        "Automatic payment capture": {
            "type": ConfigurationTypeField.BOOLEAN,
            "help_text": "Determines if Saleor should automaticaly capture payments.",
            "label": "Automatic payment capture",
        },
        "Supported currencies": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Determines currencies supported by gateway."
            " Please enter currency codes separated by a comma.",
            "label": "Supported currencies",
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
        self.config = GatewayConfig(
            gateway_name=GATEWAY_NAME,
            auto_capture=configuration["Automatic payment capture"],
            supported_currencies=configuration["Supported currencies"],
            connection_params={
                "public_key": configuration["Public API key"],
                "private_key": configuration["Secret API key"],
            },
            store_customer=configuration["Store customers card"],
        )

    def _get_gateway_config(self):
        return self.config

    @require_active_plugin
    def authorize_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        return authorize(payment_information, self._get_gateway_config())

    @require_active_plugin
    def capture_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        return capture(payment_information, self._get_gateway_config())

    @require_active_plugin
    def refund_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        return refund(payment_information, self._get_gateway_config())

    @require_active_plugin
    def void_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        return void(payment_information, self._get_gateway_config())

    @require_active_plugin
    def process_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        return process_payment(payment_information, self._get_gateway_config())

    @require_active_plugin
    def list_payment_sources(
        self, customer_id: str, previous_value
    ) -> List["CustomerSource"]:
        sources = list_client_sources(self._get_gateway_config(), customer_id)
        previous_value.extend(sources)
        return previous_value

    @require_active_plugin
    def get_supported_currencies(self, previous_value):
        config = self._get_gateway_config()
        return get_supported_currencies(config, GATEWAY_NAME)

    @require_active_plugin
    def get_payment_config(self, previous_value):
        config = self._get_gateway_config()
        return [
            {"field": "api_key", "value": config.connection_params["public_key"]},
            {"field": "store_customer_card", "value": config.store_customer},
        ]
    @require_active_plugin
    def confirm_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        payment_intent_id = payment_information.token
        api_key = self.config.connection_params["secret_api_key"]

        # before we will call stripe API, let's check if the transaction object hasn't
        # been created by webhook handler
        payment_transaction = Transaction.objects.filter(
            payment_id=payment_information.payment_id,
            is_success=True,
            action_required=False,
            kind__in=[
                TransactionKind.AUTH,
                TransactionKind.CAPTURE,
                TransactionKind.PENDING,
            ],
        ).first()

        if payment_transaction:
            return GatewayResponse(
                is_success=True,
                action_required=False,
                kind=payment_transaction.kind,
                amount=payment_transaction.amount,
                currency=payment_transaction.currency,
                transaction_id=payment_transaction.token,
                error=None,
                raw_response=payment_transaction.gateway_response,
                transaction_already_processed=True,
            )

        payment_intent = None
        error = None
        payment_method_info = None
        if payment_intent_id:
            payment_intent, error = retrieve_payment_intent(api_key, payment_intent_id)

        kind = TransactionKind.AUTH
        if payment_intent:
            amount = price_from_minor_unit(
                payment_intent.amount, payment_intent.currency
            )
            currency = payment_intent.currency

            kind, action_required = self._get_transaction_details_for_stripe_status(
                payment_intent.status
            )
            if kind == TransactionKind.CAPTURE:
                payment_method_info = get_payment_method_details(payment_intent)
        else:
            action_required = False
            amount = payment_information.amount
            currency = payment_information.currency

        raw_response = None
        if payment_intent and payment_intent.last_response:
            raw_response = payment_intent.last_response.data

        return GatewayResponse(
            is_success=True if payment_intent else False,
            action_required=action_required,
            kind=kind,
            amount=amount,
            currency=currency,
            transaction_id=payment_intent.id if payment_intent else "",
            error=error.user_message if error else None,
            raw_response=raw_response,
            psp_reference=payment_intent.id if payment_intent else None,
            payment_method_info=payment_method_info,
        )