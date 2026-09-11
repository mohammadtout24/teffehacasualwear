from django.urls import path

from . import views

app_name = 'store'

urlpatterns = [
    path('', views.home, name='home'),
    path('shop/', views.shop, name='shop'),
    path('new-in/', views.shop, {'collection': 'new'}, name='new_in'),
    path('sale/', views.shop, {'collection': 'sale'}, name='sale'),
    path('search/', views.search, name='search'),
    path('shop/<path:path>/', views.category, name='category'),
    path('product/<slug:slug>/', views.product_detail, name='product'),
    path('bag/', views.cart_detail, name='cart'),
    path('bag/add/<int:product_id>/', views.cart_add, name='cart_add'),
    path('bag/update/', views.cart_update, name='cart_update'),
    path('bag/remove/', views.cart_remove, name='cart_remove'),
    path('checkout/', views.checkout, name='checkout'),
    path('order/<str:number>/', views.order_success, name='order_success'),
]
