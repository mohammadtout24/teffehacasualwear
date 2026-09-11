from django.db.models import Prefetch

from .cart import Cart
from .models import Category, StoreSettings


def store(request):
    """Navigation tree, store settings and cart count for every page."""
    active_children = Category.objects.filter(is_active=True)
    nav_categories = (
        Category.objects.filter(parent__isnull=True, is_active=True)
        .prefetch_related(
            Prefetch(
                'children',
                queryset=active_children.prefetch_related(
                    Prefetch('children', queryset=active_children)
                ),
            )
        )
    )
    cart = Cart(request)
    return {
        'store': StoreSettings.load(),
        'nav_categories': nav_categories,
        'cart': cart,
        'cart_count': len(cart),
    }
