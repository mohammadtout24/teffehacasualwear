from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.StoreLoginView.as_view(), name='login'),
    path('signup/', views.signup, name='signup'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('details/', views.edit_details, name='details'),
    path('password/', views.StorePasswordChangeView.as_view(), name='password'),
    path('addresses/new/', views.address_form, name='address_add'),
    path('addresses/<int:pk>/edit/', views.address_form, name='address_edit'),
    path('addresses/<int:pk>/delete/', views.address_delete, name='address_delete'),
    path('addresses/<int:pk>/default/', views.address_make_default, name='address_default'),
    path('orders/<str:number>/', views.order_detail, name='order'),
]
