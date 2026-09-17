import io
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Category, Color, Order, Product, ProductVariant, PromoCode, Size, StoreSettings

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA, RESEND_API_KEY='re_test', ORDER_NOTIFICATION_EMAIL='teffehawear@gmail.com')
class StoreFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('setup_categories', stdout=io.StringIO())
        cls.tees = Category.objects.get(path='women/tops/t-shirts')
        cls.size_m = Size.objects.get(name='M')
        cls.black = Color.objects.create(name='Black', hex_code='#000000')
        cls.product = Product.objects.create(name='Test Tee', price=Decimal('20.00'))
        cls.product.categories.add(cls.tees)
        cls.product.sizes.add(cls.size_m)
        cls.product.colors.add(cls.black)
        cls.stock = ProductVariant.objects.create(product=cls.product, size=cls.size_m, color=cls.black, quantity=10)
        StoreSettings.objects.create(delivery_fee=Decimal('4.00'), free_delivery_over=Decimal('75.00'))

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def add_to_cart(self, **data):
        payload = {'size': 'M', 'color': 'Black', 'quantity': 2, **data}
        return self.client.post(reverse('store:cart_add', args=[self.product.pk]), payload)

    def test_category_tree_matches_brief(self):
        women = Category.objects.get(path='women')
        self.assertEqual(
            [c.name for c in women.children.all()],
            ['Tops', 'Bottoms', 'Dresses', 'Sets', 'Jackets & Blazers', 'Sportswear'],
        )
        men = Category.objects.get(path='men')
        self.assertEqual([c.name for c in men.children.all()],
                         ['Sports Tops', 'Sports Sets', 'Sports Jackets', 'Polo Shirts'])
        # "Sports Sets" exists in three places with distinct URLs.
        self.assertEqual(Category.objects.filter(slug='sports-sets').count(), 3)

    def test_parent_category_lists_products_from_subcategories(self):
        for path in ('women', 'women/tops', 'women/tops/t-shirts'):
            response = self.client.get(reverse('store:category', args=[path]))
            self.assertContains(response, 'Test Tee')
        response = self.client.get(reverse('store:category', args=['men']))
        self.assertNotContains(response, 'Test Tee')

    def test_add_to_cart_requires_valid_size(self):
        self.add_to_cart(size='')
        self.assertEqual(self.client.session.get('cart', {}), {})
        self.add_to_cart(size='XXS')
        self.assertEqual(self.client.session.get('cart', {}), {})
        self.add_to_cart()
        self.assertEqual(len(self.client.session['cart']), 1)

    def test_add_to_cart_json_response(self):
        response = self.client.post(
            reverse('store:cart_add', args=[self.product.pk]),
            {'size': 'M', 'color': 'Black'}, headers={'x-requested-with': 'fetch'},
        )
        self.assertEqual(response.json()['count'], 1)
        self.assertIn('Test Tee', response.json()['drawer'])

    @mock.patch('store.emails.requests.post')
    def test_checkout_creates_cod_order_and_emails_store(self, post):
        post.return_value.ok = True
        self.add_to_cart()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('store:checkout'), {
                'full_name': 'Sara Haddad', 'phone': '+961 70 123 456', 'email': 'sara@example.com',
                'city': 'Beirut', 'address': 'Hamra Street, Bldg 5', 'notes': '',
            })
        order = Order.objects.get()
        self.assertRedirects(response, reverse('store:order_success', args=[order.number]))
        self.assertEqual(order.subtotal, Decimal('40.00'))
        self.assertEqual(order.delivery_fee, Decimal('4.00'))
        self.assertEqual(order.total, Decimal('44.00'))
        self.assertEqual(order.payment_method, 'Cash on delivery')
        self.assertEqual(order.items.get().size, 'M')

        post.assert_called_once()
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['to'], ['teffehawear@gmail.com'])
        self.assertEqual(payload['reply_to'], 'sara@example.com')
        self.assertIn(order.number, payload['subject'])
        self.assertIn('Hamra Street', payload['html'])
        order.refresh_from_db()
        self.assertTrue(order.email_sent)
        self.assertEqual(self.client.session['cart'], {})

        # Only the browser that placed the order can see its confirmation.
        self.assertContains(self.client.get(response.url), 'Thank you, Sara!')
        self.client.logout()
        self.assertEqual(self.client.get(response.url).status_code, 404)

    @mock.patch('store.emails.requests.post')
    def test_order_is_kept_when_email_fails(self, post):
        post.return_value.ok = False
        post.return_value.status_code = 403
        self.add_to_cart(quantity=4)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('store:checkout'), {
                'full_name': 'Ali', 'phone': '70123456', 'city': 'Tyre', 'address': 'Main road',
            })
        order = Order.objects.get()
        self.assertFalse(order.email_sent)
        self.assertEqual(order.delivery_fee, Decimal('0.00'))  # 80 >= free delivery threshold

    def test_checkout_rejects_bad_phone(self):
        self.add_to_cart()
        response = self.client.post(reverse('store:checkout'), {
            'full_name': 'Ali', 'phone': '12', 'city': 'Tyre', 'address': 'Main road',
        })
        self.assertContains(response, 'valid phone number')
        self.assertFalse(Order.objects.exists())

    def checkout_data(self, **extra):
        return {'full_name': 'Sara Haddad', 'phone': '+961 70 123 456', 'city': 'Beirut',
                'address': 'Hamra Street', **extra}

    @mock.patch('store.emails.requests.post')
    def test_percent_promo_code_discounts_order(self, post):
        post.return_value.ok = True
        PromoCode.objects.create(code='welcome10', kind='percent', value=Decimal('10'))
        self.add_to_cart()  # 2 × 20 = 40
        url = reverse('store:checkout')

        response = self.client.post(url, self.checkout_data(action='apply_promo', promo_code=' Welcome10 '))
        self.assertContains(response, 'WELCOME10')
        self.assertContains(response, 'Sara Haddad')  # typed delivery details are kept
        self.assertNotContains(response, 'field__error')
        self.assertEqual(response.context['totals']['total'], Decimal('40.00'))  # 40 − 4 + 4 delivery

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, self.checkout_data())
        order = Order.objects.get()
        self.assertEqual((order.promo_code, order.discount, order.total),
                         ('WELCOME10', Decimal('4.00'), Decimal('40.00')))
        self.assertEqual(PromoCode.objects.get().times_used, 1)
        self.assertIn('WELCOME10', post.call_args.kwargs['json']['html'])
        self.assertNotIn('promo_code', self.client.session)

    def test_code_typed_but_not_applied_is_still_checked(self):
        self.add_to_cart()
        response = self.client.post(reverse('store:checkout'), self.checkout_data(promo_code='NOPE'))
        self.assertContains(response, 'not valid')
        self.assertFalse(Order.objects.exists())

    def test_promo_code_rules(self):
        PromoCode.objects.create(code='BIG', kind='fixed', value=Decimal('15'), min_subtotal=Decimal('50'))
        PromoCode.objects.create(code='OLD', kind='percent', value=10, ends_at=timezone.now() - timedelta(days=1))
        PromoCode.objects.create(code='GONE', kind='percent', value=10, max_uses=1, times_used=1)
        PromoCode.objects.create(code='OFF', kind='percent', value=10, is_active=False)
        PromoCode.objects.create(code='SHIPFREE', kind='free_delivery')
        PromoCode.objects.create(code='HUGE', kind='fixed', value=Decimal('100'))
        self.add_to_cart()  # subtotal 40
        url = reverse('store:checkout')

        for code, message in [('BIG', 'minimum order'), ('OLD', 'expired'), ('GONE', 'fully used'), ('OFF', 'not valid')]:
            response = self.client.post(url, {'action': 'apply_promo', 'promo_code': code})
            self.assertContains(response, message)
            self.assertIsNone(response.context['totals']['promo'])

        totals = self.client.post(url, {'action': 'apply_promo', 'promo_code': 'shipfree'}).context['totals']
        self.assertEqual((totals['discount'], totals['delivery_fee'], totals['total']),
                         (Decimal('0.00'), Decimal('0.00'), Decimal('40.00')))

        totals = self.client.post(url, {'action': 'remove_promo'}).context['totals']
        self.assertEqual(totals['total'], Decimal('44.00'))

        # A fixed discount never exceeds the bag subtotal.
        totals = self.client.post(url, {'action': 'apply_promo', 'promo_code': 'HUGE'}).context['totals']
        self.assertEqual((totals['discount'], totals['total']), (Decimal('40.00'), Decimal('4.00')))

    def test_promo_code_usage_limit_is_enforced_when_ordering(self):
        promo = PromoCode.objects.create(code='ONCE', kind='fixed', value=5, max_uses=1)
        self.add_to_cart()
        self.client.post(reverse('store:checkout'), {'action': 'apply_promo', 'promo_code': 'ONCE'})
        self.assertTrue(promo.claim())  # someone else uses it first
        self.assertFalse(promo.claim())
        response = self.client.post(reverse('store:checkout'), self.checkout_data())
        self.assertContains(response, 'fully used')
        self.assertFalse(Order.objects.exists())

    def test_stock_limits_what_can_be_added(self):
        url = reverse('store:cart_add', args=[self.product.pk])
        fetch = {'x-requested-with': 'fetch'}
        self.stock.quantity = 2
        self.stock.save()
        response = self.client.post(url, {'size': 'M', 'color': 'Black', 'quantity': 3}, headers=fetch)
        self.assertEqual(response.status_code, 400)
        self.assertIn('only 2 left', response.json()['error'])

        self.stock.quantity = 50
        self.stock.save()
        response = self.client.post(url, {'size': 'M', 'color': 'Black', 'quantity': 51}, headers=fetch)
        self.assertIn('don’t have that many', response.json()['error'])  # the real number stays private

        self.stock.quantity = 0
        self.stock.save()
        response = self.client.post(url, {'size': 'M', 'color': 'Black'}, headers=fetch)
        self.assertIn('sold out', response.json()['error'])

    def test_shop_only_ever_says_1_or_2_left(self):
        self.stock.quantity = 57
        self.stock.save()
        self.assertContains(self.client.get(self.product.get_absolute_url()), '"M|Black": 3')  # 3 = plenty

        self.stock.quantity = 1
        self.stock.save()
        self.assertContains(self.client.get(self.product.get_absolute_url()), '"M|Black": 1')
        self.add_to_cart(quantity=1)
        self.assertContains(self.client.get(reverse('store:cart')), 'Only 1 left')

    @mock.patch('store.emails.requests.post')
    def test_orders_take_stock_and_stop_when_it_runs_out(self, post):
        from django.db import transaction

        from store import stock

        post.return_value.ok = True
        self.add_to_cart()  # 2
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('store:checkout'), self.checkout_data())
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 8)

        self.add_to_cart(quantity=3)
        ProductVariant.objects.filter(pk=self.stock.pk).update(quantity=1)  # sold in the shop meanwhile
        response = self.client.post(reverse('store:checkout'), self.checkout_data())
        self.assertRedirects(response, reverse('store:cart'), fetch_redirect_response=False)
        self.assertEqual(Order.objects.count(), 1)

        # Placing the order re-checks stock inside the transaction, all or nothing.
        with self.assertRaises(stock.OutOfStock), transaction.atomic():
            stock.reserve([(self.product.pk, 'M', 'Black', 5)])
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 1)

    def test_remove_sample_data_keeps_real_products(self):
        sample = Product.objects.create(name='Sample', price=1, is_sample=True)
        call_command('remove_sample_data', stdout=io.StringIO())
        self.assertFalse(Product.objects.filter(pk=sample.pk).exists())
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_admin_pages_render(self):
        from django.contrib.auth.models import User
        self.client.force_login(User.objects.create_superuser('admin', 'a@example.com', 'x'))
        PromoCode.objects.create(code='ADMIN5', kind='fixed', value=5, max_uses=10)
        for model in ('product', 'category', 'order', 'color', 'size', 'storesettings', 'promocode'):
            url = reverse(f'admin:store_{model}_changelist')
            self.assertEqual(self.client.get(url).status_code, 200, model)
        self.assertEqual(self.client.get(reverse('admin:store_product_change', args=[self.product.pk])).status_code, 200)

    def test_pages_render(self):
        self.add_to_cart()
        for name in ('store:home', 'store:shop', 'store:new_in', 'store:sale', 'store:cart', 'store:checkout'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.assertContains(self.client.get(reverse('store:search'), {'q': 'tee'}), 'Test Tee')
        self.assertContains(self.client.get(self.product.get_absolute_url()), 'Add to bag')
