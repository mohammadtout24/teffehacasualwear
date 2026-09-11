import re

from django import forms

from .models import Order


class CheckoutForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['full_name', 'phone', 'email', 'city', 'address', 'notes']
        labels = {
            'full_name': 'Full name',
            'phone': 'Phone number',
            'email': 'Email (optional)',
            'city': 'City / Area',
            'address': 'Full address',
            'notes': 'Order notes (optional)',
        }
        widgets = {
            'full_name': forms.TextInput(attrs={'autocomplete': 'name', 'placeholder': 'e.g. Sara Haddad'}),
            'phone': forms.TextInput(attrs={'autocomplete': 'tel', 'inputmode': 'tel', 'placeholder': 'We will call to confirm your order'}),
            'email': forms.EmailInput(attrs={'autocomplete': 'email', 'placeholder': 'you@example.com'}),
            'city': forms.TextInput(attrs={'autocomplete': 'address-level2'}),
            'address': forms.TextInput(attrs={'autocomplete': 'street-address', 'placeholder': 'Street, building, floor, nearby landmark'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Preferred delivery time, gift note…'}),
        }

    def clean_phone(self):
        phone = self.cleaned_data['phone'].strip()
        digits = re.sub(r'\D', '', phone)
        if len(digits) < 7 or len(digits) > 15:
            raise forms.ValidationError('Please enter a valid phone number.')
        return phone
