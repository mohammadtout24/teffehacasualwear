from decimal import Decimal

from .models import Product, StoreSettings

CART_SESSION_KEY = 'cart'
MAX_QUANTITY = 20


class Cart:
    """Session-backed shopping cart.

    Each line is keyed by product id + size + color, so the same product in
    two sizes shows up as two lines.
    """

    def __init__(self, request):
        self.session = request.session
        self.data = self.session.setdefault(CART_SESSION_KEY, {})
        self._lines = None

    @staticmethod
    def make_key(product_id, size='', color=''):
        return f'{product_id}|{size}|{color}'

    def add(self, product, size='', color='', quantity=1):
        key = self.make_key(product.pk, size, color)
        line = self.data.get(key, {'product_id': product.pk, 'size': size, 'color': color, 'quantity': 0})
        line['quantity'] = min(line['quantity'] + quantity, MAX_QUANTITY)
        self.data[key] = line
        self._save()

    def set_quantity(self, key, quantity):
        if key not in self.data:
            return
        if quantity <= 0:
            del self.data[key]
        else:
            self.data[key]['quantity'] = min(quantity, MAX_QUANTITY)
        self._save()

    def remove(self, key):
        self.data.pop(key, None)
        self._save()

    def clear(self):
        self.session[CART_SESSION_KEY] = {}
        self.data = self.session[CART_SESSION_KEY]
        self._save()

    def _save(self):
        self.session.modified = True
        self._lines = None

    @property
    def lines(self):
        """Cart lines joined with live products. Lines for deleted or hidden
        products are dropped silently."""
        if self._lines is None:
            ids = {line['product_id'] for line in self.data.values()}
            products = Product.objects.active().filter(pk__in=ids).prefetch_related('images__color')
            by_id = {p.pk: p for p in products}
            lines = []
            for key, line in list(self.data.items()):
                product = by_id.get(line['product_id'])
                if product is None:
                    del self.data[key]
                    self.session.modified = True
                    continue
                lines.append({
                    'key': key,
                    'product': product,
                    'image': product.image_for(line['color']),
                    'size': line['size'],
                    'color': line['color'],
                    'quantity': line['quantity'],
                    'unit_price': product.price,
                    'line_total': product.price * line['quantity'],
                })
            self._lines = lines
        return self._lines

    def __iter__(self):
        return iter(self.lines)

    def __len__(self):
        return sum(line['quantity'] for line in self.data.values())

    @property
    def subtotal(self):
        return sum((line['line_total'] for line in self.lines), Decimal('0.00'))

    def totals(self, store=None):
        store = store or StoreSettings.load()
        subtotal = self.subtotal
        delivery = store.delivery_fee_for(subtotal)
        remaining = None
        if store.free_delivery_over is not None and delivery > 0:
            remaining = store.free_delivery_over - subtotal
        return {
            'subtotal': subtotal,
            'delivery_fee': delivery,
            'total': subtotal + delivery,
            'free_delivery_remaining': remaining,
        }
