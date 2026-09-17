from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Category, Color, Order, OrderItem, Product, ProductImage, ProductVariant, PromoCode, Size, StoreSettings,
)


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    fields = ['size', 'color', 'quantity']
    extra = 0
    verbose_name_plural = 'stock (per size and color)'


def thumb(image, size=56):
    if not image:
        return '—'
    return format_html(
        '<img src="{}" style="width:{}px;height:{}px;object-fit:cover;border-radius:6px">',
        image.url, size, int(size * 4 / 3),
    )


class SubcategoryInline(admin.TabularInline):
    model = Category
    fk_name = 'parent'
    fields = ['name', 'slug', 'sort_order', 'is_active']
    extra = 0
    verbose_name = 'subcategory'
    verbose_name_plural = 'subcategories'


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'path', 'product_count', 'sort_order', 'is_active']
    list_editable = ['sort_order', 'is_active']
    list_filter = ['parent', 'is_active']
    search_fields = ['name', 'path']
    prepopulated_fields = {'slug': ['name']}
    inlines = [SubcategoryInline]
    ordering = ['path']

    @admin.display(description='products')
    def product_count(self, obj):
        return obj.products.count()


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    fields = ['preview', 'image', 'color', 'alt', 'sort_order']
    readonly_fields = ['preview']
    extra = 1

    @admin.display(description='')
    def preview(self, obj):
        return thumb(obj.image)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['preview', 'name', 'price', 'compare_at_price', 'in_stock', 'is_featured', 'is_active', 'is_sample']
    list_display_links = ['preview', 'name']
    list_editable = ['price', 'in_stock', 'is_featured', 'is_active']
    list_filter = ['is_active', 'in_stock', 'is_featured', 'is_sample', 'categories']
    search_fields = ['name', 'code', 'description']
    prepopulated_fields = {'slug': ['name']}
    filter_horizontal = ['categories', 'sizes', 'colors']
    inlines = [ProductImageInline, ProductVariantInline]
    fieldsets = [
        (None, {'fields': ['code', 'name', 'slug', 'categories']}),
        ('Pricing', {'fields': ['price', 'compare_at_price']}),
        ('Description', {'fields': ['description', 'details']}),
        ('Options', {'fields': ['sizes', 'colors']}),
        ('Visibility', {'fields': ['is_active', 'in_stock', 'is_featured']}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('images')

    @admin.display(description='')
    def preview(self, obj):
        image = obj.main_image
        return thumb(image.image if image else None, 40)


@admin.register(Size)
class SizeAdmin(admin.ModelAdmin):
    list_display = ['name', 'sort_order']
    list_editable = ['sort_order']


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ['swatch', 'name', 'hex_code']
    list_display_links = ['swatch', 'name']

    @admin.display(description='')
    def swatch(self, obj):
        return format_html(
            '<span style="display:inline-block;width:18px;height:18px;border-radius:50%;'
            'background:{};border:1px solid #ccc"></span>', obj.hex_code,
        )


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    fields = ['product_name', 'size', 'color', 'unit_price', 'quantity', 'line_total']
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['number', 'created_at', 'channel', 'full_name', 'phone', 'city', 'total_display', 'status', 'email_sent']
    list_editable = ['status']
    list_filter = ['channel', 'status', 'created_at', 'city']
    search_fields = ['number', 'full_name', 'phone', 'email', 'address']
    date_hierarchy = 'created_at'
    readonly_fields = [
        'number', 'created_at', 'payment_method', 'subtotal', 'promo_code', 'discount',
        'delivery_fee', 'total', 'email_sent', 'user', 'channel', 'recorded_by',
    ]
    inlines = [OrderItemInline]
    fieldsets = [
        ('Order', {'fields': ['number', 'channel', 'created_at', 'status', 'payment_method', 'email_sent', 'recorded_by']}),
        ('Customer', {'fields': ['user', 'full_name', 'phone', 'email', 'city', 'address', 'notes']}),
        ('Totals', {'fields': ['subtotal', 'promo_code', 'discount', 'delivery_fee', 'total']}),
    ]

    @admin.display(description='total', ordering='total')
    def total_display(self, obj):
        return f'{obj.currency}{obj.total}'


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ['code', 'offer', 'min_subtotal', 'usage', 'starts_at', 'ends_at', 'is_active']
    list_editable = ['is_active']
    list_filter = ['is_active', 'kind']
    search_fields = ['code']
    readonly_fields = ['times_used', 'created_at']
    fieldsets = [
        (None, {'fields': ['code', 'is_active']}),
        ('Discount', {'fields': ['kind', 'value', 'min_subtotal']}),
        ('Limits', {'fields': ['starts_at', 'ends_at', 'max_uses', 'times_used']}),
    ]

    @admin.display(description='offer')
    def offer(self, obj):
        return obj.describe(StoreSettings.load().currency)

    @admin.display(description='used')
    def usage(self, obj):
        return f'{obj.times_used} / {obj.max_uses}' if obj.max_uses is not None else obj.times_used


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    fieldsets = [
        ('Delivery & currency', {'fields': ['currency', 'delivery_fee', 'free_delivery_over', 'delivery_time']}),
        ('Homepage', {'fields': ['announcement', 'hero_title', 'hero_subtitle', 'hero_image', 'logo']}),
        ('Contact & social', {'fields': ['phone', 'whatsapp', 'address', 'instagram_url', 'facebook_url', 'tiktok_url']}),
    ]

    def has_add_permission(self, request):
        return not StoreSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
