from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.models import Address

from . import stock
from .cart import Cart
from .emails import send_order_notification
from .forms import CheckoutForm
from .models import LOW_STOCK, Category, Color, Order, OrderItem, Product, Size, StoreSettings

PRODUCTS_PER_PAGE = 12

SORT_OPTIONS = {
    'featured': ('Featured', ['-is_featured', '-created_at']),
    'newest': ('Newest', ['-created_at']),
    'price-asc': ('Price: low to high', ['price']),
    'price-desc': ('Price: high to low', ['-price']),
}


def _product_qs():
    return Product.objects.active().prefetch_related('images', 'colors', 'variants')


def home(request):
    products = _product_qs()
    departments = Category.objects.filter(parent__isnull=True, is_active=True).prefetch_related('children')
    women = departments.filter(slug='women').first()
    spotlight = []
    if women:
        spotlight = [c for c in women.children.all() if c.is_active][:6]
    context = {
        'departments': departments,
        'spotlight_categories': spotlight,
        'best_sellers': products.filter(is_featured=True)[:8],
        'new_arrivals': products.order_by('-created_at')[:8],
        'sale_products': products.filter(compare_at_price__gt=F('price'))[:4],
        'hero_products': list(products.filter(is_featured=True).order_by('-price')[:3]),
        'sportswear': Category.objects.filter(path='women/sportswear').first(),
        'men': departments.filter(slug='men').first(),
    }
    return render(request, 'store/home.html', context)


def _parse_price(value):
    try:
        return Decimal(value) if value not in (None, '') else None
    except InvalidOperation:
        return None


def _product_listing(request, base_qs, template_context):
    """Apply the shared filter / sort / paginate logic used by every listing page."""
    options_qs = base_qs
    qs = base_qs

    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
            | Q(categories__name__icontains=query) | Q(colors__name__icontains=query)
        )
        options_qs = qs

    selected_sizes = request.GET.getlist('size')
    selected_colors = request.GET.getlist('color')
    min_price = _parse_price(request.GET.get('min'))
    max_price = _parse_price(request.GET.get('max'))
    only_sale = request.GET.get('sale') == '1'

    if selected_sizes:
        qs = qs.filter(sizes__name__in=selected_sizes)
    if selected_colors:
        qs = qs.filter(colors__name__in=selected_colors)
    if min_price is not None:
        qs = qs.filter(price__gte=min_price)
    if max_price is not None:
        qs = qs.filter(price__lte=max_price)
    if only_sale:
        qs = qs.filter(compare_at_price__gt=F('price'))

    sort = request.GET.get('sort', template_context.pop('default_sort', 'featured'))
    if sort not in SORT_OPTIONS:
        sort = 'featured'
    qs = qs.distinct().order_by(*SORT_OPTIONS[sort][1])

    page = Paginator(qs, PRODUCTS_PER_PAGE).get_page(request.GET.get('page'))
    option_ids = options_qs.values('pk')
    filter_count = len(selected_sizes) + len(selected_colors) + only_sale + (min_price is not None) + (max_price is not None)

    context = {
        'page_obj': page,
        'products': page.object_list,
        'query': query,
        'sort': sort,
        'sort_options': [(key, label) for key, (label, _) in SORT_OPTIONS.items()],
        'available_sizes': Size.objects.filter(products__in=option_ids).distinct(),
        'available_colors': Color.objects.filter(products__in=option_ids).distinct(),
        'selected_sizes': selected_sizes,
        'selected_colors': selected_colors,
        'min_price': request.GET.get('min', ''),
        'max_price': request.GET.get('max', ''),
        'only_sale': only_sale,
        'filter_count': filter_count,
        **template_context,
    }
    return render(request, 'store/product_list.html', context)


def shop(request, collection='all'):
    qs = _product_qs()
    titles = {
        'all': ('Shop all', 'Every piece in the Teffaha collection.'),
        'new': ('New in', 'Fresh arrivals, just landed.'),
        'sale': ('Sale', 'Favourites at softer prices — while sizes last.'),
    }
    if collection == 'sale':
        qs = qs.filter(compare_at_price__gt=F('price'))
    title, intro = titles[collection]
    return _product_listing(request, qs, {
        'title': title,
        'intro': intro,
        'collection': collection,
        'default_sort': 'newest' if collection == 'new' else 'featured',
    })


def search(request):
    query = request.GET.get('q', '').strip()
    return _product_listing(request, _product_qs(), {
        'title': f'Results for “{query}”' if query else 'Search',
        'intro': '',
        'collection': 'search',
    })


def category(request, path):
    cat = get_object_or_404(
        Category.objects.prefetch_related('children'), path=path.strip('/'), is_active=True
    )
    qs = _product_qs().in_categories(cat.get_descendant_ids())
    # Sidebar: this category's children, or its siblings when it is a leaf.
    nav_parent = cat if cat.children.exists() else cat.parent
    sidebar = nav_parent.children.filter(is_active=True) if nav_parent else []
    return _product_listing(request, qs, {
        'title': cat.name,
        'intro': cat.description,
        'category': cat,
        'breadcrumbs': cat.get_ancestors(include_self=True),
        'sidebar_parent': nav_parent,
        'sidebar_categories': sidebar,
        'collection': 'category',
    })


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.active().prefetch_related(
            'images__color', 'sizes', 'colors', 'categories', 'variants__size', 'variants__color'
        ),
        slug=slug,
    )
    images = list(product.images.all())
    # List colors in the same order as their photos so the pre-selected
    # color always matches the main image.
    photo_order = {img.color_id: i for i, img in reversed(list(enumerate(images))) if img.color_id}
    colors = sorted(product.colors.all(), key=lambda c: (photo_order.get(c.pk, len(images)), c.name))

    primary = product.primary_category()
    related = []
    if primary:
        related = (
            _product_qs().in_categories(primary.root.get_descendant_ids())
            .exclude(pk=product.pk).order_by('-is_featured', '-created_at')[:4]
        )
    return render(request, 'store/product_detail.html', {
        'product': product,
        'images': images,
        'colors': colors,
        'breadcrumbs': primary.get_ancestors(include_self=True) if primary else [],
        'related': related,
    })


# --- Cart -----------------------------------------------------------------

def _wants_json(request):
    return request.headers.get('x-requested-with') == 'fetch'


def cart_detail(request):
    cart = Cart(request)
    return render(request, 'store/cart.html', {'cart': cart, 'totals': cart.totals()})


@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(
        Product.objects.active().prefetch_related('variants__size', 'variants__color'), pk=product_id
    )
    size = request.POST.get('size', '')
    color = request.POST.get('color', '')
    try:
        quantity = max(1, int(request.POST.get('quantity', 1)))
    except ValueError:
        quantity = 1

    error = None
    if not product.in_stock:
        error = 'Sorry, this item is currently sold out.'
    elif product.sizes.exists() and not product.sizes.filter(name=size).exists():
        error = 'Please choose a size.'
    elif product.colors.exists() and not product.colors.filter(name=color).exists():
        error = 'Please choose a color.'
    else:
        # Exact stock numbers stay private: only 1 or 2 left is ever mentioned.
        in_bag = Cart(request).data.get(Cart.make_key(product.pk, size, color), {}).get('quantity', 0)
        available = product.stock_for(size, color)
        if available == 0:
            error = 'Sorry, this one is sold out.'
        elif in_bag + quantity > available:
            if available <= LOW_STOCK:
                error = f'Sorry, only {available} left' + (' — and it’s already in your bag.' if in_bag >= available else '.')
            else:
                error = 'Sorry, we don’t have that many in stock.'

    if error:
        if _wants_json(request):
            return JsonResponse({'ok': False, 'error': error}, status=400)
        messages.error(request, error)
        return redirect(product.get_absolute_url())

    cart = Cart(request)
    cart.add(product, size=size, color=color, quantity=quantity)

    if _wants_json(request):
        drawer = render_to_string(
            'store/partials/cart_drawer_body.html',
            {'cart': cart, 'totals': cart.totals(), 'added': product},
            request=request,
        )
        return JsonResponse({'ok': True, 'count': len(cart), 'drawer': drawer})
    messages.success(request, f'{product.name} was added to your bag.')
    return redirect('store:cart')


@require_POST
def cart_update(request):
    cart = Cart(request)
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        quantity = 1
    key = request.POST.get('key', '')
    line = next((line for line in cart.lines if line['key'] == key), None)
    if line and quantity > line['quantity'] and quantity > line['available']:
        # Don't reveal how many are left unless it's only 1 or 2.
        if 0 < line['available'] <= LOW_STOCK:
            quantity = line['available']
            messages.info(request, f'Only {quantity} left of {line["product"].name}.')
        else:
            quantity = line['quantity']
            messages.error(request, f'Sorry, we don’t have more of {line["product"].name} in stock.')
    cart.set_quantity(key, quantity)
    return redirect('store:cart')


@require_POST
def cart_remove(request):
    Cart(request).remove(request.POST.get('key', ''))
    return redirect('store:cart')


# --- Checkout --------------------------------------------------------------

PROMO_ACTIONS = ('apply_promo', 'remove_promo')


def checkout(request):
    cart = Cart(request)
    if not cart.lines:
        messages.info(request, 'Your bag is empty.')
        return redirect('store:cart')
    if any(line['short'] for line in cart.lines):
        messages.error(request, 'Some items in your bag have fewer left than you asked for. Please update your bag first.')
        return redirect('store:cart')

    store = StoreSettings.load()
    action = request.POST.get('action', '') if request.method == 'POST' else ''
    typed_code = request.POST.get('promo_code', '').strip()
    promo_error = ''

    if action == 'remove_promo':
        cart.remove_promo()
    elif typed_code:
        # "Apply" was pressed, or a code was typed but never applied before
        # "Place order" — either way it is checked before anything is saved.
        cart.apply_promo(typed_code)
    elif action == 'apply_promo':
        promo_error = 'Please enter a promo code.'

    totals = cart.totals(store)
    if totals['promo_error']:
        promo_error = totals['promo_error']
        cart.remove_promo()
        totals = cart.totals(store)

    user = request.user if request.user.is_authenticated else None
    saved_addresses = list(user.addresses.all()) if user else []
    if action in PROMO_ACTIONS:
        # Keep the delivery details typed so far, without flagging empty fields yet.
        names = [*CheckoutForm._meta.fields, 'save_address']
        form = CheckoutForm(user=user, initial={name: request.POST.get(name, '') for name in names})
    elif request.method == 'POST':
        form = CheckoutForm(request.POST, user=user)
    else:
        form = CheckoutForm(user=user, initial=_saved_details(user, saved_addresses))

    if request.method == 'POST' and not action and form.is_valid() and not promo_error:
        try:
            order = _place_order(request, cart, store, form, totals)
        except stock.OutOfStock as error:
            messages.error(
                request,
                f'Sorry — {", ".join(stock.describe(error.keys))} just sold out or has fewer left than you wanted. '
                'Please check your bag.',
            )
            return redirect('store:cart')
        if order:
            return redirect('store:order_success', number=order.number)
        promo_error = (
            'Sorry, this promo code has just been fully used, so it was removed. '
            'Please check your total and place your order again.'
        )
        cart.remove_promo()
        totals = cart.totals(store)

    return render(request, 'store/checkout.html', {
        'cart': cart,
        'totals': totals,
        'form': form,
        'promo_error': promo_error,
        'promo_input': typed_code if promo_error else '',
        'saved_addresses': saved_addresses,
        'selected_address': request.POST.get('saved_address') or next(
            (str(a.pk) for a in saved_addresses if a.is_default), ''
        ),
    })


def _saved_details(user, saved_addresses):
    """Checkout form pre-filled from the customer's account and default address."""
    if user is None:
        return {}
    initial = {'full_name': user.get_full_name(), 'email': user.email}
    default = next((a for a in saved_addresses if a.is_default), None)
    if default:
        initial.update(full_name=default.full_name, phone=default.phone, city=default.city, address=default.address)
    return initial


def _place_order(request, cart, store, form, totals):
    """Save the order and queue its email. Returns None, saving nothing, if the
    promo code reached its usage limit after the totals were calculated."""
    promo = totals['promo']
    with transaction.atomic():
        if promo and not promo.claim():
            return None
        # Raises OutOfStock (rolling everything back) if something sold out meanwhile.
        stock.reserve([(line['product'].pk, line['size'], line['color'], line['quantity']) for line in cart.lines])
        order = form.save(commit=False)
        order.user = request.user if request.user.is_authenticated else None
        order.subtotal = totals['subtotal']
        order.promo_code = promo.code if promo else ''
        order.discount = totals['discount']
        order.delivery_fee = totals['delivery_fee']
        order.total = totals['total']
        order.currency = store.currency
        order.save()
        OrderItem.objects.bulk_create([
            OrderItem(
                order=order,
                product=line['product'],
                product_name=line['product'].name,
                product_code=line['product'].code,
                size=line['size'],
                color=line['color'],
                unit_price=line['unit_price'],
                quantity=line['quantity'],
            )
            for line in cart.lines
        ])
        if order.user and form.cleaned_data.get('save_address'):
            Address.remember(order.user, order)

        admin_url = request.build_absolute_uri(
            reverse('admin:store_order_change', args=[order.pk])
        )

        def notify():
            if send_order_notification(order, admin_url=admin_url):
                Order.objects.filter(pk=order.pk).update(email_sent=True)

        transaction.on_commit(notify)

    cart.clear()
    cart.remove_promo()
    placed = request.session.get('placed_orders', [])
    request.session['placed_orders'] = (placed + [order.number])[-10:]
    return order


def order_success(request, number):
    # Only the browser that placed the order may view its confirmation page.
    if number not in request.session.get('placed_orders', []):
        raise Http404
    order = get_object_or_404(Order.objects.prefetch_related('items__product__images__color'), number=number)
    return render(request, 'store/order_success.html', {'order': order})
