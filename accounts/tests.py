from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from store.models import Order, Product, ProductVariant, StoreSettings

from .models import Address

User = get_user_model()

PASSWORD = 'Soft-Linen-42'
DELIVERY = {'full_name': 'Sara Haddad', 'phone': '+961 70 123 456', 'city': 'Beirut', 'address': 'Hamra Street, Bldg 5'}


@override_settings(RESEND_API_KEY='')
class AccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        StoreSettings.objects.create(delivery_fee=Decimal('4.00'), free_delivery_over=None)
        cls.product = Product.objects.create(name='Plain Tee', price=Decimal('20.00'))
        ProductVariant.objects.create(product=cls.product, quantity=50)

    def make_user(self, email='sara@example.com'):
        return User.objects.create_user(
            username=email, email=email, password=PASSWORD, first_name='Sara', last_name='Haddad'
        )

    def add_to_bag(self):
        self.client.post(reverse('store:cart_add', args=[self.product.pk]), {'quantity': 1})

    def place_order(self, **data):
        self.add_to_bag()
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse('store:checkout'), {**DELIVERY, **data})

    def signup(self, email='Sara@Example.com', password=PASSWORD):
        return self.client.post(reverse('accounts:signup'), {
            'full_name': 'Sara Haddad', 'email': email, 'password1': password, 'password2': password,
        })

    def test_signup_creates_account_and_logs_in(self):
        self.assertRedirects(self.signup(), reverse('accounts:dashboard'))
        user = User.objects.get()
        self.assertEqual((user.username, user.email, user.first_name, user.last_name),
                         ('sara@example.com', 'sara@example.com', 'Sara', 'Haddad'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_signup_rejects_duplicate_email_and_weak_password(self):
        self.make_user()
        response = self.signup(email='SARA@example.com', password='12345678')
        self.assertContains(response, 'already exists')
        self.assertContains(response, 'too common')
        self.assertEqual(User.objects.count(), 1)

    def test_login_with_email_is_case_insensitive(self):
        self.make_user()
        login_url = reverse('accounts:login')
        response = self.client.post(login_url, {'username': 'SARA@example.com', 'password': PASSWORD})
        self.assertRedirects(response, reverse('accounts:dashboard'))
        self.client.logout()
        self.assertContains(self.client.post(login_url, {'username': 'sara@example.com', 'password': 'nope'}),
                            'don’t match')

    def test_checkout_is_prefilled_and_order_is_linked_to_account(self):
        user = self.make_user()
        Address.objects.create(user=user, label='Home', **DELIVERY)
        self.client.force_login(user)
        self.add_to_bag()

        response = self.client.get(reverse('store:checkout'))
        self.assertEqual(response.context['form'].initial['email'], 'sara@example.com')
        self.assertContains(response, 'value="Hamra Street, Bldg 5"')

        self.place_order(email='sara@example.com', save_address='on')
        order = Order.objects.get()
        self.assertEqual(order.user, user)
        self.assertEqual(user.addresses.count(), 1)  # the same address isn't saved twice
        self.assertContains(self.client.get(reverse('accounts:order', args=[order.number])), order.number)

    def test_new_address_is_saved_only_when_ticked(self):
        user = self.make_user()
        self.client.force_login(user)
        self.place_order()
        self.assertFalse(user.addresses.exists())
        self.place_order(city='Tyre', save_address='on')
        self.assertEqual(list(user.addresses.values_list('city', 'is_default')), [('Tyre', True)])

    def test_guest_order_is_saved_to_account_created_afterwards(self):
        self.add_to_bag()
        response = self.client.get(reverse('store:checkout'))
        self.assertNotIn('save_address', response.context['form'].fields)
        self.assertContains(response, reverse('accounts:login'))

        self.place_order(email='sara@example.com')
        order = Order.objects.get()
        self.assertIsNone(order.user)
        signup_page = self.client.get(reverse('accounts:signup'))
        self.assertEqual(signup_page.context['form'].initial['email'], 'sara@example.com')

        self.signup()
        order.refresh_from_db()
        user = User.objects.get()
        self.assertEqual(order.user, user)
        self.assertEqual(user.addresses.get().address, 'Hamra Street, Bldg 5')

    def test_account_pages_are_private(self):
        owner, other = self.make_user(), self.make_user('ali@example.com')
        order = Order.objects.create(user=owner, **DELIVERY)
        address = Address.objects.create(user=owner, **DELIVERY)
        dashboard = reverse('accounts:dashboard')
        self.assertRedirects(self.client.get(dashboard), f"{reverse('accounts:login')}?next={dashboard}")

        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('accounts:order', args=[order.number])).status_code, 404)
        self.assertEqual(self.client.get(reverse('accounts:address_edit', args=[address.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('accounts:address_delete', args=[address.pk])).status_code, 404)
        self.assertTrue(Address.objects.filter(pk=address.pk).exists())

    def test_customer_always_has_one_default_address(self):
        user = self.make_user()
        self.client.force_login(user)
        home = Address.objects.create(user=user, label='Home', **DELIVERY)
        work = Address.objects.create(user=user, label='Work', **{**DELIVERY, 'city': 'Saida'})
        self.assertEqual(list(user.addresses.filter(is_default=True)), [home])

        self.client.post(reverse('accounts:address_default', args=[work.pk]))
        self.assertEqual(list(user.addresses.filter(is_default=True)), [work])

        self.client.post(reverse('accounts:address_delete', args=[work.pk]))
        self.assertEqual(list(user.addresses.filter(is_default=True)), [home])

    def test_account_pages_render_and_details_update(self):
        user = self.make_user()
        self.client.force_login(user)
        Address.objects.create(user=user, **DELIVERY)
        Order.objects.create(user=user, **DELIVERY)
        for name in ('accounts:dashboard', 'accounts:details', 'accounts:password', 'accounts:address_add'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

        self.client.post(reverse('accounts:details'), {'full_name': 'Sara H', 'email': 'New@Example.com'})
        user.refresh_from_db()
        self.assertEqual((user.username, user.email, user.last_name), ('new@example.com', 'new@example.com', 'H'))

        self.client.post(reverse('accounts:logout'))
        self.assertNotIn('_auth_user_id', self.client.session)
