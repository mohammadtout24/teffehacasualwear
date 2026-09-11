import io
import shutil
import tempfile
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Category, Color, Order, Product, Size, StoreSettings

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

    def test_remove_sample_data_keeps_real_products(self):
        sample = Product.objects.create(name='Sample', price=1, is_sample=True)
        call_command('remove_sample_data', stdout=io.StringIO())
        self.assertFalse(Product.objects.filter(pk=sample.pk).exists())
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_admin_pages_render(self):
        from django.contrib.auth.models import User
        self.client.force_login(User.objects.create_superuser('admin', 'a@example.com', 'x'))
        for model in ('product', 'category', 'order', 'color', 'size', 'storesettings'):
            url = reverse(f'admin:store_{model}_changelist')
            self.assertEqual(self.client.get(url).status_code, 200, model)
        self.assertEqual(self.client.get(reverse('admin:store_product_change', args=[self.product.pk])).status_code, 200)

    def test_pages_render(self):
        self.add_to_cart()
        for name in ('store:home', 'store:shop', 'store:new_in', 'store:sale', 'store:cart', 'store:checkout'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.assertContains(self.client.get(reverse('store:search'), {'q': 'tee'}), 'Test Tee')
        self.assertContains(self.client.get(self.product.get_absolute_url()), 'Add to bag')
