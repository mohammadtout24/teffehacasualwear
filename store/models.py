from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from .money import format_money

# Customers never see stock numbers, except "Only 1 left" / "Only 2 left" at or below this.
LOW_STOCK = 2


class Category(models.Model):
    """A node in the category tree, e.g. Women > Tops > T-Shirts.

    `path` stores the full slug path ("women/tops/t-shirts") so category URLs
    read naturally and stay unique even when two branches share a name
    (e.g. "Sports Sets" exists under both Women and Men).
    """

    parent = models.ForeignKey(
        'self', null=True, blank=True, related_name='children', on_delete=models.CASCADE
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, blank=True)
    path = models.CharField(max_length=255, unique=True, editable=False)
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to='categories/', blank=True,
        help_text='Optional. If empty, the first product image in this category is used.',
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return ' › '.join(c.name for c in self.get_ancestors(include_self=True))

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name) or slugify(self.name, allow_unicode=True)
        self.path = f'{self.parent.path}/{self.slug}' if self.parent else self.slug
        super().save(*args, **kwargs)
        # Keep descendants' paths in sync after a rename or move.
        for child in self.children.all():
            child.save()

    def get_absolute_url(self):
        return reverse('store:category', args=[self.path])

    def get_ancestors(self, include_self=False):
        chain = []
        node = self if include_self else self.parent
        while node is not None:
            chain.append(node)
            node = node.parent
        return list(reversed(chain))

    def get_descendant_ids(self, include_self=True):
        ids = [self.pk] if include_self else []
        for child in self.children.all():
            ids.extend(child.get_descendant_ids())
        return ids

    @property
    def depth(self):
        return self.path.count('/')

    @property
    def root(self):
        return self.get_ancestors(include_self=True)[0]

    def cover_image(self):
        """Uploaded image, or the main image of the newest product in the subtree."""
        if self.image:
            return self.image
        image = (
            ProductImage.objects.filter(
                product__is_active=True,
                product__categories__in=self.get_descendant_ids(),
            )
            .order_by('-product__is_featured', '-product__price', 'sort_order')
            .first()
        )
        return image.image if image else None


class Size(models.Model):
    name = models.CharField(max_length=20, unique=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class Color(models.Model):
    name = models.CharField(max_length=40, unique=True)
    hex_code = models.CharField(max_length=7, default='#000000', help_text='e.g. #7A0F1F')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def in_categories(self, category_ids):
        return self.filter(categories__in=category_ids).distinct()


class Product(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    code = models.CharField(
        'product ID', max_length=40, blank=True,
        help_text='Your own ID for this product, e.g. TW-1042. Used to find it when recording in-store sales.',
    )
    description = models.TextField(blank=True)
    details = models.TextField(
        'fabric & care', blank=True, help_text='One item per line, shown as a list.'
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(
        'original price', max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Optional. Set higher than the price to show the item as on sale.',
    )
    categories = models.ManyToManyField(Category, related_name='products')
    sizes = models.ManyToManyField(Size, blank=True, related_name='products')
    colors = models.ManyToManyField(Color, blank=True, related_name='products')
    in_stock = models.BooleanField(default=True)
    is_active = models.BooleanField('visible on site', default=True)
    is_featured = models.BooleanField('best seller', default=False)
    is_sample = models.BooleanField(
        default=False, editable=False,
        help_text='Created by load_sample_data; removed by remove_sample_data.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                Lower('code'), condition=~models.Q(code=''), name='unique_product_code',
                violation_error_message='Another product already uses this ID.',
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or 'product'
            slug, n = base, 2
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f'{base}-{n}', n + 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('store:product', args=[self.slug])

    @property
    def display_id(self):
        """The product ID, or its database number (#12) if no ID was given."""
        return self.code or f'#{self.pk}'

    @property
    def on_sale(self):
        return bool(self.compare_at_price and self.compare_at_price > self.price)

    @property
    def discount_percent(self):
        if not self.on_sale:
            return 0
        return int(round((1 - self.price / self.compare_at_price) * 100))

    @property
    def savings(self):
        return self.compare_at_price - self.price if self.on_sale else Decimal('0')

    @property
    def main_image(self):
        images = list(self.images.all())
        return images[0] if images else None

    @property
    def hover_image(self):
        images = list(self.images.all())
        return images[1] if len(images) > 1 else None

    def image_for(self, color_name):
        """The photo tagged with this color, falling back to the main image."""
        images = list(self.images.all())
        for image in images:
            if image.color_id and image.color.name == color_name:
                return image
        return images[0] if images else None

    def stock_map(self):
        """{(size name, color name): quantity}; names are '' for products without sizes/colors."""
        return {
            (v.size.name if v.size_id else '', v.color.name if v.color_id else ''): v.quantity
            for v in self.variants.all()
        }

    def stock_for(self, size, color):
        return self.stock_map().get((size or '', color or ''), 0)

    @property
    def total_stock(self):
        return sum(v.quantity for v in self.variants.all())

    @property
    def low_stock(self):
        return any(0 < v.quantity <= LOW_STOCK for v in self.variants.all())

    @property
    def is_available(self):
        return self.in_stock and self.total_stock > 0

    def public_stock(self):
        """Stock for the shop page, capped so the real numbers stay private:
        0 = sold out, 1-2 = that many left, 3 = plenty."""
        return {f'{size}|{color}': min(quantity, LOW_STOCK + 1) for (size, color), quantity in self.stock_map().items()}

    @property
    def detail_lines(self):
        return [line.strip() for line in self.details.splitlines() if line.strip()]

    def primary_category(self):
        """Deepest category, used for breadcrumbs."""
        cats = list(self.categories.all())
        return max(cats, key=lambda c: c.path.count('/'), default=None)


class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='products/')
    alt = models.CharField(max_length=150, blank=True)
    color = models.ForeignKey(
        Color, null=True, blank=True, on_delete=models.SET_NULL,
        help_text='Optional. Selecting this color on the product page shows this image.',
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'pk']

    def __str__(self):
        return self.alt or f'Image of {self.product}'


class ProductVariant(models.Model):
    """How many of one size + color of a product are in stock (never shown to customers)."""

    product = models.ForeignKey(Product, related_name='variants', on_delete=models.CASCADE)
    size = models.ForeignKey(Size, null=True, blank=True, on_delete=models.CASCADE)
    color = models.ForeignKey(Color, null=True, blank=True, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'stock'
        verbose_name_plural = 'stock'

    def __str__(self):
        parts = [part for part in (self.color and self.color.name, self.size and self.size.name) if part]
        return f'{self.product} ({", ".join(parts) or "any"}): {self.quantity}'


class StoreSettings(models.Model):
    """Single row of site-wide settings editable from the admin."""

    currency = models.CharField(max_length=5, default='$')
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('4.00'))
    free_delivery_over = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, default=Decimal('75.00'),
        help_text='Orders with a subtotal at or above this amount ship free. Leave empty to disable.',
    )
    delivery_time = models.CharField(max_length=100, default='2–4 business days')
    announcement = models.CharField(
        max_length=200, blank=True, default='Cash on delivery on every order',
        help_text='Short message shown in the bar at the top of every page.',
    )
    phone = models.CharField(max_length=30, blank=True)
    whatsapp = models.CharField(
        max_length=20, blank=True, help_text='International format, digits only, e.g. 96170123456'
    )
    instagram_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)
    address = models.CharField(max_length=200, blank=True)
    logo = models.ImageField(
        upload_to='branding/', blank=True,
        help_text='Optional. Upload the logo file to replace the text logo in the header.',
    )
    hero_title = models.CharField(max_length=120, default='Everyday elegance, made casual.')
    hero_subtitle = models.CharField(
        max_length=240, blank=True,
        default='Soft basics, easy sets and sportswear for her and him — delivered to your door, paid on arrival.',
    )
    hero_image = models.ImageField(upload_to='branding/', blank=True)

    class Meta:
        verbose_name = 'store settings'
        verbose_name_plural = 'store settings'

    def __str__(self):
        return 'Store settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def delivery_fee_for(self, subtotal):
        if subtotal <= 0:
            return Decimal('0.00')
        if self.free_delivery_over is not None and subtotal >= self.free_delivery_over:
            return Decimal('0.00')
        return self.delivery_fee


class PromoCode(models.Model):
    class Kind(models.TextChoices):
        PERCENT = 'percent', 'Percentage off'
        FIXED = 'fixed', 'Fixed amount off'
        FREE_DELIVERY = 'free_delivery', 'Free delivery'

    code = models.CharField(
        max_length=30, unique=True,
        help_text='What customers type at checkout, e.g. WELCOME10. Not case-sensitive.',
    )
    kind = models.CharField('discount type', max_length=20, choices=Kind.choices, default=Kind.PERCENT)
    value = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal('0'),
        help_text='10 means 10% off (percentage) or 10 off in your currency (fixed amount). '
                  'Ignored for free delivery.',
    )
    min_subtotal = models.DecimalField(
        'minimum order', max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Optional. The bag subtotal needed before the code can be used.',
    )
    starts_at = models.DateTimeField('valid from', null=True, blank=True)
    ends_at = models.DateTimeField('valid until', null=True, blank=True)
    max_uses = models.PositiveIntegerField(
        'usage limit', null=True, blank=True,
        help_text='Optional. Total number of orders that can use this code.',
    )
    times_used = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField('active', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    def clean(self):
        # Normalise before the admin's uniqueness check so "welcome10" clashes with "WELCOME10".
        self.code = (self.code or '').strip().upper()
        errors = {}
        if self.kind == self.Kind.PERCENT and not (0 < (self.value or 0) <= 100):
            errors['value'] = 'Enter a percentage between 1 and 100.'
        if self.kind == self.Kind.FIXED and (self.value or 0) <= 0:
            errors['value'] = 'Enter the amount to take off.'
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors['ends_at'] = 'The end date must be after the start date.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @classmethod
    def find(cls, code):
        code = (code or '').strip()
        return cls.objects.filter(code__iexact=code).first() if code else None

    def problem(self, subtotal, currency='$'):
        """Why this code can't be used on a bag worth `subtotal`, or '' if it can."""
        now = timezone.now()
        if not self.is_active or (self.starts_at and now < self.starts_at):
            return 'This promo code is not valid.'
        if self.ends_at and now >= self.ends_at:
            return 'This promo code has expired.'
        if self.max_uses is not None and self.times_used >= self.max_uses:
            return 'This promo code has already been fully used.'
        if self.min_subtotal and subtotal < self.min_subtotal:
            return (
                f'Add {format_money(self.min_subtotal - subtotal, currency)} more to use this code '
                f'(minimum order {format_money(self.min_subtotal, currency)}).'
            )
        return ''

    def discount_for(self, subtotal):
        if self.kind == self.Kind.PERCENT:
            amount = (subtotal * self.value / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        elif self.kind == self.Kind.FIXED:
            amount = self.value
        else:
            amount = Decimal('0.00')
        return min(amount, subtotal)

    def describe(self, currency='$'):
        if self.kind == self.Kind.PERCENT:
            return f'{self.value.normalize():f}% off'
        if self.kind == self.Kind.FIXED:
            return f'{format_money(self.value, currency)} off'
        return 'Free delivery'

    def claim(self):
        """Count one use. False if the usage limit was reached in the meantime."""
        codes = PromoCode.objects.filter(pk=self.pk)
        if self.max_uses is not None:
            codes = codes.filter(times_used__lt=self.max_uses)
        return codes.update(times_used=models.F('times_used') + 1) == 1


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'New'
        CONFIRMED = 'confirmed', 'Confirmed'
        SHIPPED = 'shipped', 'Out for delivery'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'

    class Channel(models.TextChoices):
        ONLINE = 'online', 'Online'
        IN_STORE = 'in_store', 'In store'

    number = models.CharField(max_length=20, unique=True, editable=False, blank=True)
    channel = models.CharField(
        'sold', max_length=10, choices=Channel.choices, default=Channel.ONLINE,
        help_text='Online orders come from the website; in-store sales are recorded in the store manager.',
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name='recorded_sales',
        on_delete=models.SET_NULL, help_text='The admin who recorded an in-store sale.',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name='orders', on_delete=models.SET_NULL,
        verbose_name='customer account', help_text='Empty for guest orders.',
    )
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    city = models.CharField('city / area', max_length=80)
    address = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    promo_code = models.CharField(max_length=30, blank=True)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=5, default='$')
    payment_method = models.CharField(max_length=40, default='Cash on delivery', editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    email_sent = models.BooleanField(default=False, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Order {self.number}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.number:
            self.number = f'TF{10000 + self.pk}'
            super().save(update_fields=['number'])

    @property
    def first_name(self):
        return self.full_name.split()[0] if self.full_name.strip() else ''

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL)
    product_name = models.CharField(max_length=150)
    product_code = models.CharField('product ID', max_length=40, blank=True)
    size = models.CharField(max_length=20, blank=True)
    color = models.CharField(max_length=40, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f'{self.quantity} × {self.product_name}'

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    @property
    def image(self):
        return self.product.image_for(self.color) if self.product else None
