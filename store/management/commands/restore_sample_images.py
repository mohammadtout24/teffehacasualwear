from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from store import sample_art
from store.management.commands.load_sample_data import PRODUCTS, _accent
from store.models import Product


class Command(BaseCommand):
    help = (
        'Re-draw missing photo files of the sample products. Hosts with a temporary '
        'disk (like Render’s free plan) lose media files on every deploy while the '
        'database keeps the products.'
    )

    def handle(self, *args, **options):
        restored = 0
        for index, (name, _paths, _price, _compare, color_names, _sizes, kind, extra) in enumerate(PRODUCTS):
            product = Product.objects.filter(name=name, is_sample=True).prefetch_related('images__color').first()
            if product is None:
                continue
            for image in product.images.all():
                if not image.image or default_storage.exists(image.image.name):
                    continue
                if not image.color or image.color.name not in color_names:
                    continue
                order = color_names.index(image.color.name)
                jpeg = sample_art.render(
                    kind, image.color.hex_code,
                    accent_hex=_accent(extra, image.color.hex_code),
                    bottom=extra.get('bottom'),
                    seed=index * 7 + order,
                )
                default_storage.save(image.image.name, ContentFile(jpeg))
                restored += 1
        self.stdout.write(self.style.SUCCESS(f'Restored {restored} sample photo files.'))
