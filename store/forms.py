import re

from django import forms

from .models import Order


def clean_phone_number(value):
    phone = value.strip()
    digits = re.sub(r'\D', '', phone)
    if len(digits) < 7 or len(digits) > 15:
        raise forms.ValidationError('Please enter a valid phone number.')
    return phone


class CheckoutForm(forms.ModelForm):
    save_address = forms.BooleanField(
        required=False, initial=True, label='Save this address to my account for next time'
    )

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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is None:
            # Guests have no account to save the address to.
            del self.fields['save_address']

    def clean_phone(self):
        return clean_phone_number(self.cleaned_data['phone'])
