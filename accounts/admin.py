from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import Address

User = get_user_model()


class AddressInline(admin.TabularInline):
    model = Address
    fields = ['label', 'full_name', 'phone', 'city', 'address', 'is_default']
    extra = 0


admin.site.unregister(User)


@admin.register(User)
class CustomerAdmin(UserAdmin):
    """Django's user admin, plus the customer's saved addresses and order count."""

    inlines = [*UserAdmin.inlines, AddressInline]
    list_display = ['email', 'first_name', 'last_name', 'order_count', 'date_joined', 'is_staff']
    ordering = ['-date_joined']

    @admin.display(description='orders')
    def order_count(self, obj):
        return obj.orders.count()


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'user', 'phone', 'city', 'is_default']
    search_fields = ['full_name', 'phone', 'city', 'address', 'user__email']
    autocomplete_fields = ['user']
