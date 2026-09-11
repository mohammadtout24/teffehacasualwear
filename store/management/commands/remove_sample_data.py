from django.core.management.base import BaseCommand

from store.models import Order, Product, ProductImage


class Command(BaseCommand):
    help = 'Delete all sample products (and their image files). Your own products are kept.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--orders', action='store_true',
            help='Also delete ALL orders (useful to clear test orders before going live).',
        )

    def handle(self, *args, **options):
        images = ProductImage.objects.filter(product__is_sample=True)
        files = 0
        for image in images:
            if image.image:
                image.image.delete(save=False)
                files += 1
        products = Product.objects.filter(is_sample=True)
        count = products.count()
        products.delete()
        self.stdout.write(self.style.SUCCESS(
            f'Removed {count} sample products and {files} image files.'
        ))

        if options['orders']:
            deleted, _ = Order.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'Removed all orders ({deleted} rows).'))
