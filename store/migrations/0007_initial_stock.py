from django.db import migrations


def create_stock(apps, schema_editor):
    """Give every existing product a stock row per size × color so the shop
    doesn't suddenly show everything as sold out.

    Sample products get varied demo numbers (a few sold out, some "only 1-2
    left"); any other product starts at 10 of each, to be corrected in the
    store manager.
    """
    Product = apps.get_model('store', 'Product')
    ProductVariant = apps.get_model('store', 'ProductVariant')
    rows = []
    for product in Product.objects.prefetch_related('sizes', 'colors').order_by('pk'):
        if ProductVariant.objects.filter(product=product).exists():
            continue
        sizes = list(product.sizes.all()) or [None]
        colors = list(product.colors.all()) or [None]
        for si, size in enumerate(sizes):
            for ci, color in enumerate(colors):
                quantity = (product.pk * 5 + si * 3 + ci * 7) % 12 if product.is_sample else 10
                rows.append(ProductVariant(product=product, size=size, color=color, quantity=quantity))
    ProductVariant.objects.bulk_create(rows)


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0006_product_stock'),
    ]

    operations = [
        migrations.RunPython(create_stock, migrations.RunPython.noop),
    ]
