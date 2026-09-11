# Teffaha Casual Wear — online store

Django storefront for Teffaha Casual Wear: Women / Men categories, product
pages with sizes & colors, a shopping bag, and **cash-on-delivery checkout**.
Every order is saved in the admin and emailed to **teffehawear@gmail.com**
through [Resend](https://resend.com).

## Run it locally

```bash
python -m venv venv
venv\Scripts\activate            # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env           # then put your Resend API key in .env
python manage.py migrate
python manage.py setup_categories
python manage.py load_sample_data    # optional demo products (see below)
python manage.py createsuperuser
python manage.py runserver
```

- Shop: http://127.0.0.1:8000/
- Admin: http://127.0.0.1:8000/admin/

## Categories

`setup_categories` creates the structure from the website brief:

- **Women** — Tops (T-Shirts, Shirts, Basic Tank Tops, Fashion Tops, Hoodies) ·
  Bottoms (Jeans, Leggings, Sweatpants) · Dresses · Sets (Sports, Denim, Casual) ·
  Jackets & Blazers (Blazers, Jackets & Denim Jackets) ·
  Sportswear (Sports Tops, Sports Leggings, Sports Sets, Sports Jackets)
- **Men** — Sports Tops · Sports Sets · Sports Jackets · Polo Shirts

Categories can be renamed, reordered, hidden or added in **Admin → Categories**.
A product can belong to several categories (e.g. a women's sports set appears
under both *Sets* and *Sportswear*). Parent pages automatically list every
product in their sub-categories.

## Sample data

`load_sample_data` adds 41 demo products with generated illustration photos so
the site looks complete while you prepare real products.

```bash
python manage.py remove_sample_data            # delete demo products + their images
python manage.py remove_sample_data --orders   # ...and delete all (test) orders too
```

Products you add yourself are never touched by `remove_sample_data`.

## Adding products (Admin → Products)

1. Name, price (and optional *original price* to show it as on sale), categories.
2. Pick sizes and colors.
3. Upload photos. Portrait **3:4** photos (e.g. 900×1200) look best. Set each
   photo's *color* so choosing a color on the product page shows that photo.
4. Tick **Best seller** to feature it on the homepage.

## Store settings (Admin → Store settings)

Currency, delivery fee, free-delivery threshold, delivery time, top announcement
bar, homepage title/subtitle/hero image, phone, WhatsApp, Instagram/Facebook/TikTok
links — and **Logo**: upload the logo image there to replace the text logo in
the header.

## Order emails (Resend)

New orders are sent to `ORDER_NOTIFICATION_EMAIL` (default
`teffehawear@gmail.com`) using Resend's HTTP API (`store/emails.py`).

1. Create a Resend account **with teffehawear@gmail.com** and create an API key.
2. Put it in `.env` as `RESEND_API_KEY=...`.

With the default sender `onboarding@resend.dev`, Resend only delivers to the
email address that owns the Resend account — that is why the account should be
created with teffehawear@gmail.com. To send from your own address (e.g.
`orders@teffaha.com`), verify your domain in Resend and set `DEFAULT_FROM_EMAIL`.

If sending fails, the order is still saved; the *Email sent* column in
Admin → Orders shows which orders were emailed. Replying to an order email
replies to the customer when they entered an email address.

## Deploying (e.g. PythonAnywhere)

1. Set `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` in `.env`.
2. `python manage.py migrate && python manage.py collectstatic`
3. Map `/static/` → `staticfiles/` and `/media/` → `media/` in the web app's
   static files settings.
4. Free PythonAnywhere accounts can only reach allowlisted sites — emails go over
   HTTPS to `api.resend.com` (not SMTP), so make sure it is on the allowlist.

## Tests

```bash
python manage.py test store
```
