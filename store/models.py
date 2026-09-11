from decimal import Decimal

from django.db import models
from django.urls import reverse
from django.utils.text import slugify


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
            self.slug = slugify(self.name)
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
    sku = models.CharField('SKU', max_length=40, blank=True)
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


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'New'
        CONFIRMED = 'confirmed', 'Confirmed'
        SHIPPED = 'shipped', 'Out for delivery'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'

    number = models.CharField(max_length=20, unique=True, editable=False, blank=True)
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    city = models.CharField('city / area', max_length=80)
    address = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
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
