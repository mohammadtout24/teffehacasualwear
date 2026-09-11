from django.core.management.base import BaseCommand
from django.utils.text import slugify

from store.models import Category, Size

# The store's category structure (from the Teffaha website brief).
# (name, description, [children]) — children use the same shape.
CATEGORY_TREE = [
    ('Women', 'Soft basics, easy sets and statement pieces for every day.', [
        ('Tops', 'Tees, shirts, tanks, fashion tops and cosy hoodies.', [
            ('T-Shirts', '', []),
            ('Shirts', '', []),
            ('Basic Tank Tops', '', []),
            ('Fashion Tops', '', []),
            ('Hoodies', '', []),
        ]),
        ('Bottoms', 'Jeans, leggings and sweatpants that go with everything.', [
            ('Jeans', '', []),
            ('Leggings', '', []),
            ('Sweatpants', '', []),
        ]),
        ('Dresses', 'Effortless dresses from day to evening.', []),
        ('Sets', 'Matching sets — one decision, a whole outfit.', [
            ('Sports Sets', '', []),
            ('Denim Sets', '', []),
            ('Casual Sets', '', []),
        ]),
        ('Jackets & Blazers', 'The finishing layer: tailored blazers and denim jackets.', [
            ('Blazers', '', []),
            ('Jackets & Denim Jackets', '', []),
        ]),
        ('Sportswear', 'Made to move: tops, leggings, sets and jackets for training and rest days.', [
            ('Sports Tops', '', []),
            ('Sports Leggings', '', []),
            ('Sports Sets', '', []),
            ('Sports Jackets', '', []),
        ]),
    ]),
    ('Men', 'Sportswear and polos built for comfort.', [
        ('Sports Tops', '', []),
        ('Sports Sets', '', []),
        ('Sports Jackets', '', []),
        ('Polo Shirts', '', []),
    ]),
]

SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL']


class Command(BaseCommand):
    help = 'Create the Teffaha category tree and standard sizes (safe to run again).'

    def handle(self, *args, **options):
        created = 0

        def build(nodes, parent=None):
            nonlocal created
            for order, (name, description, children) in enumerate(nodes):
                cat, is_new = Category.objects.get_or_create(
                    parent=parent, slug=slugify(name),
                    defaults={'name': name, 'description': description, 'sort_order': order},
                )
                created += is_new
                build(children, cat)

        build(CATEGORY_TREE)
        for order, name in enumerate(SIZES):
            Size.objects.get_or_create(name=name, defaults={'sort_order': order})

        self.stdout.write(self.style.SUCCESS(
            f'Categories ready ({created} created, {Category.objects.count()} total).'
        ))
