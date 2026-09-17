import csv
import io
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.core.management import call_command
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Max, Q, Sum
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from store import stock
from store.models import (
    LOW_STOCK, Category, Color, Order, OrderItem, Product, ProductImage, ProductVariant, PromoCode, Size,
    StoreSettings,
)

from . import analytics as stats
from .forms import (
    CategoryForm, ColorForm, ProductForm, PromoCodeForm, SizeForm, StaffLoginForm, StoreSettingsForm,
)

User = get_user_model()


# --- Helpers ----------------------------------------------------------------

def staff_required(view):
    """Only admin (staff) accounts may use the store manager."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_staff):
            return redirect(f"{reverse('manager:login')}?next={quote(request.get_full_path())}")
        return view(request, *args, **kwargs)
    return wrapper


def _safe_next(request, default):
    url = request.POST.get('next') or request.GET.get('next')
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return url
    return default


def _wants_json(request):
    return request.headers.get('x-requested-with') == 'fetch'


def _first_error(form):
    for errors in form.errors.values():
        return errors[0]
    return 'Please check the form.'


def _category_tree(queryset=None):
    """Categories in menu order (parents before children), each with `indent`."""
    nodes = list(Category.objects.all() if queryset is None else queryset)
    children = {}
    for node in nodes:
        children.setdefault(node.parent_id, []).append(node)
    ordered = []

    def walk(parent_id, depth):
        for node in sorted(children.get(parent_id, []), key=lambda c: (c.sort_order, c.name)):
            node.indent = '— ' * depth
            ordered.append(node)
            walk(node.pk, depth + 1)

    walk(None, 0)
    return ordered


def _toggle(request, obj, allowed, fallback_url):
    field = request.POST.get('field')
    if field not in allowed:
        return HttpResponseBadRequest('Unknown field')
    setattr(obj, field, not getattr(obj, field))
    obj.save(update_fields=[field])
    if _wants_json(request):
        return JsonResponse({'ok': True, 'value': getattr(obj, field)})
    return redirect(_safe_next(request, fallback_url))


def _stock_warning(keys):
    return (
        f'Heads up: fewer were in stock than were sold for {", ".join(stock.describe(keys))}. '
        'The stock is now 0 — please recount and update it.'
    )


def _delta(current, previous):
    """Change vs. the same point last month, worded for the stat tiles."""
    if not previous:
        return {'direction': 'flat', 'text': 'Nothing at this point last month' if current else 'Nothing yet this month'}
    change = round((current - previous) / previous * 100)
    if change > 0:
        return {'direction': 'up', 'text': f'Up {change}% vs. this time last month'}
    if change < 0:
        return {'direction': 'down', 'text': f'Down {-change}% vs. this time last month'}
    return {'direction': 'flat', 'text': 'Same as this time last month'}


# --- Login --------------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect(_safe_next(request, reverse('manager:dashboard')))
    form = StaffLoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        return redirect(_safe_next(request, reverse('manager:dashboard')))
    return render(request, 'manager/login.html', {
        'form': form, 'next': request.POST.get('next') or request.GET.get('next', ''),
    })


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, 'You’ve been logged out.')
    return redirect('manager:login')


# --- Dashboard ----------------------------------------------------------------

@staff_required
def dashboard(request):
    now = timezone.localtime()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_start = (month_start - timedelta(days=1)).replace(day=1)
    prev_cutoff = min(prev_start + (now - month_start), month_start)

    active = Order.objects.exclude(status=Order.Status.CANCELLED)
    this_month = active.filter(created_at__gte=month_start)
    same_time_last_month = active.filter(created_at__gte=prev_start, created_at__lt=prev_cutoff)
    month_orders, prev_orders = this_month.count(), same_time_last_month.count()
    month_sales = this_month.aggregate(total=Sum('total'))['total'] or Decimal('0')
    prev_sales = same_time_last_month.aggregate(total=Sum('total'))['total'] or Decimal('0')
    in_store_this_month = this_month.filter(channel=Order.Channel.IN_STORE)
    month_in_store = in_store_this_month.count()
    store_sales = in_store_this_month.aggregate(total=Sum('total'))['total'] or Decimal('0')
    customers = User.objects.filter(is_staff=False)

    top = list(
        OrderItem.objects.filter(order__created_at__gte=now - timedelta(days=30))
        .exclude(order__status=Order.Status.CANCELLED)
        .values('product_id', 'product_name')
        .annotate(sold=Sum('quantity'), revenue=Sum(F('unit_price') * F('quantity')))
        .order_by('-sold')[:5]
    )
    products = Product.objects.prefetch_related('images').in_bulk([t['product_id'] for t in top if t['product_id']])
    for item in top:
        product = products.get(item['product_id'])
        item['image'] = product.main_image if product else None

    attention = [
        {'count': Product.objects.filter(is_active=True).annotate(stock_total=Sum('variants__quantity'))
            .filter(Q(stock_total=0) | Q(stock_total__isnull=True)).count(),
         'label': 'products out of stock', 'url': reverse('manager:products') + '?status=out_of_stock'},
        {'count': Product.objects.filter(
            is_active=True, variants__quantity__gte=1, variants__quantity__lte=LOW_STOCK).distinct().count(),
         'label': 'products running low (1–2 left of a size or color)',
         'url': reverse('manager:products') + '?status=low_stock'},
        {'count': Product.objects.filter(is_active=True, in_stock=False).count(),
         'label': 'products marked not for sale', 'url': reverse('manager:products') + '?status=sold_out'},
        {'count': Product.objects.filter(images__isnull=True).count(),
         'label': 'products without photos', 'url': reverse('manager:products') + '?status=no_photos'},
        {'count': Product.objects.filter(is_active=False).count(),
         'label': 'hidden products', 'url': reverse('manager:products') + '?status=hidden'},
    ]

    hour = now.hour
    return render(request, 'manager/dashboard.html', {
        'section': 'dashboard',
        'greeting': 'morning' if hour < 12 else 'afternoon' if hour < 18 else 'evening',
        'kpis': {
            'new_orders': Order.objects.filter(status=Order.Status.NEW).count(),
            'month_orders': month_orders,
            'orders_delta': _delta(month_orders, prev_orders),
            'month_sales': month_sales,
            'sales_delta': _delta(month_sales, prev_sales),
            'month_online': month_orders - month_in_store,
            'month_in_store': month_in_store,
            'store_sales': store_sales,
            'customers': customers.count(),
            'new_customers': customers.filter(date_joined__gte=month_start).count(),
        },
        'recent_orders': Order.objects.filter(channel=Order.Channel.ONLINE).prefetch_related('items')[:8],
        'top_products': top,
        'attention': [a for a in attention if a['count']],
    })


# --- Orders -------------------------------------------------------------------

ORDER_FLOW = [Order.Status.NEW, Order.Status.CONFIRMED, Order.Status.SHIPPED, Order.Status.DELIVERED]
NEXT_STEP = {
    Order.Status.NEW: (Order.Status.CONFIRMED, 'Confirm order'),
    Order.Status.CONFIRMED: (Order.Status.SHIPPED, 'Mark as out for delivery'),
    Order.Status.SHIPPED: (Order.Status.DELIVERED, 'Mark as delivered'),
}


@staff_required
def order_list(request):
    statuses = dict(Order.Status.choices)
    status = request.GET.get('status', 'all')
    if status not in statuses:
        status = 'all'
    query = request.GET.get('q', '').strip()

    orders = Order.objects.filter(channel=Order.Channel.ONLINE).prefetch_related('items')
    if query:
        orders = orders.filter(
            Q(number__icontains=query) | Q(full_name__icontains=query) | Q(phone__icontains=query)
            | Q(city__icontains=query) | Q(email__icontains=query)
        )
    counts = {row['status']: row['n'] for row in orders.order_by().values('status').annotate(n=Count('pk'))}
    tabs = [('all', 'All', sum(counts.values()))] + [
        (value, label, counts.get(value, 0)) for value, label in Order.Status.choices
    ]
    if status != 'all':
        orders = orders.filter(status=status)

    return render(request, 'manager/orders.html', {
        'section': 'orders',
        'page_obj': Paginator(orders, 20).get_page(request.GET.get('page')),
        'tabs': tabs,
        'status': status,
        'status_label': statuses.get(status, ''),
        'query': query,
    })


@staff_required
def order_detail(request, number):
    order = get_object_or_404(
        Order.objects.select_related('user', 'recorded_by').prefetch_related('items__product__images__color'),
        number=number,
    )
    current = ORDER_FLOW.index(order.status) if order.status in ORDER_FLOW else -1
    steps = [
        {'label': Order.Status(value).label,
         'state': 'done' if i < current else 'current' if i == current else 'todo'}
        for i, value in enumerate(ORDER_FLOW)
    ]
    return render(request, 'manager/order_detail.html', {
        'section': 'in_store' if order.channel == Order.Channel.IN_STORE else 'orders',
        'order': order,
        'steps': steps,
        'next_step': NEXT_STEP.get(order.status),
        'statuses': Order.Status.choices,
        'whatsapp': re.sub(r'\D', '', order.phone),
    })


@staff_required
@require_POST
def order_status(request, number):
    order = get_object_or_404(Order, number=number)
    status = request.POST.get('status')
    if status in dict(Order.Status.choices) and status != order.status:
        was_cancelled = order.status == Order.Status.CANCELLED
        note, short = '', []
        with transaction.atomic():
            order.status = status
            order.save(update_fields=['status'])
            if status == Order.Status.CANCELLED:
                stock.give_back(stock.order_lines(order))
                note = ' Its items were put back in stock.'
            elif was_cancelled:
                short = stock.remove(stock.order_lines(order))
                note = ' Its items were taken out of stock again.'
        messages.success(request, f'Order {order.number} is now “{order.get_status_display()}”.{note}')
        if short:
            messages.warning(request, _stock_warning(short))
    return redirect(_safe_next(request, reverse('manager:order', args=[order.number])))


@staff_required
@require_POST
def order_delete(request, number):
    order = get_object_or_404(Order, number=number)
    with transaction.atomic():
        if order.status != Order.Status.CANCELLED:  # cancelled orders already gave their stock back
            stock.give_back(stock.order_lines(order))
        order.delete()
    if order.channel == Order.Channel.IN_STORE:
        messages.success(request, f'Sale {number} was deleted.')
        return redirect('manager:in_store')
    messages.success(request, f'Order {number} was deleted.')
    return redirect('manager:orders')


# --- Products -----------------------------------------------------------------

PRODUCT_FILTERS = [
    ('all', 'All products'),
    ('visible', 'Showing in shop'),
    ('hidden', 'Hidden'),
    ('low_stock', 'Running low (1–2 left)'),
    ('out_of_stock', 'Out of stock'),
    ('sold_out', 'Not for sale'),
    ('on_sale', 'On sale'),
    ('best', 'Best sellers'),
    ('no_photos', 'Without photos'),
    ('sample', 'Sample products'),
]


@staff_required
def product_list(request):
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', 'all')
    category_id = request.GET.get('category', '')

    products = Product.objects.prefetch_related('images', 'categories', 'variants')
    if query:
        products = products.filter(Q(name__icontains=query) | Q(code__icontains=query))
    category = Category.objects.filter(pk=category_id).first() if category_id.isdigit() else None
    if category:
        products = products.in_categories(category.get_descendant_ids())
    filters = {
        'visible': Q(is_active=True), 'hidden': Q(is_active=False), 'sold_out': Q(in_stock=False),
        'on_sale': Q(compare_at_price__gt=F('price')), 'best': Q(is_featured=True),
        'no_photos': Q(images__isnull=True), 'sample': Q(is_sample=True),
    }
    if status == 'low_stock':
        products = products.filter(variants__quantity__gte=1, variants__quantity__lte=LOW_STOCK).distinct()
    elif status == 'out_of_stock':
        products = products.annotate(stock_total=Sum('variants__quantity')).filter(
            Q(stock_total=0) | Q(stock_total__isnull=True)
        )
    elif status in filters:
        products = products.filter(filters[status])
    else:
        status = 'all'

    return render(request, 'manager/products.html', {
        'section': 'products',
        'page_obj': Paginator(products.order_by('-created_at'), 25).get_page(request.GET.get('page')),
        'query': query,
        'status': status,
        'category_id': str(category.pk) if category else '',
        'categories': _category_tree(),
        'product_filters': PRODUCT_FILTERS,
        'sample_count': Product.objects.filter(is_sample=True).count(),
    })


def _selected(form, name):
    return {str(value) for value in (form[name].value() or [])}


def _save_product_extras(request, form, product):
    """New color/sizes typed in the form, photo changes and new uploads."""
    data = form.cleaned_data
    color_name = data.get('new_color_name', '').strip()
    if color_name:
        color = Color.objects.filter(name__iexact=color_name).first() or Color.objects.create(
            name=color_name, hex_code=data['new_color_hex'].upper()
        )
        product.colors.add(color)

    for name in [part.strip() for part in data.get('new_sizes', '').split(',') if part.strip()]:
        size = Size.objects.filter(name__iexact=name).first()
        if size is None:
            last = Size.objects.order_by('-sort_order').first()
            size = Size.objects.create(name=name[:20], sort_order=last.sort_order + 1 if last else 0)
        product.sizes.add(size)

    colors = {str(c.pk): c for c in Color.objects.all()}
    main = request.POST.get('main_image', '')
    photos = []
    for image in product.images.all():
        if request.POST.get(f'image-{image.pk}-remove'):
            image.image.delete(save=False)
            image.delete()
            continue
        color_key = f'image-{image.pk}-color'
        if color_key in request.POST:
            image.color = colors.get(request.POST[color_key])
        photos.append(image)
    photos.sort(key=lambda image: (str(image.pk) != main, image.sort_order, image.pk))
    for upload in data.get('new_images') or []:
        photos.append(ProductImage(product=product, image=upload, alt=product.name, color=data.get('new_images_color')))
    for position, image in enumerate(photos):
        image.sort_order = position
        image.save()


def _save_stock(request, product):
    """One stock row per ticked size × color; rows for combinations no longer ticked are removed."""
    grid_sent = request.POST.get('stock_grid') == '1'  # the stock table was on the page
    sizes = list(product.sizes.all()) or [None]
    colors = list(product.colors.all()) or [None]
    existing = {(v.size_id, v.color_id): v for v in product.variants.all()}
    keep = set()
    for size in sizes:
        for color in colors:
            key = (size.pk if size else None, color.pk if color else None)
            keep.add(key)
            raw = request.POST.get(f'stock-{key[0] or 0}-{key[1] or 0}', '').strip()
            quantity = min(int(raw), 99_999) if raw.isdigit() and grid_sent else 0
            variant = existing.get(key)
            if variant is None:
                ProductVariant.objects.create(product=product, size=size, color=color, quantity=quantity)
            elif grid_sent and variant.quantity != quantity:
                variant.quantity = quantity
                variant.save(update_fields=['quantity'])
    for key, variant in existing.items():
        if key not in keep:
            variant.delete()


def _stock_data(request, product):
    """What the stock table on the product form needs (built in the browser from the ticked options)."""
    if request.method == 'POST':
        values = {name[len('stock-'):]: value for name, value in request.POST.items() if name.startswith('stock-')}
    elif product:
        values = {f'{v.size_id or 0}-{v.color_id or 0}': v.quantity for v in product.variants.all()}
    else:
        values = {}
    return {
        'values': values,
        'low': LOW_STOCK,
        'sizes': [{'id': size.pk, 'name': size.name} for size in Size.objects.all()],
        'colors': [{'id': color.pk, 'name': color.name, 'hex': color.hex_code} for color in Color.objects.all()],
    }


@staff_required
def product_form(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else None
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            product = form.save()
            _save_product_extras(request, form, product)
            _save_stock(request, product)
        messages.success(request, f'“{product.name}” was saved.')
        if request.POST.get('then') == 'new':
            return redirect('manager:product_add')
        return redirect('manager:product_edit', pk=product.pk)

    return render(request, 'manager/product_form.html', {
        'section': 'products',
        'form': form,
        'product': product,
        'images': list(product.images.select_related('color')) if product else [],
        'photos_lost': request.method == 'POST' and bool(request.FILES),
        'categories': _category_tree(),
        'all_sizes': Size.objects.all(),
        'all_colors': Color.objects.all(),
        'selected_categories': _selected(form, 'categories'),
        'selected_sizes': _selected(form, 'sizes'),
        'selected_colors': _selected(form, 'colors'),
        'stock_data': _stock_data(request, product),
    })


@staff_required
@require_POST
def product_toggle(request, pk):
    product = get_object_or_404(Product, pk=pk)
    return _toggle(request, product, {'in_stock', 'is_active', 'is_featured'}, reverse('manager:products'))


@staff_required
@require_POST
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    for image in product.images.all():
        image.image.delete(save=False)
    product.delete()
    messages.success(request, f'“{product.name}” was deleted.')
    return redirect('manager:products')


@staff_required
@require_POST
def remove_sample_products(request):
    count = Product.objects.filter(is_sample=True).count()
    call_command('remove_sample_data', stdout=io.StringIO())
    messages.success(request, f'Removed {count} sample products. Your own products weren’t touched.')
    return redirect('manager:products')


# --- Categories ---------------------------------------------------------------

def _find_product(raw):
    """A product by its Product ID (not case-sensitive).

    Products that have no ID yet can still be found by their number, e.g. "#12".
    """
    raw = (raw or '').strip()
    if not raw:
        return None
    products = Product.objects.prefetch_related(
        'images__color', 'sizes', 'colors', 'variants__size', 'variants__color'
    )
    product = products.filter(code__iexact=raw).first()
    number = raw.lstrip('#').strip()
    if product is None and number.isdigit():
        product = products.filter(pk=int(number)).first()
    return product


@staff_required
def product_lookup(request):
    product = _find_product(request.GET.get('id'))
    if product is None:
        return JsonResponse({'ok': False, 'error': 'No product has this ID.'}, status=404)
    image = product.main_image
    photos = {}  # color name -> the first photo showing that color
    for photo in product.images.all():
        if photo.color_id and photo.color.name not in photos:
            photos[photo.color.name] = photo.image.url
    return JsonResponse({
        'ok': True,
        'id': product.display_id,
        'name': product.name,
        'price': str(product.price),
        'sizes': [size.name for size in product.sizes.all()],
        'colors': [color.name for color in product.colors.all()],
        'image': image.image.url if image else '',
        'photos': photos,
        'in_stock': product.in_stock,
        'stock': {f'{size}|{color}': quantity for (size, color), quantity in product.stock_map().items()},
    })


def _parse_sale_items(post):
    """Read the item rows of the in-store sale form.

    Returns (items ready to save, error messages, rows to re-fill the form with).
    """
    names = ('item_product', 'item_size', 'item_color', 'item_qty', 'item_price')
    columns = [post.getlist(name) for name in names]
    items, errors, rows = [], [], []
    for index in range(len(columns[0])):
        raw, size, color, qty_raw, price_raw = (
            column[index].strip() if index < len(column) else '' for column in columns
        )
        if not raw:
            continue
        rows.append({'product': raw, 'size': size, 'color': color, 'qty': qty_raw, 'price': price_raw})
        label = f'Item {len(rows)}'
        product = _find_product(raw)
        if product is None:
            errors.append(f'{label}: there’s no product with ID “{raw}”.')
            continue
        label = f'{label} ({product.name})'
        quantity = int(qty_raw) if qty_raw.isdigit() else 0
        if not 1 <= quantity <= 999:
            errors.append(f'{label}: enter a quantity of at least 1.')
            continue
        try:
            price = Decimal(price_raw) if price_raw else product.price
        except InvalidOperation:
            price = None
        if price is None or not price.is_finite() or price < 0:
            errors.append(f'{label}: enter a valid price.')
            continue
        if not size and product.sizes.all():
            errors.append(f'{label}: choose a size.')
            continue
        if not color and product.colors.all():
            errors.append(f'{label}: choose a color.')
            continue
        if size and size not in {s.name for s in product.sizes.all()}:
            errors.append(f'{label}: size “{size}” isn’t one of its sizes.')
            continue
        if color and color not in {c.name for c in product.colors.all()}:
            errors.append(f'{label}: color “{color}” isn’t one of its colors.')
            continue
        items.append({
            'product': product, 'size': size, 'color': color,
            'quantity': quantity, 'unit_price': price.quantize(Decimal('0.01')),
        })
    if not rows:
        errors.append('Add at least one product by its ID.')
    return items, errors, rows


def _in_store_promo(code, subtotal, currency):
    """(promo, error message) for a code used on an in-store sale worth `subtotal`."""
    promo = PromoCode.find(code)
    if promo is None:
        return None, 'This promo code is not valid.'
    if promo.kind == PromoCode.Kind.FREE_DELIVERY:
        return None, 'Free-delivery codes can’t be used for in-store sales.'
    error = promo.problem(subtotal, currency)
    return (None, error) if error else (promo, '')


def _save_in_store_sale(request, store, items, subtotal, promo):
    """Save the sale and take its items out of stock.

    Returns (sale, lines that had less stock than sold); the sale is None, and
    nothing is saved, if the promo code ran out meanwhile.
    """
    with transaction.atomic():
        if promo and not promo.claim():
            return None, []
        discount = promo.discount_for(subtotal) if promo else Decimal('0.00')
        sale = Order.objects.create(
            channel=Order.Channel.IN_STORE,
            status=Order.Status.DELIVERED,
            payment_method='Paid in store',
            full_name='', phone='', city='', address='',
            subtotal=subtotal,
            promo_code=promo.code if promo else '',
            discount=discount,
            total=subtotal - discount,
            currency=store.currency,
            recorded_by=request.user,
        )
        OrderItem.objects.bulk_create([
            OrderItem(
                order=sale, product=item['product'], product_name=item['product'].name,
                product_code=item['product'].code,
                size=item['size'], color=item['color'],
                unit_price=item['unit_price'], quantity=item['quantity'],
            )
            for item in items
        ])
        short = stock.remove([
            (item['product'].pk, item['size'], item['color'], item['quantity']) for item in items
        ])
    return sale, short


@staff_required
def in_store_promo_check(request):
    """Rules of a promo code, so the sale form can show the discount as items change.

    The minimum order is left to the browser (it knows the current total); the
    sale is checked again on the server when it's saved.
    """
    store = StoreSettings.load()
    code = request.GET.get('code', '')
    promo = PromoCode.find(code)
    ignore_minimum = (promo.min_subtotal or Decimal('0')) if promo else Decimal('0')
    promo, error = _in_store_promo(code, ignore_minimum, store.currency)
    if error:
        return JsonResponse({'ok': False, 'error': error})
    return JsonResponse({
        'ok': True,
        'code': promo.code,
        'kind': promo.kind,
        'value': float(promo.value),
        'min_subtotal': float(promo.min_subtotal or 0),
        'label': promo.describe(store.currency),
    })


@staff_required
def in_store_list(request):
    query = request.GET.get('q', '').strip()
    all_sales = Order.objects.filter(channel=Order.Channel.IN_STORE)
    sales = all_sales.select_related('recorded_by').prefetch_related('items__product__images__color')
    if query:
        sales = sales.filter(
            Q(number__icontains=query) | Q(items__product_name__icontains=query)
            | Q(items__product_code__icontains=query)
        ).distinct()
    now = timezone.localtime()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    stats = lambda qs: qs.aggregate(count=Count('pk'), total=Sum('total'))  # noqa: E731
    return render(request, 'manager/in_store.html', {
        'section': 'in_store',
        'query': query,
        'page_obj': Paginator(sales, 25).get_page(request.GET.get('page')),
        'today': stats(all_sales.filter(created_at__gte=today_start)),
        'month': stats(all_sales.filter(created_at__gte=today_start.replace(day=1))),
    })


@staff_required
def in_store_new(request):
    store = StoreSettings.load()
    item_errors, rows = [], []
    promo_code, promo_error = '', ''
    if request.method == 'POST':
        items, item_errors, rows = _parse_sale_items(request.POST)
        promo_code = request.POST.get('promo_code', '').strip()
        subtotal = sum((item['unit_price'] * item['quantity'] for item in items), Decimal('0.00'))
        promo = None
        if promo_code and items:
            promo, promo_error = _in_store_promo(promo_code, subtotal, store.currency)
        if not item_errors and not promo_error:
            sale, short = _save_in_store_sale(request, store, items, subtotal, promo)
            if sale:
                messages.success(request, f'Sale {sale.number} was saved and its items were taken out of stock.')
                if short:
                    messages.warning(request, _stock_warning(short))
                return redirect('manager:order', number=sale.number)
            promo_error = 'This promo code has just been fully used. Remove it or try another one.'

    return render(request, 'manager/in_store_form.html', {
        'section': 'in_store',
        'item_errors': item_errors,
        'promo_code': promo_code,
        'promo_error': promo_error,
        'rows': rows,
        'products': Product.objects.order_by('name').only('pk', 'name', 'code'),
    })


@staff_required
def category_list(request):
    categories = Category.objects.annotate(product_count=Count('products', distinct=True))
    return render(request, 'manager/categories.html', {
        'section': 'categories',
        'categories': _category_tree(categories),
    })


@staff_required
def category_form(request, pk=None):
    category = get_object_or_404(Category, pk=pk) if pk else Category()
    initial = {}
    if not pk and request.GET.get('parent', '').isdigit():
        initial['parent'] = request.GET['parent']
    form = CategoryForm(request.POST or None, request.FILES or None, instance=category, initial=initial, tree=_category_tree())
    if request.method == 'POST' and form.is_valid():
        category = form.save()
        messages.success(request, f'Category “{category.name}” was saved.')
        return redirect('manager:categories')
    return render(request, 'manager/category_form.html', {
        'section': 'categories', 'form': form, 'category': category if pk else None,
    })


@staff_required
@require_POST
def category_toggle(request, pk):
    return _toggle(request, get_object_or_404(Category, pk=pk), {'is_active'}, reverse('manager:categories'))


@staff_required
@require_POST
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if category.children.exists():
        messages.error(request, f'“{category.name}” has sub-categories. Move or delete them first.')
        return redirect('manager:category_edit', pk=pk)
    category.delete()
    messages.success(request, f'Category “{category.name}” was deleted. Its products are still in your shop.')
    return redirect('manager:categories')


# --- Promo codes --------------------------------------------------------------

@staff_required
def promo_list(request):
    return render(request, 'manager/promos.html', {
        'section': 'promos', 'promos': PromoCode.objects.all(), 'now': timezone.now(),
    })


@staff_required
def promo_form(request, pk=None):
    promo = get_object_or_404(PromoCode, pk=pk) if pk else None
    form = PromoCodeForm(request.POST or None, instance=promo)
    if request.method == 'POST' and form.is_valid():
        promo = form.save()
        messages.success(request, f'Promo code {promo.code} was saved.')
        return redirect('manager:promos')
    return render(request, 'manager/promo_form.html', {'section': 'promos', 'form': form, 'promo': promo})


@staff_required
@require_POST
def promo_toggle(request, pk):
    return _toggle(request, get_object_or_404(PromoCode, pk=pk), {'is_active'}, reverse('manager:promos'))


@staff_required
@require_POST
def promo_delete(request, pk):
    promo = get_object_or_404(PromoCode, pk=pk)
    promo.delete()
    messages.success(request, f'Promo code {promo.code} was deleted.')
    return redirect('manager:promos')


# --- Customers ----------------------------------------------------------------

def _with_order_stats(users):
    return users.annotate(
        order_count=Count('orders', distinct=True),
        spent=Sum('orders__total', filter=~Q(orders__status=Order.Status.CANCELLED)),
        last_order=Max('orders__created_at'),
    )


@staff_required
def customer_list(request):
    query = request.GET.get('q', '').strip()
    customers = User.objects.filter(is_staff=False)
    if query:
        customers = customers.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query)
            | Q(addresses__phone__icontains=query)
        ).distinct()
    return render(request, 'manager/customers.html', {
        'section': 'customers',
        'query': query,
        'page_obj': Paginator(_with_order_stats(customers).order_by('-date_joined'), 25).get_page(request.GET.get('page')),
    })


@staff_required
def customer_detail(request, pk):
    customer = get_object_or_404(_with_order_stats(User.objects.all()), pk=pk)
    return render(request, 'manager/customer_detail.html', {
        'section': 'customers',
        'customer': customer,
        'orders': customer.orders.prefetch_related('items'),
        'addresses': customer.addresses.all(),
    })


# --- Sizes & colors -----------------------------------------------------------

@staff_required
def options(request):
    if request.method == 'POST':
        action = request.POST.get('action', '')
        kind, _, verb = action.partition('_')
        model, form_class = {'size': (Size, SizeForm), 'color': (Color, ColorForm)}.get(verb, (None, None))
        if model is None:
            return HttpResponseBadRequest('Unknown action')
        label = model._meta.verbose_name
        if kind == 'delete':
            obj = get_object_or_404(model, pk=request.POST.get('pk'))
            obj.delete()
            messages.success(request, f'{label.capitalize()} “{obj.name}” was deleted.')
        elif kind in ('add', 'update'):
            instance = get_object_or_404(model, pk=request.POST.get('pk')) if kind == 'update' else None
            form = form_class(request.POST, instance=instance)
            if form.is_valid():
                obj = form.save()
                messages.success(request, f'{label.capitalize()} “{obj.name}” was saved.')
            else:
                messages.error(request, _first_error(form))
        return redirect(reverse('manager:options') + f'#{verb}s')

    return render(request, 'manager/options.html', {
        'section': 'options',
        'sizes': Size.objects.annotate(product_count=Count('products')),
        'colors': Color.objects.annotate(product_count=Count('products')),
        'size_form': SizeForm(),
        'color_form': ColorForm(initial={'hex_code': '#7A0F1F'}),
    })


# --- Store settings -----------------------------------------------------------

@staff_required
def analytics_view(request):
    today = timezone.localdate()
    period = stats.resolve_period(request.GET, today)
    channel = request.GET.get('channel', 'all')
    if channel not in dict(stats.CHANNELS):
        channel = 'all'
    return render(request, 'manager/analytics.html', {
        'section': 'analytics',
        'today': today,
        'period': period,
        'previous': period.previous(),
        'channel': channel,
        'presets': stats.PRESETS,
        'channels': stats.CHANNELS,
        'r': stats.build_report(period, channel, StoreSettings.load().currency),
    })


@staff_required
def analytics_export(request):
    """Every order and in-store sale in the chosen period, as a spreadsheet file."""
    period = stats.resolve_period(request.GET, timezone.localdate())
    start, end = period.bounds()
    orders = Order.objects.filter(created_at__gte=start, created_at__lt=end).order_by('created_at').prefetch_related('items')
    channel = request.GET.get('channel', 'all')
    if channel in ('online', 'in_store'):
        orders = orders.filter(channel=channel)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = (
        f'attachment; filename="teffaha-orders-{period.start:%Y-%m-%d}-to-{period.end:%Y-%m-%d}.csv"'
    )
    response.write('﻿')  # lets Excel open the file as UTF-8
    writer = csv.writer(response)
    writer.writerow(stats.EXPORT_HEADER)
    for order in orders:
        writer.writerow(stats.export_row(order))
    return response


@staff_required
def store_settings(request):
    form = StoreSettingsForm(request.POST or None, request.FILES or None, instance=StoreSettings.load())
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Store settings were saved.')
        return redirect('manager:settings')
    return render(request, 'manager/settings.html', {'section': 'settings', 'form': form})
