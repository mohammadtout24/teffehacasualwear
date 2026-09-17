"""Keeping stock counts in step with online orders and in-store sales.

A "line" is (product_id, size name, color name, quantity). Sizes and colors are
matched by name, so order items (which store names) map back to stock rows.
"""
from collections import Counter

from django.db.models import F

from .models import Product, ProductVariant


class OutOfStock(Exception):
    """Raised when an online order asks for more than is in stock."""

    def __init__(self, keys):
        super().__init__('Not enough stock')
        self.keys = keys  # [(product_id, size, color)]


def _lookup(product_id, size, color):
    lookup = {'product_id': product_id}
    lookup.update({'size__name': size} if size else {'size__isnull': True})
    lookup.update({'color__name': color} if color else {'color__isnull': True})
    return lookup


def _combine(lines):
    totals = Counter()
    for product_id, size, color, quantity in lines:
        if product_id:
            totals[(product_id, size or '', color or '')] += quantity
    return totals


def order_lines(order):
    return [(item.product_id, item.size, item.color, item.quantity) for item in order.items.all()]


def reserve(lines):
    """Take stock for an online order, all or nothing.

    Call inside transaction.atomic(): raises OutOfStock, rolling the transaction
    back, when any line has fewer left than ordered.
    """
    short = []
    for (product_id, size, color), quantity in _combine(lines).items():
        taken = ProductVariant.objects.filter(
            **_lookup(product_id, size, color), quantity__gte=quantity
        ).update(quantity=F('quantity') - quantity)
        if not taken:
            short.append((product_id, size, color))
    if short:
        raise OutOfStock(short)


def remove(lines):
    """Take stock for an in-store sale. Never refuses and never goes below zero;
    returns the lines whose stock count was lower than what was sold."""
    short = []
    for key, quantity in _combine(lines).items():
        variant = ProductVariant.objects.select_for_update().filter(**_lookup(*key)).first()
        if variant is None or variant.quantity < quantity:
            short.append(key)
        if variant is not None:
            variant.quantity = max(0, variant.quantity - quantity)
            variant.save(update_fields=['quantity'])
    return short


def give_back(lines):
    """Put stock back, e.g. when an order is cancelled."""
    for key, quantity in _combine(lines).items():
        ProductVariant.objects.filter(**_lookup(*key)).update(quantity=F('quantity') + quantity)


def describe(keys):
    """Readable names such as "Linen Shirt (Beige, size M)"."""
    names = dict(Product.objects.filter(pk__in={key[0] for key in keys}).values_list('pk', 'name'))
    described = []
    for product_id, size, color in keys:
        extra = ', '.join(part for part in (color, size and f'size {size}') if part)
        described.append(names.get(product_id, 'A product') + (f' ({extra})' if extra else ''))
    return described
