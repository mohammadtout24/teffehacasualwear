from datetime import timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from store import sample_art
from store.models import Category, Color, Product, ProductImage, ProductVariant, Size

COLORS = {
    'Black': '#1f1f1f',
    'White': '#f4f1ea',
    'Cream': '#ece2d0',
    'Beige': '#d9c3a5',
    'Camel': '#b98a5a',
    'Brown': '#7b5a42',
    'Dusty Pink': '#d9a5a0',
    'Burgundy': '#7a1323',
    'Lilac': '#b7a6c9',
    'Sage': '#9fb09a',
    'Olive': '#6b7048',
    'Sky Blue': '#a9c4dc',
    'Navy': '#1f2d4a',
    'Grey Melange': '#a3a3a3',
    'Charcoal': '#3b3b3e',
    'Champagne': '#e3cfa9',
    'Mid Blue': '#4a6a93',
    'Light Wash': '#8fa9c7',
    'Dark Wash': '#2c3e5c',
}

W_SIZES = ['XS', 'S', 'M', 'L', 'XL']
M_SIZES = ['S', 'M', 'L', 'XL', 'XXL']
GOLD = '#c89b4a'

COTTON = 'Soft cotton jersey\nMachine wash cold, inside out\nDo not tumble dry'
STRETCH = '78% polyamide, 22% elastane\nFour-way stretch, squat-proof\nMachine wash cold'
DENIM = '98% cotton, 2% elastane denim\nWash inside out with similar colours\nDo not bleach'
FLEECE = 'Brushed-back cotton fleece\nMachine wash at 30°C\nIron on low heat'

# name, category paths, price, original price, colors, sizes, art kind, extras
PRODUCTS = [
    # Women — Tops
    ('Essential Crew Neck Tee', ['women/tops/t-shirts'], 12, None, ['White', 'Black', 'Dusty Pink'], W_SIZES, 'tee',
     {'featured': True, 'desc': 'The everyday tee you will reach for first. A clean crew neck, soft hand-feel and a relaxed-but-neat fit that tucks or layers easily.', 'details': COTTON}),
    ('Oversized Cotton Tee', ['women/tops/t-shirts'], 15, None, ['Beige', 'Sage', 'Grey Melange'], W_SIZES, 'tee_oversized',
     {'desc': 'Dropped shoulders and a boxy cut for that effortless oversized look. Heavyweight cotton that keeps its shape wash after wash.', 'details': COTTON}),
    ('Classic Poplin Shirt', ['women/tops/shirts'], 24, None, ['White', 'Sky Blue'], W_SIZES, 'shirt',
     {'desc': 'A crisp poplin shirt with a sharp collar and buttoned cuffs. Wear it buttoned up, open over a tank, or knotted at the waist.', 'details': '100% cotton poplin\nMachine wash at 30°C\nIron while slightly damp'}),
    ('Linen Blend Oversized Shirt', ['women/tops/shirts'], 27, 34, ['Beige', 'Olive'], W_SIZES, 'shirt_oversized',
     {'desc': 'Breezy linen-blend shirt with a chest pocket and a curved hem. Light enough for warm days, easy to layer when it cools down.', 'details': '55% linen, 45% cotton\nMachine wash cold\nNaturally creases — that is part of the charm'}),
    ('Ribbed Basic Tank Top', ['women/tops/basic-tank-tops'], 9, None, ['Black', 'White', 'Cream', 'Burgundy'], W_SIZES, 'tank',
     {'featured': True, 'desc': 'A fitted rib-knit tank that works on its own or under everything. Stretchy, soft and the perfect base layer.', 'details': '95% cotton, 5% elastane rib\nMachine wash cold'}),
    ('Scoop Neck Cotton Tank', ['women/tops/basic-tank-tops'], 8, None, ['Grey Melange', 'Dusty Pink', 'Navy'], W_SIZES, 'tank_scoop',
     {'desc': 'A relaxed scoop-neck tank in breathable cotton. Your go-to for hot days and lounging at home.', 'details': COTTON}),
    ('Puff Sleeve Crop Top', ['women/tops/fashion-tops'], 19, None, ['Burgundy', 'Cream', 'Lilac'], W_SIZES, 'puff_top',
     {'featured': True, 'desc': 'Romantic puff sleeves, a square neckline and a smocked stretch body that hugs in all the right places.', 'details': '100% viscose\nHand wash cold\nDry flat'}),
    ('Wrap Front Tie Top', ['women/tops/fashion-tops'], 21, 26, ['Burgundy', 'Black'], W_SIZES, 'wrap_top',
     {'desc': 'A flattering wrap silhouette with long sleeves and a side tie you can cinch as tight as you like.', 'details': '95% polyester, 5% elastane\nMachine wash cold'}),
    ('Everyday Fleece Hoodie', ['women/tops/hoodies'], 29, None, ['Grey Melange', 'Dusty Pink', 'Black'], W_SIZES, 'hoodie',
     {'featured': True, 'desc': 'Our cosiest hoodie: brushed fleece inside, a roomy kangaroo pocket and a lined hood with drawcords.', 'details': FLEECE}),
    ('Cropped Zip Hoodie', ['women/tops/hoodies'], 32, None, ['Sage', 'Cream'], W_SIZES, 'zip_hoodie',
     {'desc': 'A cropped zip-through hoodie that pairs perfectly with high-waisted leggings and joggers.', 'details': FLEECE}),

    # Women — Bottoms
    ('High Rise Straight Jeans', ['women/bottoms/jeans'], 35, None, ['Mid Blue', 'Light Wash', 'Dark Wash'], ['24', '26', '28', '30', '32'], 'jeans',
     {'featured': True, 'accent': GOLD, 'desc': 'A high rise that sits at your natural waist and a straight leg that flatters every shape. Classic five-pocket styling.', 'details': DENIM}),
    ('Wide Leg Jeans', ['women/bottoms/jeans'], 38, 45, ['Light Wash', 'Mid Blue'], ['24', '26', '28', '30', '32'], 'wide_jeans',
     {'accent': GOLD, 'desc': 'Relaxed wide-leg jeans with a full-length hem. Wear them with sneakers now, heels later.', 'details': DENIM}),
    ('Soft Touch Leggings', ['women/bottoms/leggings'], 14, None, ['Black', 'Navy', 'Brown'], W_SIZES, 'leggings',
     {'desc': 'Buttery-soft everyday leggings with a comfortable high waistband that stays put.', 'details': '92% cotton, 8% elastane\nMachine wash cold'}),
    ('Relaxed Jogger Sweatpants', ['women/bottoms/sweatpants'], 22, None, ['Grey Melange', 'Beige', 'Black'], W_SIZES, 'joggers',
     {'desc': 'Classic joggers with an elastic drawstring waist, side pockets and ribbed cuffs.', 'details': FLEECE}),
    ('Wide Leg Sweatpants', ['women/bottoms/sweatpants'], 24, None, ['Dusty Pink', 'Sage', 'Charcoal'], W_SIZES, 'wide_sweats',
     {'desc': 'Lounge-worthy wide-leg sweatpants that still look put together outside the house.', 'details': FLEECE}),

    # Women — Dresses
    ('Satin Slip Midi Dress', ['women/dresses'], 39, None, ['Burgundy', 'Black', 'Champagne'], W_SIZES, 'slip_dress',
     {'featured': True, 'desc': 'A fluid satin slip dress with a soft cowl neckline and adjustable straps. Dress it up with heels or down with a tee underneath.', 'details': '100% polyester satin\nHand wash cold\nSteam, do not iron directly'}),
    ('Cotton T-Shirt Dress', ['women/dresses'], 26, None, ['Black', 'Beige'], W_SIZES, 'tee_dress',
     {'desc': 'All the comfort of your favourite tee in an easy, slightly flared knee-length dress.', 'details': COTTON}),
    ('Tiered Maxi Dress', ['women/dresses'], 42, 52, ['Sage', 'Cream', 'Burgundy'], W_SIZES, 'tiered_dress',
     {'desc': 'A floaty tiered maxi with a smocked bodice and square neckline. Made for sunny days and summer evenings.', 'details': '100% cotton voile\nHand wash cold\nLine dry'}),

    # Women — Sets
    ('Seamless Sports Set', ['women/sets/sports-sets', 'women/sportswear/sports-sets'], 34, None, ['Lilac', 'Black', 'Sage'], W_SIZES, 'sports_bra',
     {'bottom': 'sport_leggings', 'featured': True, 'desc': 'A matching seamless sports bra and high-waist leggings set. Supportive, sculpting and seriously comfortable.', 'details': STRETCH}),
    ('Denim Jacket & Jeans Set', ['women/sets/denim-sets'], 65, None, ['Mid Blue', 'Light Wash'], W_SIZES, 'denim_jacket',
     {'bottom': 'jeans', 'accent': GOLD, 'featured': True, 'desc': 'The full denim look: our classic cropped denim jacket with matching straight-leg jeans. Can be worn together or apart.', 'details': DENIM}),
    ('Denim Shirt & Wide Leg Set', ['women/sets/denim-sets'], 58, 69, ['Light Wash'], W_SIZES, 'denim_shirt',
     {'bottom': 'wide_jeans', 'accent': GOLD, 'desc': 'A relaxed denim shirt and wide-leg jeans in the same light wash for an easy head-to-toe look.', 'details': DENIM}),
    ('Hoodie & Jogger Lounge Set', ['women/sets/casual-sets'], 45, None, ['Grey Melange', 'Dusty Pink', 'Beige'], W_SIZES, 'hoodie',
     {'bottom': 'joggers', 'featured': True, 'desc': 'Our fleece hoodie with matching joggers — the ultimate comfort set for home, travel and weekend errands.', 'details': FLEECE}),
    ('Tee & Wide Pants Set', ['women/sets/casual-sets'], 36, None, ['Cream', 'Black'], W_SIZES, 'tee_oversized',
     {'bottom': 'wide_sweats', 'desc': 'An oversized tee and flowing wide-leg pants in matching jersey. Relaxed, polished and easy.', 'details': COTTON}),

    # Women — Jackets & Blazers
    ('Tailored Single-Button Blazer', ['women/jackets-blazers/blazers'], 55, None, ['Black', 'Beige', 'Burgundy'], W_SIZES, 'blazer',
     {'featured': True, 'desc': 'A sharp single-button blazer with notch lapels and flap pockets. Instantly elevates jeans and a tee.', 'details': '68% polyester, 30% viscose, 2% elastane\nFully lined\nDry clean recommended'}),
    ('Oversized Double-Breasted Blazer', ['women/jackets-blazers/blazers'], 62, 75, ['Camel', 'Cream'], W_SIZES, 'blazer_double',
     {'desc': 'A relaxed, longline double-breasted blazer with structured shoulders.', 'details': '68% polyester, 30% viscose, 2% elastane\nFully lined\nDry clean recommended'}),
    ('Classic Denim Jacket', ['women/jackets-blazers/jackets-denim-jackets'], 42, None, ['Mid Blue', 'Light Wash', 'Black'], W_SIZES, 'denim_jacket',
     {'accent': GOLD, 'desc': 'The denim jacket that goes with everything — chest flap pockets, contrast stitching and a slightly cropped fit.', 'details': DENIM}),
    ('Cropped Bomber Jacket', ['women/jackets-blazers/jackets-denim-jackets'], 48, None, ['Olive', 'Black'], W_SIZES, 'bomber',
     {'accent': '#b98a5a', 'desc': 'A lightweight bomber with ribbed trims, a sleeve pocket and a cropped, boxy fit.', 'details': '100% nylon shell, polyester lining\nMachine wash cold'}),

    # Women — Sportswear
    ('Racerback Sports Bra', ['women/sportswear/sports-tops'], 16, None, ['Black', 'Dusty Pink', 'Sage'], W_SIZES, 'sports_bra',
     {'desc': 'Medium-support sports bra with a racerback, removable pads and a soft elastic underband.', 'details': STRETCH}),
    ('Breathable Training Tee', ['women/sportswear/sports-tops'], 15, None, ['White', 'Lilac'], W_SIZES, 'sport_tee',
     {'desc': 'A quick-dry training tee with raglan sleeves and breathable mesh side panels.', 'details': '100% recycled polyester\nQuick-dry, anti-odour\nMachine wash cold'}),
    ('High-Waist Sculpt Leggings', ['women/sportswear/sports-leggings'], 22, None, ['Black', 'Navy', 'Burgundy'], W_SIZES, 'sport_leggings',
     {'featured': True, 'desc': 'Sculpting high-waist leggings with a wide waistband and contoured seams. Squat-proof and made to move.', 'details': STRETCH}),
    ('Flare Yoga Leggings', ['women/sportswear/sports-leggings'], 24, None, ['Black', 'Brown'], W_SIZES, 'flare_leggings',
     {'desc': 'Figure-hugging through the thigh with a flattering flare from the knee.', 'details': STRETCH}),
    ('Zip Jacket & Leggings Set', ['women/sportswear/sports-sets'], 49, None, ['Black', 'Sage'], W_SIZES, 'track_jacket',
     {'bottom': 'leggings', 'stripes': True, 'desc': 'A fitted zip-up training jacket with matching leggings. Warm-up to cool-down, sorted.', 'details': STRETCH}),
    ('Lightweight Running Jacket', ['women/sportswear/sports-jackets'], 36, None, ['Black', 'Lilac', 'White'], W_SIZES, 'track_jacket',
     {'stripes': True, 'desc': 'A light, stretchy full-zip jacket with a stand collar and zip pockets for your keys.', 'details': '88% polyester, 12% elastane\nMachine wash cold'}),

    # Men
    ("Men's Dri-Fit Training Tee", ['men/sports-tops'], 16, None, ['Black', 'Navy', 'Grey Melange'], M_SIZES, 'men_sport_tee',
     {'desc': 'A lightweight, moisture-wicking tee with raglan sleeves for full range of motion.', 'details': '100% polyester\nQuick-dry\nMachine wash cold'}),
    ("Men's Performance Tank", ['men/sports-tops'], 13, None, ['Black', 'Charcoal', 'White'], M_SIZES, 'men_tank',
     {'desc': 'A breathable training tank with deep armholes to keep you cool on heavy days.', 'details': '100% polyester\nQuick-dry\nMachine wash cold'}),
    ("Men's Track Suit Set", ['men/sports-sets'], 59, None, ['Navy', 'Black'], M_SIZES, 'men_track_jacket',
     {'bottom': 'joggers', 'stripes': True, 'featured': True, 'desc': 'A full-zip track jacket with matching joggers, finished with contrast side stripes.', 'details': '100% polyester tricot\nMachine wash cold'}),
    ("Men's Training Tee & Shorts Set", ['men/sports-sets'], 32, 38, ['Black', 'Grey Melange'], M_SIZES, 'men_sport_tee',
     {'bottom': 'shorts', 'stripes': True, 'desc': 'A matching training tee and drawstring shorts set, ready for the gym or the pitch.', 'details': '100% polyester\nQuick-dry\nMachine wash cold'}),
    ("Men's Hooded Windbreaker", ['men/sports-jackets'], 44, None, ['Black', 'Olive'], M_SIZES, 'windbreaker',
     {'stripes': True, 'desc': 'A lightweight hooded windbreaker with a high collar and zip pockets.', 'details': '100% nylon, water-repellent finish\nMachine wash cold'}),
    ("Men's Full-Zip Track Jacket", ['men/sports-jackets'], 39, None, ['Navy', 'Black', 'Burgundy'], M_SIZES, 'men_track_jacket',
     {'stripes': True, 'desc': 'A retro-inspired track jacket with contrast sleeve stripes and ribbed trims.', 'details': '100% polyester tricot\nMachine wash cold'}),
    ("Men's Classic Piqué Polo", ['men/polo-shirts'], 19, None, ['White', 'Navy', 'Burgundy', 'Black'], M_SIZES, 'polo',
     {'featured': True, 'desc': 'A timeless piqué polo with a ribbed collar, two-button placket and a small embroidered apple.', 'details': '100% cotton piqué\nMachine wash at 30°C'}),
    ("Men's Slim Fit Polo", ['men/polo-shirts'], 21, 26, ['Olive', 'Beige', 'Sky Blue'], M_SIZES, 'polo',
     {'desc': 'A slimmer-cut polo in stretch piqué that keeps its shape all day.', 'details': '95% cotton, 5% elastane piqué\nMachine wash at 30°C'}),
]


def _accent(kind_extras, hex_code):
    if kind_extras.get('accent'):
        return kind_extras['accent']
    if kind_extras.get('stripes'):
        return '#1f1f1f' if sample_art.lum(sample_art.rgb(hex_code)) > .7 else '#f4f1ea'
    return None


class Command(BaseCommand):
    help = 'Load sample products with generated images. Remove them later with remove_sample_data.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Delete existing sample products first.')

    def handle(self, *args, **options):
        call_command('setup_categories', stdout=self.stdout)

        if Product.objects.filter(is_sample=True).exists():
            if not options['reset']:
                self.stdout.write(self.style.WARNING(
                    'Sample products already exist. Use --reset to recreate them.'))
                return
            call_command('remove_sample_data', stdout=self.stdout)

        colors = {}
        for name, hex_code in COLORS.items():
            colors[name], _ = Color.objects.get_or_create(name=name, defaults={'hex_code': hex_code})
        for order, name in enumerate(['24', '26', '28', '30', '32'], start=10):
            Size.objects.get_or_create(name=name, defaults={'sort_order': order})
        sizes = {s.name: s for s in Size.objects.all()}
        categories = {c.path: c for c in Category.objects.all()}

        now = timezone.now()
        total = len(PRODUCTS)
        for index, (name, paths, price, compare, color_names, size_names, kind, extra) in enumerate(PRODUCTS):
            with transaction.atomic():
                product = Product.objects.create(
                    name=name,
                    code=f'TF-{1000 + index}',
                    description=extra.get('desc', ''),
                    details=extra.get('details', ''),
                    price=Decimal(price),
                    compare_at_price=Decimal(compare) if compare else None,
                    is_featured=extra.get('featured', False),
                    is_sample=True,
                )
                product.categories.set([categories[p] for p in paths])
                product.sizes.set([sizes[s] for s in size_names])
                product.colors.set([colors[c] for c in color_names])
                # Varied demo stock, including a few sold-out and "only 1-2 left" options.
                ProductVariant.objects.bulk_create([
                    ProductVariant(product=product, size=sizes[s], color=colors[c],
                                   quantity=(index * 5 + si * 3 + ci * 7) % 12)
                    for si, s in enumerate(size_names) for ci, c in enumerate(color_names)
                ])

                for order, color_name in enumerate(color_names):
                    hex_code = colors[color_name].hex_code
                    jpeg = sample_art.render(
                        kind, hex_code,
                        accent_hex=_accent(extra, hex_code),
                        bottom=extra.get('bottom'),
                        seed=index * 7 + order,
                    )
                    ProductImage.objects.create(
                        product=product,
                        image=ContentFile(jpeg, name=f'sample-{product.slug}-{order + 1}.jpg'),
                        alt=f'{name} in {color_name}',
                        color=colors[color_name],
                        sort_order=order,
                    )
                # Stagger creation times so "New in" has a stable order
                # (earlier entries in the list count as newer).
                Product.objects.filter(pk=product.pk).update(created_at=now - timedelta(hours=index))
            self.stdout.write(f'  [{index + 1}/{total}] {name}')

        self.stdout.write(self.style.SUCCESS(f'Loaded {total} sample products.'))
