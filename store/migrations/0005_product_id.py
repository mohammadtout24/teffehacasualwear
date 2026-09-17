import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):
    """Turn the optional SKU into the shop's own Product ID (keeping existing values)."""

    dependencies = [
        ('store', '0004_in_store_sales'),
    ]

    operations = [
        migrations.RenameField(model_name='product', old_name='sku', new_name='code'),
        migrations.AlterField(
            model_name='product',
            name='code',
            field=models.CharField(
                blank=True, max_length=40, verbose_name='product ID',
                help_text='Your own ID for this product, e.g. TW-1042. Used to find it when recording in-store sales.',
            ),
        ),
        migrations.AddConstraint(
            model_name='product',
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower('code'),
                condition=models.Q(('code', ''), _negated=True),
                name='unique_product_code',
                violation_error_message='Another product already uses this ID.',
            ),
        ),
        migrations.AddField(
            model_name='orderitem',
            name='product_code',
            field=models.CharField(blank=True, max_length=40, verbose_name='product ID'),
        ),
    ]
