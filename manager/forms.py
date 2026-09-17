import re
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.utils.text import slugify

from store.models import Category, Color, Product, PromoCode, Size, StoreSettings

User = get_user_model()
HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')


class StaffLoginForm(AuthenticationForm):
    """Log in with an admin (staff) account, by username or email."""

    username = forms.CharField(
        label='Email or username',
        widget=forms.TextInput(attrs={'autofocus': True, 'autocomplete': 'username'}),
    )
    password = forms.CharField(
        label='Password', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'})
    )
    error_messages = {
        'invalid_login': 'Those details don’t match an account. Check the email/username and password.',
        'inactive': 'This account has been switched off.',
        'not_staff': 'This account isn’t an admin account, so it can’t open the store manager.',
    }

    def clean(self):
        username = (self.cleaned_data.get('username') or '').strip()
        if '@' in username:
            user = User.objects.filter(email__iexact=username).order_by('-is_staff').first()
            if user:
                self.cleaned_data['username'] = user.get_username()
        return super().clean()

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise forms.ValidationError(self.error_messages['not_staff'], code='not_staff')


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput(attrs={'accept': 'image/*'}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if isinstance(data, (list, tuple)):
            return [super(MultipleImageField, self).clean(item, initial) for item in data]
        return [super().clean(data, initial)] if data else []


class ProductForm(forms.ModelForm):
    new_images = MultipleImageField(required=False, label='Add photos')
    new_images_color = forms.ModelChoiceField(
        Color.objects.all(), required=False, empty_label='Any color', label='The new photos show'
    )
    new_color_name = forms.CharField(required=False, max_length=40, label='Add a new color')
    new_color_hex = forms.CharField(
        required=False, initial='#000000', label='Shade', widget=forms.TextInput(attrs={'type': 'color'})
    )
    new_sizes = forms.CharField(
        required=False, max_length=200, label='Add sizes that aren’t listed',
        widget=forms.TextInput(attrs={'placeholder': 'e.g. 36, 38, 40 or One size'}),
        help_text='Separate several sizes with commas.',
    )

    class Meta:
        model = Product
        fields = [
            'code', 'name', 'description', 'details', 'price', 'compare_at_price',
            'categories', 'sizes', 'colors', 'in_stock', 'is_active', 'is_featured',
        ]
        labels = {
            'name': 'Product name',
            'code': 'Product ID',
            'description': 'Description',
            'details': 'Fabric & care (optional)',
            'price': 'Price',
            'compare_at_price': 'Original price (optional)',
            'in_stock': 'For sale',
            'is_active': 'Show in the shop',
            'is_featured': 'Best seller',
        }
        help_texts = {
            'compare_at_price': 'Fill in to show the item on sale — e.g. original 45, price 35.',
            'details': 'One point per line, e.g. “100% cotton”.',
            'code': 'Your own ID for this product. You’ll type it when recording in-store sales.',
        }
        widgets = {
            'code': forms.TextInput(attrs={'placeholder': 'e.g. TW-1042', 'autocomplete': 'off', 'spellcheck': 'false'}),
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Ribbed Basic Tank Top'}),
            'description': forms.Textarea(attrs={'rows': 5, 'placeholder': 'What makes it special: fit, feel, how to wear it…'}),
            'details': forms.Textarea(attrs={'rows': 4, 'placeholder': '95% cotton, 5% elastane\nMachine wash cold'}),
            'price': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'inputmode': 'decimal'}),
            'compare_at_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'inputmode': 'decimal'}),
            'categories': forms.CheckboxSelectMultiple,
            'sizes': forms.CheckboxSelectMultiple,
            'colors': forms.CheckboxSelectMultiple,
        }
        error_messages = {
            'categories': {'required': 'Tick at least one category so customers can find this product.'},
            'code': {'required': 'Enter the product ID.'},
            'name': {'required': 'Give the product a name.'},
            'price': {'required': 'Enter the price.'},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['code'].required = True

    def clean_code(self):
        code = self.cleaned_data['code'].strip()
        if Product.objects.filter(code__iexact=code).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Another product already uses this ID.')
        return code

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is not None and price < 0:
            raise forms.ValidationError('The price can’t be negative.')
        return price

    def clean_new_color_hex(self):
        value = self.cleaned_data.get('new_color_hex') or ''
        return value if HEX_COLOR.match(value) else '#000000'

    def clean(self):
        cleaned = super().clean()
        price, original = cleaned.get('price'), cleaned.get('compare_at_price')
        if price is not None and original is not None and original <= price:
            self.add_error('compare_at_price', 'The original price must be higher than the price — or leave it empty.')
        return cleaned


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'parent', 'description', 'image', 'sort_order', 'is_active']
        labels = {
            'name': 'Category name',
            'parent': 'Place it inside',
            'description': 'Short description (optional)',
            'image': 'Category photo (optional)',
            'sort_order': 'Position',
            'is_active': 'Show on the website',
        }
        help_texts = {
            'image': 'If empty, a product photo from this category is used.',
            'sort_order': 'Lower numbers appear first in menus.',
        }
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, tree=(), **kwargs):
        super().__init__(*args, **kwargs)
        excluded = set(self.instance.get_descendant_ids()) if self.instance.pk else set()
        options = [c for c in tree if c.pk not in excluded]
        parent = self.fields['parent']
        parent.queryset = Category.objects.exclude(pk__in=excluded)
        parent.choices = [('', 'Nothing — it’s a main department (like Women or Men)')] + [
            (c.pk, f'{c.indent}{c.name}') for c in options
        ]

    def clean(self):
        cleaned = super().clean()
        name = (cleaned.get('name') or '').strip()
        if not name:
            return cleaned
        slug = self.instance.slug or slugify(name) or slugify(name, allow_unicode=True)
        if not slug:
            self.add_error('name', 'Use at least one letter or number in the name.')
            return cleaned
        parent = cleaned.get('parent')
        path = f'{parent.path}/{slug}' if parent else slug
        if Category.objects.filter(path=path).exclude(pk=self.instance.pk).exists():
            self.add_error('name', 'There’s already a category with this name in the same place.')
        return cleaned


class PromoCodeForm(forms.ModelForm):
    class Meta:
        model = PromoCode
        fields = ['code', 'kind', 'value', 'min_subtotal', 'starts_at', 'ends_at', 'max_uses', 'is_active']
        labels = {
            'code': 'Code customers type',
            'kind': 'What does it give?',
            'value': 'Discount',
            'min_subtotal': 'Minimum order (optional)',
            'starts_at': 'Starts (optional)',
            'ends_at': 'Ends (optional)',
            'max_uses': 'Usage limit (optional)',
            'is_active': 'Active',
        }
        help_texts = {
            'code': 'Letters and numbers, e.g. WELCOME10. Not case-sensitive.',
            'value': '',
            'min_subtotal': 'The bag must be worth at least this much.',
            'max_uses': 'Total number of orders that can use it.',
        }
        widgets = {
            'code': forms.TextInput(attrs={'placeholder': 'WELCOME10', 'autocapitalize': 'characters', 'spellcheck': 'false'}),
            'kind': forms.RadioSelect,
            'value': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'min_subtotal': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'starts_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'ends_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'max_uses': forms.NumberInput(attrs={'min': '1'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['value'].required = False

    def clean_value(self):
        return self.cleaned_data.get('value') or Decimal('0')


class StoreSettingsForm(forms.ModelForm):
    class Meta:
        model = StoreSettings
        fields = [
            'currency', 'delivery_fee', 'free_delivery_over', 'delivery_time',
            'phone', 'whatsapp', 'address', 'instagram_url', 'facebook_url', 'tiktok_url',
            'announcement', 'hero_title', 'hero_subtitle', 'hero_image', 'logo',
        ]
        labels = {
            'currency': 'Currency symbol',
            'delivery_fee': 'Delivery fee',
            'free_delivery_over': 'Free delivery for orders over',
            'delivery_time': 'Delivery time',
            'phone': 'Phone number',
            'whatsapp': 'WhatsApp number',
            'address': 'Shop address (optional)',
            'instagram_url': 'Instagram link',
            'facebook_url': 'Facebook link',
            'tiktok_url': 'TikTok link',
            'announcement': 'Top bar message',
            'hero_title': 'Homepage headline',
            'hero_subtitle': 'Homepage text',
            'hero_image': 'Homepage photo',
            'logo': 'Logo',
        }
        help_texts = {
            'currency': 'Shown before every price, e.g. $',
            'free_delivery_over': 'Leave empty if delivery is never free.',
            'delivery_time': 'e.g. 2–4 business days',
            'whatsapp': 'With country code, e.g. 961 70 123 456.',
            'announcement': 'The short line at the very top of every page.',
            'hero_image': 'Optional. A large portrait photo for the top of the homepage.',
            'logo': 'Optional. Replaces the text logo at the top of the site.',
        }
        widgets = {
            'hero_subtitle': forms.Textarea(attrs={'rows': 3}),
            'delivery_fee': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'free_delivery_over': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'instagram_url': forms.URLInput(attrs={'placeholder': 'https://instagram.com/yourshop'}),
            'facebook_url': forms.URLInput(attrs={'placeholder': 'https://facebook.com/yourshop'}),
            'tiktok_url': forms.URLInput(attrs={'placeholder': 'https://tiktok.com/@yourshop'}),
        }

    def clean_whatsapp(self):
        return re.sub(r'\D', '', self.cleaned_data.get('whatsapp') or '')


class SizeForm(forms.ModelForm):
    class Meta:
        model = Size
        fields = ['name', 'sort_order']
        labels = {'name': 'Size', 'sort_order': 'Position'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sort_order'].required = False

    def clean_sort_order(self):
        value = self.cleaned_data.get('sort_order')
        if value is None:
            last = Size.objects.order_by('-sort_order').first()
            value = last.sort_order + 1 if last else 0
        return value


class ColorForm(forms.ModelForm):
    class Meta:
        model = Color
        fields = ['name', 'hex_code']
        labels = {'name': 'Color name', 'hex_code': 'Shade'}
        widgets = {'hex_code': forms.TextInput(attrs={'type': 'color'})}

    def clean_hex_code(self):
        value = self.cleaned_data.get('hex_code') or ''
        if not HEX_COLOR.match(value):
            raise forms.ValidationError('Pick a shade.')
        return value.upper()
