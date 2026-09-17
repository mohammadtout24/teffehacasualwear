import io
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from store.models import (
    Category, Color, Order, OrderItem, Product, ProductVariant, PromoCode, Size, StoreSettings,
)

User = get_user_model()
MEDIA = tempfile.mkdtemp()
PASSWORD = 'Soft-Linen-42'


def photo(name):
    buffer = io.BytesIO()
    Image.new('RGB', (30, 40), '#7a0f1f').save(buffer, 'PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


@override_settings(MEDIA_ROOT=MEDIA, RESEND_API_KEY='')
class ManagerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('setup_categories', stdout=io.StringIO())
        cls.tees = Category.objects.get(path='women/tops/t-shirts')
        cls.women = Category.objects.get(path='women')
        cls.size_m = Size.objects.get(name='M')
        cls.black = Color.objects.create(name='Black', hex_code='#000000')
        cls.product = Product.objects.create(name='Plain Tee', price=Decimal('20.00'))
        cls.product.categories.add(cls.tees)
        cls.staff = User.objects.create_user('boss', 'boss@teffaha.test', PASSWORD, is_staff=True, first_name='Nour')
        cls.customer = User.objects.create_user('sara@example.com', 'sara@example.com', PASSWORD, first_name='Sara')
        cls.order = Order.objects.create(
            user=cls.customer, full_name='Sara Haddad', phone='+961 70 123 456', city='Beirut',
            address='Hamra Street', subtotal=20, delivery_fee=4, total=24,
        )
        OrderItem.objects.create(order=cls.order, product=cls.product, product_name='Plain Tee',
                                 size='M', unit_price=20, quantity=1)
        StoreSettings.load()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.client.force_login(self.staff)

    def test_only_admin_accounts_get_in(self):
        self.client.logout()
        dashboard, login = reverse('manager:dashboard'), reverse('manager:login')
        self.assertRedirects(self.client.get(dashboard), f'{login}?next=/manage/')

        self.client.force_login(self.customer)
        self.assertRedirects(self.client.get(dashboard), f'{login}?next=/manage/', fetch_redirect_response=False)
        self.assertContains(self.client.get(login), 'isn’t an admin account')

    def test_login_with_email_or_username(self):
        self.client.logout()
        login, dashboard = reverse('manager:login'), reverse('manager:dashboard')
        self.assertRedirects(self.client.post(login, {'username': 'BOSS@teffaha.test', 'password': PASSWORD}), dashboard)
        self.client.logout()
        self.assertRedirects(self.client.post(login, {'username': 'boss', 'password': PASSWORD}), dashboard)
        self.client.logout()

        response = self.client.post(login, {'username': 'sara@example.com', 'password': PASSWORD})
        self.assertContains(response, 'isn’t an admin account')
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(self.client.post(login, {'username': 'boss', 'password': 'wrong'}), 'don’t match')

    def test_every_page_renders(self):
        promo = PromoCode.objects.create(code='WELCOME10', kind='percent', value=10)
        urls = [
            reverse('manager:dashboard'),
            reverse('manager:orders'), reverse('manager:orders') + '?status=new&q=sara',
            reverse('manager:order', args=[self.order.number]),
            reverse('manager:products'), reverse('manager:products') + f'?status=no_photos&category={self.women.pk}&q=tee',
            reverse('manager:product_add'), reverse('manager:product_edit', args=[self.product.pk]),
            reverse('manager:categories'), reverse('manager:category_add') + f'?parent={self.women.pk}',
            reverse('manager:category_edit', args=[self.tees.pk]),
            reverse('manager:promos'), reverse('manager:promo_add'), reverse('manager:promo_edit', args=[promo.pk]),
            reverse('manager:customers'), reverse('manager:customer', args=[self.customer.pk]),
            reverse('manager:options'), reverse('manager:settings'),
            reverse('manager:in_store'), reverse('manager:in_store') + '?q=tee', reverse('manager:in_store_new'),
            reverse('manager:products') + '?status=low_stock', reverse('manager:products') + '?status=out_of_stock',
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertContains(self.client.get(reverse('manager:dashboard')), 'New orders to confirm')

    def test_order_status_and_delete(self):
        url = reverse('manager:order_status', args=[self.order.number])
        self.client.post(url, {'status': 'confirmed'})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'confirmed')
        self.client.post(url, {'status': 'not-a-status'})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'confirmed')

        self.client.post(reverse('manager:order_delete', args=[self.order.number]))
        self.assertFalse(Order.objects.filter(pk=self.order.pk).exists())

    def test_add_product_with_photos_new_color_and_sizes(self):
        response = self.client.post(reverse('manager:product_add'), {
            'code': 'TW-2001', 'name': 'Linen Shirt', 'price': '35', 'compare_at_price': '45', 'description': 'Airy.',
            'categories': [self.tees.pk], 'sizes': [self.size_m.pk], 'new_sizes': 'XL, 2XL',
            'new_color_name': 'Olive', 'new_color_hex': '#6b7048', 'in_stock': 'on', 'is_active': 'on',
            'new_images': [photo('front.png'), photo('back.png')],
        })
        product = Product.objects.get(name='Linen Shirt')
        self.assertRedirects(response, reverse('manager:product_edit', args=[product.pk]))
        self.assertEqual(product.code, 'TW-2001')
        self.assertEqual(set(product.sizes.values_list('name', flat=True)), {'M', 'XL', '2XL'})
        self.assertEqual(list(product.colors.values_list('name', flat=True)), ['Olive'])
        first, second = product.images.all()
        self.assertTrue(product.on_sale)

        # Make the second photo the main one and remove the first.
        self.client.post(reverse('manager:product_edit', args=[product.pk]), {
            'code': 'TW-2001', 'name': 'Linen Shirt', 'price': '35', 'categories': [self.tees.pk], 'is_active': 'on',
            'main_image': second.pk, f'image-{first.pk}-remove': 'on', f'image-{second.pk}-color': self.black.pk,
        })
        self.assertEqual([(i.pk, i.color, i.sort_order) for i in product.images.all()], [(second.pk, self.black, 0)])
        self.assertFalse(product.images.filter(pk=first.pk).exists())

    def test_product_form_explains_mistakes(self):
        url = reverse('manager:product_add')
        self.assertContains(self.client.post(url, {'name': 'No ID', 'price': '5'}), 'Enter the product ID')
        self.product.code = 'TW-1'
        self.product.save()
        response = self.client.post(url, {'code': 'tw-1', 'name': 'Oops', 'price': '30', 'compare_at_price': '20'})
        self.assertContains(response, 'Another product already uses this ID')
        self.assertContains(response, 'Tick at least one category')
        self.assertContains(response, 'original price must be higher')
        self.assertFalse(Product.objects.filter(name='Oops').exists())

    def test_quick_toggles(self):
        url = reverse('manager:product_toggle', args=[self.product.pk])
        response = self.client.post(url, {'field': 'in_stock'}, headers={'x-requested-with': 'fetch'})
        self.assertEqual(response.json(), {'ok': True, 'value': False})
        self.assertEqual(self.client.post(url, {'field': 'price'}).status_code, 400)

    def test_categories(self):
        url = reverse('manager:category_add')
        self.client.post(url, {'name': 'Skirts', 'parent': self.women.pk, 'sort_order': 9, 'is_active': 'on'})
        self.assertTrue(Category.objects.filter(path='women/skirts').exists())
        response = self.client.post(url, {'name': 'Skirts', 'parent': self.women.pk, 'sort_order': 9})
        self.assertContains(response, 'already a category')

        # A category with sub-categories can't be deleted by accident.
        self.client.post(reverse('manager:category_delete', args=[self.women.pk]))
        self.assertTrue(Category.objects.filter(pk=self.women.pk).exists())

    def test_promo_codes(self):
        url = reverse('manager:promo_add')
        self.client.post(url, {'code': 'summer', 'kind': 'percent', 'value': '15', 'is_active': 'on'})
        self.assertEqual(PromoCode.objects.get(code='SUMMER').value, Decimal('15'))
        self.client.post(url, {'code': 'freeship', 'kind': 'free_delivery', 'value': '', 'is_active': 'on'})
        self.assertTrue(PromoCode.objects.filter(code='FREESHIP', kind='free_delivery').exists())
        self.assertContains(self.client.post(url, {'code': 'bad', 'kind': 'percent', 'value': '150'}), 'between 1 and 100')

    def test_store_settings_sizes_and_colors(self):
        self.client.post(reverse('manager:settings'), {
            'currency': '$', 'delivery_fee': '5', 'free_delivery_over': '', 'delivery_time': '1–2 days',
            'whatsapp': '+961 70 123 456', 'announcement': 'Hello', 'hero_title': 'Hi',
        })
        store = StoreSettings.load()
        self.assertEqual((store.delivery_fee, store.free_delivery_over, store.whatsapp),
                         (Decimal('5.00'), None, '96170123456'))

        url = reverse('manager:options')
        self.client.post(url, {'action': 'add_color', 'name': 'Olive', 'hex_code': '#6b7048'})
        self.assertEqual(Color.objects.get(name='Olive').hex_code, '#6B7048')
        self.client.post(url, {'action': 'add_size', 'name': '3XL', 'sort_order': ''})
        size = Size.objects.get(name='3XL')
        self.assertGreater(size.sort_order, self.size_m.sort_order)
        self.client.post(url, {'action': 'delete_size', 'pk': size.pk})
        self.assertFalse(Size.objects.filter(pk=size.pk).exists())

    def test_product_lookup_by_product_id(self):
        self.product.code = 'TEE-01'
        self.product.save()
        self.product.sizes.add(self.size_m)
        ProductVariant.objects.create(product=self.product, size=self.size_m, quantity=6)
        url = reverse('manager:product_lookup')
        data = self.client.get(url, {'id': 'tee-01'}).json()
        self.assertEqual((data['id'], data['name'], data['price'], data['sizes']), ('TEE-01', 'Plain Tee', '20.00', ['M']))
        self.assertEqual((data['image'], data['photos'], data['stock']), ('', {}, {'M|': 6}))
        # A product without an ID can still be found by its number.
        jacket = Product.objects.create(name='Denim Jacket', price=10)
        self.assertEqual(self.client.get(url, {'id': f'#{jacket.pk}'}).json()['id'], f'#{jacket.pk}')
        self.assertEqual(self.client.get(url, {'id': 'NOPE-1'}).status_code, 404)

    def test_record_in_store_sale(self):
        self.product.code = 'TW-7'
        self.product.save()
        jacket = Product.objects.create(name='Denim Jacket', price=Decimal('42.00'))
        jacket.colors.add(self.black)
        tee_stock = ProductVariant.objects.create(product=self.product, quantity=5)
        jacket_stock = ProductVariant.objects.create(product=jacket, color=self.black, quantity=0)
        response = self.client.post(reverse('manager:in_store_new'), {
            'item_product': ['tw-7', f'#{jacket.pk}', ''],
            'item_size': ['', '', ''], 'item_color': ['', 'Black', ''],
            'item_qty': ['2', '1', '1'], 'item_price': ['', '38', ''],
        })
        sale = Order.objects.get(channel='in_store')
        self.assertRedirects(response, reverse('manager:order', args=[sale.number]))
        self.assertEqual(
            (sale.channel, sale.status, sale.payment_method, sale.total, sale.recorded_by),
            ('in_store', 'delivered', 'Paid in store', Decimal('78.00'), self.staff),
        )
        self.assertEqual(
            [(i.product_name, i.product_code, i.color, i.quantity, i.unit_price) for i in sale.items.order_by('pk')],
            [('Plain Tee', 'TW-7', '', 2, Decimal('20.00')), ('Denim Jacket', '', 'Black', 1, Decimal('38.00'))],
        )
        tee_stock.refresh_from_db()
        jacket_stock.refresh_from_db()
        self.assertEqual((tee_stock.quantity, jacket_stock.quantity), (3, 0))  # never below zero
        # Listed under in-store sales, not among the online orders to handle.
        self.assertNotContains(self.client.get(reverse('manager:orders')), sale.number)
        self.assertContains(self.client.get(reverse('manager:in_store')), 'Denim Jacket')
        self.assertContains(self.client.get(reverse('manager:in_store'), {'q': 'denim'}), sale.number)
        detail = self.client.get(reverse('manager:order', args=[sale.number]))
        self.assertContains(detail, 'Paid in store')
        self.assertNotContains(detail, '<h2 class="m-card__title">Customer</h2>', html=False)
        self.assertContains(self.client.get(reverse('manager:dashboard')), '1 in store')

    def test_in_store_sale_explains_mistakes(self):
        url = reverse('manager:in_store_new')
        response = self.client.post(url, {
            'item_product': ['424242'], 'item_size': [''], 'item_color': [''], 'item_qty': ['1'], 'item_price': [''],
        })
        self.assertContains(response, 'no product with ID “424242”')
        self.assertContains(self.client.post(url, {}), 'Add at least one product')
        self.assertFalse(Order.objects.filter(channel='in_store').exists())

    def sale_post(self, **extra):
        return self.client.post(reverse('manager:in_store_new'), {
            'item_product': [f'#{self.product.pk}'], 'item_size': [''], 'item_color': [''],
            'item_qty': ['2'], 'item_price': [''], **extra,
        })

    def test_in_store_sale_with_promo_code(self):
        promo = PromoCode.objects.create(code='SHOP10', kind='percent', value=10)
        response = self.sale_post(promo_code=' shop10 ')  # 2 × 20 = 40
        sale = Order.objects.get(channel='in_store')
        self.assertRedirects(response, reverse('manager:order', args=[sale.number]))
        self.assertEqual((sale.subtotal, sale.promo_code, sale.discount, sale.total),
                         (Decimal('40.00'), 'SHOP10', Decimal('4.00'), Decimal('36.00')))
        promo.refresh_from_db()
        self.assertEqual(promo.times_used, 1)
        self.assertContains(self.client.get(reverse('manager:order', args=[sale.number])), 'SHOP10')

    def test_in_store_promo_code_rules(self):
        PromoCode.objects.create(code='FREESHIP', kind='free_delivery')
        PromoCode.objects.create(code='BIG', kind='fixed', value=5, min_subtotal=100)
        self.assertContains(self.sale_post(promo_code='nope'), 'This promo code is not valid')
        self.assertContains(self.sale_post(promo_code='freeship'), 'can’t be used for in-store sales')
        self.assertContains(self.sale_post(promo_code='big'), 'minimum order')
        self.assertFalse(Order.objects.filter(channel='in_store').exists())

        check = reverse('manager:in_store_promo_check')
        data = self.client.get(check, {'code': 'big'}).json()
        self.assertEqual((data['ok'], data['code'], data['kind'], data['value'], data['min_subtotal']),
                         (True, 'BIG', 'fixed', 5.0, 100.0))
        self.assertFalse(self.client.get(check, {'code': 'freeship'}).json()['ok'])
        self.assertEqual(self.client.get(check, {'code': 'nope'}).json(),
                         {'ok': False, 'error': 'This promo code is not valid.'})

    def test_analytics_periods(self):
        from datetime import date

        from manager.analytics import nice_axis, resolve_period

        today = date(2026, 9, 14)
        week = resolve_period({'period': '7d'}, today)
        previous = week.previous()
        self.assertEqual((week.start, week.end, previous.start, previous.end),
                         (date(2026, 9, 8), date(2026, 9, 14), date(2026, 9, 1), date(2026, 9, 7)))
        last_month = resolve_period({'period': 'last_month'}, today)
        self.assertEqual((last_month.start, last_month.end), (date(2026, 8, 1), date(2026, 8, 31)))
        custom = resolve_period({'period': 'custom', 'from': '2026-09-10', 'to': '2026-09-01'}, today)
        self.assertEqual((custom.start, custom.end), (date(2026, 9, 1), date(2026, 9, 10)))
        self.assertEqual(resolve_period({'period': 'custom', 'from': 'oops'}, today).key, '30d')
        self.assertEqual(nice_axis(47), (60, [0, 20, 40, 60]))
        self.assertEqual(nice_axis(3, integer=True), (3, [0, 1, 2, 3]))

    def test_analytics_numbers(self):
        sale = Order.objects.create(
            channel='in_store', status='delivered', full_name='', phone='', city='', address='',
            subtotal=40, discount=4, promo_code='SHOP10', total=36,
        )
        OrderItem.objects.create(order=sale, product=self.product, product_name='Plain Tee', size='M',
                                 color='Black', unit_price=20, quantity=2)
        Order.objects.create(full_name='Gone', phone='70000000', city='Tyre', address='a', total=99, status='cancelled')

        url = reverse('manager:analytics')
        report = self.client.get(url).context['r']
        summary = report['summary']
        self.assertEqual((summary['revenue'], summary['orders'], summary['items'], summary['discounts'], summary['cancelled']),
                         (Decimal('60'), 2, 3, Decimal('4'), 1))  # the cancelled order isn't a sale
        self.assertEqual([(p['name'], p['units']) for p in report['top_products']], [('Plain Tee', 3)])
        self.assertEqual(report['promos'][0]['code'], 'SHOP10')
        self.assertEqual([(part['key'], part['orders']) for part in report['split']['parts']], [('online', 1), ('in_store', 1)])
        self.assertEqual([row['label'] for row in report['cities']], ['Beirut'])
        self.assertEqual(report['sizes'][0]['label'], 'M')

        online = self.client.get(url, {'channel': 'online'}).context['r']
        self.assertEqual(online['summary']['revenue'], Decimal('24'))
        self.assertIsNone(online['split'])

    def test_analytics_renders_for_every_filter(self):
        from manager.analytics import CHANNELS, PRESETS

        url = reverse('manager:analytics')
        for period, _ in PRESETS:
            for channel, _ in CHANNELS:
                self.assertEqual(self.client.get(url, {'period': period, 'channel': channel}).status_code, 200)
        today = timezone.localdate()
        long_range = {'period': 'custom', 'from': str(today - timedelta(days=300)), 'to': str(today)}
        self.assertEqual(self.client.get(url, long_range).context['r']['charts']['unit'], 'month')
        empty = {'period': 'custom', 'from': '2020-01-01', 'to': '2020-01-31'}
        self.assertContains(self.client.get(url, empty), 'No sales in this period')

    def test_analytics_csv_export(self):
        Order.objects.create(full_name='=HYPERLINK("x")', phone='70123456', city='Beirut', address='a', total=10)
        response = self.client.get(reverse('manager:analytics_export'), {'period': '7d'})
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment;', response['Content-Disposition'])
        content = response.content.decode('utf-8-sig')
        self.assertTrue(content.startswith('Order,Date,Time'))
        self.assertIn(self.order.number, content)
        self.assertIn('1 x Plain Tee (size M)', content)
        self.assertIn("'=HYPERLINK", content)  # neutralised so spreadsheets don't run it

    def test_product_form_saves_stock_grid(self):
        white = Color.objects.create(name='White', hex_code='#FFFFFF')
        base = {'code': 'TW-50', 'name': 'Basic Tank', 'price': '9', 'categories': [self.tees.pk],
                'is_active': 'on', 'in_stock': 'on', 'stock_grid': '1'}
        self.client.post(reverse('manager:product_add'), {
            **base, 'sizes': [self.size_m.pk], 'colors': [self.black.pk, white.pk],
            f'stock-{self.size_m.pk}-{self.black.pk}': '7', f'stock-{self.size_m.pk}-{white.pk}': '',
        })
        product = Product.objects.get(code='TW-50')
        self.assertEqual(sorted((v.color.name, v.quantity) for v in product.variants.all()), [('Black', 7), ('White', 0)])

        # Untick every size and color: their stock rows go, one "any" row remains.
        self.client.post(reverse('manager:product_edit', args=[product.pk]), {**base, 'stock-0-0': '2'})
        self.assertEqual([(v.size, v.color, v.quantity) for v in product.variants.all()], [(None, None, 2)])
        def listed(status):
            response = self.client.get(reverse('manager:products'), {'status': status})
            return list(response.context['page_obj'].object_list)

        self.assertIn(product, listed('low_stock'))
        self.assertNotIn(product, listed('out_of_stock'))
        self.assertIn(self.product, listed('out_of_stock'))  # Plain Tee has no stock rows at all

    def test_cancelling_or_deleting_an_order_puts_stock_back(self):
        variant = ProductVariant.objects.create(product=self.product, size=self.size_m, quantity=4)
        url = reverse('manager:order_status', args=[self.order.number])
        self.client.post(url, {'status': 'cancelled'})
        variant.refresh_from_db()
        self.assertEqual(variant.quantity, 5)
        self.client.post(url, {'status': 'confirmed'})
        variant.refresh_from_db()
        self.assertEqual(variant.quantity, 4)
        self.client.post(reverse('manager:order_delete', args=[self.order.number]))
        variant.refresh_from_db()
        self.assertEqual(variant.quantity, 5)

    def test_in_store_sale_needs_size_when_product_has_sizes(self):
        self.product.sizes.add(self.size_m)
        self.assertContains(self.sale_post(), 'choose a size')

    def test_remove_sample_products_button(self):
        sample = Product.objects.create(name='Demo', price=1, is_sample=True)
        self.client.post(reverse('manager:remove_sample_products'))
        self.assertFalse(Product.objects.filter(pk=sample.pk).exists())
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
