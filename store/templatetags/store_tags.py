import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

from ..money import format_money

register = template.Library()


@register.simple_tag
def asset(path):
    """Static file URL with a version number, so browsers fetch the new CSS/JS
    after every change instead of reusing an old cached copy."""
    url = static(path)
    found = finders.find(path)
    return f'{url}?v={int(os.path.getmtime(found))}' if found else url


def _store_currency(context):
    store = context.get('store')
    return store.currency if store else '$'


@register.simple_tag(takes_context=True)
def money(context, amount, currency=None):
    """Format an amount with the store currency: 12 -> "$12", 12.5 -> "$12.50"."""
    return format_money(amount, currency or _store_currency(context))


@register.simple_tag(takes_context=True)
def promo_label(context, promo):
    """What a promo code gives: "10% off", "$5 off" or "Free delivery"."""
    return promo.describe(_store_currency(context)) if promo else ''


@register.simple_tag(takes_context=True)
def query_with(context, **changes):
    """Current query string with some keys replaced (None removes a key).
    Always drops `page` unless it is set explicitly."""
    params = context['request'].GET.copy()
    if 'page' not in changes:
        params.pop('page', None)
    for key, value in changes.items():
        if value is None or value == '':
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f'?{encoded}' if encoded else '?'


@register.simple_tag(takes_context=True)
def query_toggle(context, key, value):
    """Current query string with `value` added to / removed from multi-value `key`."""
    params = context['request'].GET.copy()
    params.pop('page', None)
    values = params.getlist(key)
    value = str(value)
    if value in values:
        values.remove(value)
    else:
        values.append(value)
    params.setlist(key, values)
    encoded = params.urlencode()
    return f'?{encoded}' if encoded else '?'


@register.filter
def is_light(hex_code):
    """True for pale swatches that need a visible border."""
    try:
        h = hex_code.lstrip('#')
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, AttributeError):
        return False
    return (0.299 * r + 0.587 * g + 0.114 * b) > 215
