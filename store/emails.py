import logging

import requests
from django.conf import settings
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

RESEND_API_URL = 'https://api.resend.com/emails'


def send_order_notification(order, admin_url=''):
    """Email a new order to the store via Resend's HTTP API.

    Uses the HTTP API rather than SMTP so this also works on hosts (e.g.
    PythonAnywhere's free tier) that block raw SMTP but allow HTTPS to
    whitelisted domains. Returns True when Resend accepted the email.
    """
    if not settings.RESEND_API_KEY:
        logger.info('RESEND_API_KEY not set; skipping order email for %s.', order.number)
        return False

    context = {'order': order, 'items': order.items.all(), 'admin_url': admin_url}
    payload = {
        'from': f'Teffaha Orders <{settings.DEFAULT_FROM_EMAIL}>',
        'to': [settings.ORDER_NOTIFICATION_EMAIL],
        'subject': (
            f'New order {order.number} — {order.full_name} — '
            f'{order.currency}{order.total}'
        ),
        'html': render_to_string('emails/order_notification.html', context),
        'text': render_to_string('emails/order_notification.txt', context),
    }
    if order.email:
        payload['reply_to'] = order.email

    try:
        response = requests.post(
            RESEND_API_URL,
            headers={'Authorization': f'Bearer {settings.RESEND_API_KEY}'},
            json=payload,
            timeout=10,
        )
    except requests.RequestException:
        logger.exception('Failed to send order email for %s via Resend.', order.number)
        return False

    if not response.ok:
        logger.warning(
            'Resend API returned %s for order %s: %s',
            response.status_code, order.number, response.text,
        )
        return False
    return True
