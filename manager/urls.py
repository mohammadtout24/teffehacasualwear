from django.urls import path

from . import views

app_name = 'manager'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('analytics/', views.analytics_view, name='analytics'),
    path('analytics/orders.csv', views.analytics_export, name='analytics_export'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    path('orders/', views.order_list, name='orders'),
    path('orders/<str:number>/', views.order_detail, name='order'),
    path('orders/<str:number>/status/', views.order_status, name='order_status'),
    path('orders/<str:number>/delete/', views.order_delete, name='order_delete'),

    path('in-store/', views.in_store_list, name='in_store'),
    path('in-store/new/', views.in_store_new, name='in_store_new'),
    path('in-store/product-lookup/', views.product_lookup, name='product_lookup'),
    path('in-store/promo-check/', views.in_store_promo_check, name='in_store_promo_check'),

    path('products/', views.product_list, name='products'),
    path('products/new/', views.product_form, name='product_add'),
    path('products/<int:pk>/', views.product_form, name='product_edit'),
    path('products/<int:pk>/toggle/', views.product_toggle, name='product_toggle'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path('sample-products/remove/', views.remove_sample_products, name='remove_sample_products'),

    path('categories/', views.category_list, name='categories'),
    path('categories/new/', views.category_form, name='category_add'),
    path('categories/<int:pk>/', views.category_form, name='category_edit'),
    path('categories/<int:pk>/toggle/', views.category_toggle, name='category_toggle'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),

    path('promo-codes/', views.promo_list, name='promos'),
    path('promo-codes/new/', views.promo_form, name='promo_add'),
    path('promo-codes/<int:pk>/', views.promo_form, name='promo_edit'),
    path('promo-codes/<int:pk>/toggle/', views.promo_toggle, name='promo_toggle'),
    path('promo-codes/<int:pk>/delete/', views.promo_delete, name='promo_delete'),

    path('customers/', views.customer_list, name='customers'),
    path('customers/<int:pk>/', views.customer_detail, name='customer'),

    path('sizes-and-colors/', views.options, name='options'),
    path('settings/', views.store_settings, name='settings'),
]
