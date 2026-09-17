"""Numbers and chart shapes for the store manager's Analytics page.

Everything is computed in Python from the orders in the chosen period. A small
shop has few enough orders that this stays fast, and it keeps the maths easy to
follow. Cancelled orders never count as sales; they're reported separately.
"""
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from store.models import Category, Color, Order, Size
from store.money import format_money

ZERO = Decimal('0')
SERIES = [('online', 'Online'), ('in_store', 'In store')]
PRESETS = [
    ('7d', 'Last 7 days'),
    ('30d', 'Last 30 days'),
    ('90d', 'Last 90 days'),
    ('month', 'This month'),
    ('last_month', 'Last month'),
    ('year', 'This year'),
    ('custom', 'Custom dates'),
]
CHANNELS = [('all', 'All sales'), ('online', 'Online only'), ('in_store', 'In store only')]
WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
HEAT_LEVELS = 6
MAX_CUSTOM_DAYS = 3 * 366


# --- Periods ----------------------------------------------------------------

@dataclass
class Period:
    key: str
    start: date  # inclusive
    end: date    # inclusive

    @property
    def days(self):
        return (self.end - self.start).days + 1

    @property
    def compare_label(self):
        return 'previous day' if self.days == 1 else f'previous {self.days} days'

    def previous(self):
        end = self.start - timedelta(days=1)
        return Period('previous', end - timedelta(days=self.days - 1), end)

    def bounds(self):
        """Aware datetimes [start, end) in the shop's time zone."""
        tz = timezone.get_current_timezone()
        return (
            datetime.combine(self.start, time.min, tzinfo=tz),
            datetime.combine(self.end + timedelta(days=1), time.min, tzinfo=tz),
        )


def _parse_date(value):
    try:
        return date.fromisoformat(value or '')
    except ValueError:
        return None


def resolve_period(params, today):
    """The period chosen in the filter row (defaults to the last 30 days)."""
    key = params.get('period', '30d')
    if key == 'custom':
        start, end = _parse_date(params.get('from')), _parse_date(params.get('to'))
        if start and end:
            start, end = min(start, end), max(start, end)
            end = min(end, today)
            start = max(min(start, end), end - timedelta(days=MAX_CUSTOM_DAYS - 1))
            return Period('custom', start, end)
        key = '30d'
    if key in ('7d', '30d', '90d'):
        return Period(key, today - timedelta(days=int(key[:-1]) - 1), today)
    if key == 'month':
        return Period(key, today.replace(day=1), today)
    if key == 'last_month':
        end = today.replace(day=1) - timedelta(days=1)
        return Period(key, end.replace(day=1), end)
    if key == 'year':
        return Period(key, today.replace(month=1, day=1), today)
    return Period('30d', today - timedelta(days=29), today)


# --- Formatting helpers -------------------------------------------------------

def _pct(part, whole):
    return float(part) / float(whole) * 100 if whole else 0.0


def _css(number):
    """A number for inline styles, always with a dot as the decimal mark."""
    return f'{number:.2f}'


def _short(value):
    value = float(value)
    for limit, suffix in ((1_000_000, 'M'), (1_000, 'K')):
        if abs(value) >= limit:
            return f'{value / limit:.1f}'.rstrip('0').rstrip('.') + suffix
    return f'{value:,.0f}'


def money(amount, currency):
    """$1,284.50 — or $12.9K once amounts reach five figures."""
    amount = Decimal(amount or 0)
    return f'{currency}{_short(amount)}' if abs(amount) >= 10_000 else format_money(amount, currency)


def _count(value, noun=''):
    text = f'{value:,}'
    return f'{text} {noun}{"" if value == 1 else "s"}' if noun else text


def _axis_label(value, currency=''):
    if value >= 1000:
        text = _short(value)
    else:
        text = f'{value:.0f}' if float(value).is_integer() else f'{value:.1f}'
    return f'{currency}{text}'


def nice_axis(max_value, integer=False, steps=4):
    """A rounded top value and evenly spaced ticks: 47 -> (60, [0, 20, 40, 60])."""
    if max_value <= 0:
        return 1, [0, 1]
    raw = max_value / steps
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    if integer:
        step = max(1, math.ceil(step))
    top = step * math.ceil(max_value / step - 1e-9)
    return top, [step * i for i in range(int(round(top / step)) + 1)]


def _tip(title, rows, total=''):
    return json.dumps({'title': title, 'rows': rows, 'total': total})


# --- Time buckets -------------------------------------------------------------

def _bucket_unit(period):
    return 'day' if period.days <= 31 else 'week' if period.days <= 182 else 'month'


def _bucket_start(day, unit):
    if unit == 'week':
        return day - timedelta(days=day.weekday())
    if unit == 'month':
        return day.replace(day=1)
    return day


def _iter_buckets(period, unit):
    current = _bucket_start(period.start, unit)
    while current <= period.end:
        yield current
        if unit == 'day':
            current += timedelta(days=1)
        elif unit == 'week':
            current += timedelta(days=7)
        else:
            current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)


def _bucket_title(day, unit):
    if unit == 'week':
        return f'Week of {day.day} {day:%b %Y}'
    if unit == 'month':
        return f'{day:%B %Y}'
    return f'{day:%a} {day.day} {day:%b %Y}'


def _bucket_short(day, unit):
    return f'{day:%b}' if unit == 'month' else f'{day.day} {day:%b}'


# --- The report ----------------------------------------------------------------

def build_report(period, channel, currency):
    orders_qs = Order.objects.all()
    if channel in ('online', 'in_store'):
        orders_qs = orders_qs.filter(channel=channel)

    start, end = period.bounds()
    orders = list(
        orders_qs.filter(created_at__gte=start, created_at__lt=end).order_by('created_at')
        .select_related('user').prefetch_related('items__product__categories', 'items__product__images__color')
    )
    previous = period.previous()
    prev_start, prev_end = previous.bounds()
    previous_orders = list(
        orders_qs.filter(created_at__gte=prev_start, created_at__lt=prev_end).prefetch_related('items')
    )

    sold = [order for order in orders if order.status != Order.Status.CANCELLED]
    summary = _summary(orders)
    series_keys = [key for key, _ in SERIES if channel in ('all', key)]
    category_names = dict(Category.objects.values_list('path', 'name'))

    return {
        'has_sales': bool(sold),
        'summary': summary,
        'kpis': _kpis(summary, _summary(previous_orders), previous, currency),
        'series': [(key, label) for key, label in SERIES if key in series_keys],
        'charts': _time_charts(period, sold, series_keys, currency),
        'split': _channel_split(sold, currency) if channel == 'all' else None,
        'statuses': _statuses(orders) if channel != 'in_store' else None,
        'top_products': _top_products(sold, currency),
        'categories': _categories(sold, currency, category_names),
        'sizes': _sizes(sold),
        'colors': _colors(sold),
        'cities': _cities(sold, currency) if channel != 'in_store' else None,
        'heatmap': _heatmap(sold),
        'promos': _promos(sold, currency),
        'customers': _customers(period, sold, channel),
    }


def _summary(orders):
    sold = [order for order in orders if order.status != Order.Status.CANCELLED]
    revenue = sum((order.total for order in sold), ZERO)
    return {
        'revenue': revenue,
        'orders': len(sold),
        'average': (revenue / len(sold)).quantize(Decimal('0.01')) if sold else ZERO,
        'items': sum(item.quantity for order in sold for item in order.items.all()),
        'discounts': sum((order.discount for order in sold), ZERO),
        'cancelled': len(orders) - len(sold),
    }


def _change(current, previous, previous_period, good):
    """Wording and tone for a KPI's change. `good` is 'up', 'down' or 'neutral'."""
    compare = previous_period.compare_label
    if not previous:
        return {'arrow': '', 'tone': 'neutral',
                'text': f'Nothing in the {compare}' if current else f'Same as the {compare}'}
    change = round((float(current) - float(previous)) / float(previous) * 100)
    if change == 0:
        return {'arrow': '', 'tone': 'neutral', 'text': f'Same as the {compare}'}
    up = change > 0
    tone = 'neutral' if good == 'neutral' else ('good' if up == (good == 'up') else 'bad')
    return {
        'arrow': '▲' if up else '▼',
        'tone': tone,
        'text': f'{"Up" if up else "Down"} {abs(change)}% vs. the {compare}',
    }


def _kpis(current, previous, previous_period, currency):
    rows = [
        ('Revenue', money(current['revenue'], currency), 'revenue', 'up', 'Not counting cancelled orders'),
        ('Orders & sales', _count(current['orders']), 'orders', 'up', ''),
        ('Average order value', money(current['average'], currency), 'average', 'up', ''),
        ('Items sold', _count(current['items']), 'items', 'up', ''),
        ('Discounts given', money(current['discounts'], currency), 'discounts', 'neutral', 'From promo codes'),
        ('Cancelled orders', _count(current['cancelled']), 'cancelled', 'down', ''),
    ]
    return [
        {'label': label, 'value': value, 'note': note,
         'delta': _change(current[key], previous[key], previous_period, good)}
        for label, value, key, good, note in rows
    ]


def _time_charts(period, sold, series_keys, currency):
    unit = _bucket_unit(period)
    buckets = list(_iter_buckets(period, unit))
    position = {start: index for index, start in enumerate(buckets)}
    revenue = {key: [ZERO] * len(buckets) for key in series_keys}
    counts = {key: [0] * len(buckets) for key in series_keys}
    for order in sold:
        index = position.get(_bucket_start(timezone.localtime(order.created_at).date(), unit))
        if index is None or order.channel not in revenue:
            continue
        revenue[order.channel][index] += order.total
        counts[order.channel][index] += 1

    labels = dict(SERIES)
    several = len(series_keys) > 1
    head = [{'day': 'Day', 'week': 'Week', 'month': 'Month'}[unit]]
    head += [f'{labels[k]} revenue' for k in series_keys] + (['Total revenue'] if several else [])
    head += [f'{labels[k]} orders' for k in series_keys] + (['Total orders'] if several else [])
    table = []
    for i, start in enumerate(buckets):
        money_cells = [money(revenue[k][i], currency) for k in series_keys]
        count_cells = [_count(counts[k][i]) for k in series_keys]
        if several:
            money_cells.append(money(sum(revenue[k][i] for k in series_keys), currency))
            count_cells.append(_count(sum(counts[k][i] for k in series_keys)))
        table.append({'title': _bucket_title(start, unit), 'cells': money_cells + count_cells})

    return {
        'unit': unit,
        'subtitle': {'day': 'Per day', 'week': 'Per week (weeks start on Monday)', 'month': 'Per month'}[unit],
        'metrics': [
            {'key': 'revenue', 'label': 'Revenue', 'chart': _column_chart(
                buckets, unit, revenue, labels, lambda v: money(v, currency),
                lambda v: _axis_label(v, currency), integer=False)},
            {'key': 'orders', 'label': 'Orders', 'chart': _column_chart(
                buckets, unit, counts, labels, _count, _axis_label, integer=True)},
        ],
        'table_head': head,
        'table': table,
    }


def _column_chart(buckets, unit, values, labels, fmt, axis_fmt, integer):
    count = len(buckets)
    totals = [sum(series[i] for series in values.values()) for i in range(count)]
    top, ticks = nice_axis(float(max(totals, default=0)), integer=integer)
    label_every = max(1, math.ceil(count / 10))
    columns = []
    for i, start in enumerate(buckets):
        title = _bucket_title(start, unit)
        rows = [{'key': key, 'label': labels[key], 'value': fmt(series[i])} for key, series in values.items()]
        total = fmt(totals[i]) if len(values) > 1 else ''
        columns.append({
            'label': _bucket_short(start, unit) if i % label_every == 0 else '',
            'height': _css(_pct(totals[i], top)),
            'segments': [
                {'key': key, 'weight': _css(float(series[i]))} for key, series in values.items() if series[i]
            ],
            'tip': _tip(title, rows, total),
            'aria': f'{title}: ' + ', '.join(f"{row['label']} {row['value']}" for row in rows),
        })
    return {
        'ticks': [{'label': axis_fmt(tick), 'bottom': _css(_pct(tick, top))} for tick in ticks],
        'columns': columns,
    }


def _bars(pairs, fmt, total=None):
    """[(label, value, extra)] -> rows whose bar width is relative to the largest value."""
    top = max((value for _, value, _ in pairs), default=0)
    total = sum(value for _, value, _ in pairs) if total is None else total
    rows = []
    for label, value, extra in pairs:
        share = round(_pct(value, total))
        rows.append({
            'label': label, 'value': fmt(value), 'width': _css(_pct(value, top)), 'share': share,
            'tip': _tip(label, [{'label': f'{share}% of the total', 'value': fmt(value)}]),
            **extra,
        })
    return rows


def _channel_split(sold, currency):
    total = sum((order.total for order in sold), ZERO)
    parts = []
    for key, label in SERIES:
        orders = [order for order in sold if order.channel == key]
        revenue = sum((order.total for order in orders), ZERO)
        parts.append({
            'key': key, 'label': label, 'revenue': money(revenue, currency), 'orders': len(orders),
            'share': round(_pct(revenue, total)), 'weight': _css(float(revenue)), 'has_revenue': revenue > 0,
        })
    return {'parts': parts, 'has_revenue': total > 0}


def _statuses(orders):
    online = [order for order in orders if order.channel == Order.Channel.ONLINE]
    if not online:
        return []
    counts = {value: 0 for value, _ in Order.Status.choices}
    for order in online:
        counts[order.status] += 1
    return _bars(
        [(label, counts[value], {'key': value}) for value, label in Order.Status.choices],
        lambda v: _count(v),
    )


def _top_products(sold, currency, limit=10):
    stats, total = {}, ZERO
    for order in sold:
        for item in order.items.all():
            key = item.product_id or f'deleted:{item.product_name}'
            row = stats.setdefault(key, {
                'name': item.product_name,
                'code': item.product_code or (item.product.code if item.product else ''),
                'product': item.product, 'units': 0, 'revenue': ZERO,
            })
            row['units'] += item.quantity
            row['revenue'] += item.line_total
            total += item.line_total
    rows = sorted(stats.values(), key=lambda r: (-r['revenue'], -r['units'], r['name']))[:limit]
    top_share = _pct(rows[0]['revenue'], total) if rows else 0
    for row in rows:
        product = row.pop('product')
        image = product.main_image if product else None
        share = _pct(row['revenue'], total)
        row.update(
            product_id=product.pk if product else None,
            image=image.image.url if image else '',
            revenue_display=money(row['revenue'], currency),
            share=round(share),
            width=_css(_pct(share, top_share)),
        )
    return rows


def _category_label(product, names):
    """"Women › Tops" for a product in Women › Tops › T-Shirts."""
    if product is None:
        return 'Deleted products'
    categories = list(product.categories.all())
    if not categories:
        return 'No category'
    parts = max(categories, key=lambda c: c.path.count('/')).path.split('/')
    return ' › '.join(names.get('/'.join(parts[:i + 1]), parts[i]) for i in range(min(2, len(parts))))


def _categories(sold, currency, names, limit=8):
    revenue = defaultdict(lambda: ZERO)
    for order in sold:
        for item in order.items.all():
            revenue[_category_label(item.product, names)] += item.line_total
    pairs = sorted(revenue.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(pairs) > limit:
        pairs = pairs[:limit - 1] + [('Other', sum((value for _, value in pairs[limit - 1:]), ZERO))]
    return _bars([(label, value, {}) for label, value in pairs], lambda v: money(v, currency))


def _sizes(sold):
    units = defaultdict(int)
    for order in sold:
        for item in order.items.all():
            units[item.size or 'No size'] += item.quantity
    size_order = {name: i for i, name in enumerate(Size.objects.values_list('name', flat=True))}
    pairs = sorted(units.items(), key=lambda kv: (kv[0] == 'No size', size_order.get(kv[0], len(size_order)), kv[0]))
    return _bars([(name, count, {}) for name, count in pairs], lambda v: _count(v))


def _colors(sold, limit=10):
    units = defaultdict(int)
    for order in sold:
        for item in order.items.all():
            if item.color:
                units[item.color] += item.quantity
    hexes = dict(Color.objects.values_list('name', 'hex_code'))
    pairs = sorted(units.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return _bars([(name, count, {'hex': hexes.get(name, '#cccccc')}) for name, count in pairs], lambda v: _count(v))


def _cities(sold, currency, limit=8):
    stats = defaultdict(lambda: [0, ZERO])
    for order in sold:
        city = order.city.strip()
        if order.channel == Order.Channel.ONLINE and city:
            stats[city.title()][0] += 1
            stats[city.title()][1] += order.total
    pairs = sorted(stats.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))[:limit]
    rows = _bars([(city, count, {}) for city, (count, _) in pairs], lambda v: _count(v, 'order'))
    for row, (city, (count, revenue)) in zip(rows, pairs):
        row['tip'] = _tip(city, [
            {'label': f'{row["share"]}% of online orders', 'value': _count(count, 'order')},
            {'label': 'revenue', 'value': money(revenue, currency)},
        ])
    return rows


def _hour(hour, short=False):
    hour %= 24
    suffix = ('a' if hour < 12 else 'p') if short else (' am' if hour < 12 else ' pm')
    return f'{hour % 12 or 12}{suffix}'


def _heatmap(sold):
    grid = [[0] * 24 for _ in WEEKDAYS]
    for order in sold:
        local = timezone.localtime(order.created_at)
        grid[local.weekday()][local.hour] += 1
    top = max(count for row in grid for count in row)
    rows = []
    for day, name in enumerate(WEEKDAYS):
        cells = []
        for hour in range(24):
            count = grid[day][hour]
            cells.append({
                'count': count,
                'level': math.ceil(count / top * HEAT_LEVELS) if count else 0,
                'tip': _tip(f'{name}, {_hour(hour)}–{_hour(hour + 1)}', [{'label': 'orders & sales', 'value': _count(count)}]),
            })
        rows.append({'day': name[:3], 'name': name, 'cells': cells})
    # Only name a busiest time when one slot clearly beats every other one.
    busiest = ''
    peaks = [(d, h) for d in range(7) for h in range(24) if top and grid[d][h] == top]
    if len(peaks) == 1:
        day, hour = peaks[0]
        busiest = f'{WEEKDAYS[day]}s, {_hour(hour)}–{_hour(hour + 1)}'
    return {
        'has_data': bool(top),
        'rows': rows,
        'busiest': busiest,
        'hours': [_hour(h, short=True) if h % 3 == 0 else '' for h in range(24)],
        'hour_names': [_hour(h, short=True) for h in range(24)],
        'levels': list(range(1, HEAT_LEVELS + 1)),
    }


def _promos(sold, currency):
    stats = {}
    for order in sold:
        if order.promo_code:
            row = stats.setdefault(order.promo_code, {'code': order.promo_code, 'orders': 0, 'discount': ZERO, 'revenue': ZERO})
            row['orders'] += 1
            row['discount'] += order.discount
            row['revenue'] += order.total
    rows = sorted(stats.values(), key=lambda r: (-r['orders'], r['code']))
    for row in rows:
        row['discount_display'] = money(row['discount'], currency)
        row['revenue_display'] = money(row['revenue'], currency)
    return rows


def _phone_key(phone):
    """Compare phone numbers by their last 8 digits, so "+961 70 123 456" and
    "70123456" count as the same customer."""
    return ''.join(ch for ch in phone if ch.isdigit())[-8:]


def _customers(period, sold, channel):
    start, end = period.bounds()
    online = [order for order in sold if order.channel == Order.Channel.ONLINE]
    with_account = sum(1 for order in online if order.user_id)
    lifetime = defaultdict(int)
    for phone in Order.objects.exclude(status=Order.Status.CANCELLED).exclude(phone='').values_list('phone', flat=True):
        lifetime[_phone_key(phone)] += 1
    buyers = {_phone_key(order.phone) for order in sold} - {''}
    account_share = round(_pct(with_account, len(online)))
    return {
        'new_accounts': get_user_model().objects.filter(
            is_staff=False, date_joined__gte=start, date_joined__lt=end
        ).count(),
        'show_accounts': channel != 'in_store' and bool(online),
        'account_share': account_share,
        'guest_share': 100 - account_share,
        'buyers': len(buyers),
        'repeat': sum(1 for key in buyers if lifetime[key] >= 2),
    }


# --- CSV export ----------------------------------------------------------------

EXPORT_HEADER = [
    'Order', 'Date', 'Time', 'Sold', 'Status', 'Customer', 'Phone', 'City', 'Address', 'Items',
    'Item count', 'Subtotal', 'Promo code', 'Discount', 'Delivery', 'Total', 'Currency', 'Payment',
]


def _csv_safe(value):
    """Stop spreadsheet apps from running text such as =SUM(...) as a formula."""
    if isinstance(value, str) and value[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value


def _item_text(item):
    details = ', '.join(part for part in (
        item.product_code and f'ID {item.product_code}', item.color, item.size and f'size {item.size}',
    ) if part)
    return f'{item.quantity} x {item.product_name}' + (f' ({details})' if details else '')


def export_row(order):
    local = timezone.localtime(order.created_at)
    return [_csv_safe(value) for value in [
        order.number, local.strftime('%Y-%m-%d'), local.strftime('%H:%M'),
        order.get_channel_display(), order.get_status_display(),
        order.full_name, order.phone, order.city, order.address,
        '; '.join(_item_text(item) for item in order.items.all()), order.item_count,
        order.subtotal, order.promo_code, order.discount, order.delivery_fee, order.total,
        order.currency, order.payment_method,
    ]]
