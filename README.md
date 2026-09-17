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

## Store manager (/manage/)

A friendly back office for running the shop. Log in at `/manage/` with an admin
account (`python manage.py createsuperuser` creates one; email or username both
work). It covers the dashboard, online orders, products (photos, sizes, colors,
categories), categories, promo codes, customers, sizes & colors and store
settings. The classic Django admin is still available at `/admin/`.

### Stock

Every product has a stock count for each size × color, set in the **Stock** table
on the product form (with a "Set every box to" shortcut). Customers never see
the numbers: the shop only says **"Only 1 left" / "Only 2 left"**, crosses out
sold-out sizes and blocks adding more than is available.

- Online orders take their items out of stock when placed. If something sold out
  meanwhile, the order isn't placed and the customer is sent back to their bag.
- In-store sales take their items out of stock too. They're never blocked; if the
  count was lower than what you sold, it goes to 0 and you're asked to recount.
- Cancelling (or deleting) an order puts its items back in stock.
- Products → filters **Running low** and **Out of stock**; the dashboard lists both.
- **For sale** (on the product) marks a product sold out whatever the stock says.

### Analytics

**Analytics** shows how the shop is doing for a chosen period (last 7/30/90 days,
this month, last month, this year or custom dates), for all sales or online / in
store only, compared with the period just before:

- revenue, orders, average order value, items sold, discounts and cancellations;
- sales over time (revenue or orders, online vs in store) and the channel split;
- online orders by status, top products, sales by category, sizes and colors sold;
- busiest weekdays and hours, top delivery cities, promo code results;
- buyers, repeat buyers (matched by phone number) and new customer accounts.

Every chart has hover details and a table view. **Download orders (CSV)** exports
every order in the period for Excel or Google Sheets.

### In-store sales

For purchases made in the physical shop: **In-store sales → Record a sale**.
Type each product's **Product ID** — the ID you enter when adding the product
(required and unique; shown in the Products list) — or search by name, and its photo appears so you can check it's the right
item. Pick size/color/quantity (the price fills in and can be changed), optionally add
a **promo code** (same rules as online; free-delivery codes don't apply in store)
and save.
Sales are saved as paid, count in the dashboard's sales and best sellers, and are kept
separate from online orders.

## Customer accounts

Accounts are optional — guests can always check out. Customers can **sign up /
log in with their email** (person icon in the header) to:

- have checkout filled in from their default address, pick another saved
  address, or tick *Save this address* to keep a new one;
- see their orders and each order's status under **My account**;
- manage saved addresses, their name/email and password.

If someone orders as a guest and then signs up or logs in in the same browser,
that order and its address are added to their account. Customers and their
addresses are in **Admin → Users** (and **Admin → Addresses**); each order shows
the customer account it belongs to.

Password reset by email isn't included yet: it needs a verified sending domain
in Resend, because the default `onboarding@resend.dev` sender can only email the
Resend account owner.

## Promo codes (Admin → Promo codes)

Customers enter a code in the order summary at checkout. Each code gives one of:

- **Percentage off** the bag subtotal (e.g. `10` = 10% off)
- **Fixed amount off** (never more than the subtotal)
- **Free delivery**

Optional limits: minimum order, valid from / until dates, and a total usage
limit. Codes are not case-sensitive, and *used* counts every order placed with
the code. Untick **Active** to switch a code off. The discount never affects
delivery pricing: free delivery is judged on the subtotal before the discount.
The code and discount are shown on the order in the admin and in the order email.

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

## Deploying on Render (free)

`render.yaml` describes everything: a free web service (gunicorn + WhiteNoise)
and a free PostgreSQL database. `build.sh` installs, collects static files,
migrates, creates the categories and the admin account.

1. On render.com: **New → Blueprint**, pick this GitHub repository, **Apply**.
2. It asks for two secrets: `RESEND_API_KEY` and `DJANGO_SUPERUSER_PASSWORD`
   (the password for the `admin` account used at `/manage/`).
3. Every push to `main` redeploys automatically.

Set `LOAD_SAMPLE_DATA=True` in the service's Environment to add the demo products.

Free-plan limits to know:
- The site sleeps after 15 minutes without visitors; the next visit takes ~1 minute.
- The disk is temporary: **photos uploaded in the store manager disappear on the
  next deploy or restart** (sample photos are re-drawn automatically). For real
  product photos, move media to a storage service (e.g. Cloudinary) or a paid disk.
- The free database expires 30 days after it's created (Render emails first) —
  upgrade it or create a new one before then.

## Tests

```bash
python manage.py test store
```
