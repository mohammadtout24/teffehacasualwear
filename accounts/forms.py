from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Q

from store.forms import clean_phone_number

from .models import Address

User = get_user_model()


def email_taken(email, exclude_pk=None):
    users = User.objects.filter(Q(username__iexact=email) | Q(email__iexact=email))
    if exclude_pk:
        users = users.exclude(pk=exclude_pk)
    return users.exists()


def split_name(full_name):
    first, _, last = full_name.strip().partition(' ')
    return first[:150], last.strip()[:150]


class LoginForm(AuthenticationForm):
    """Customers log in with their email (sign-up stores it as the username)."""

    username = forms.EmailField(
        label='Email', widget=forms.EmailInput(attrs={'autofocus': True, 'autocomplete': 'email'})
    )
    password = forms.CharField(
        label='Password', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'})
    )
    error_messages = {
        'invalid_login': 'That email and password don’t match. Please try again.',
        'inactive': 'This account is inactive.',
    }

    def clean_username(self):
        return self.cleaned_data['username'].strip().lower()


class SignupForm(forms.Form):
    full_name = forms.CharField(
        label='Full name', max_length=120, widget=forms.TextInput(attrs={'autocomplete': 'name'})
    )
    email = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={'autocomplete': 'email'}))
    password1 = forms.CharField(
        label='Password', strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text='At least 8 characters — not too common and not only numbers.',
    )
    password2 = forms.CharField(
        label='Confirm password', strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if email_taken(email):
            raise forms.ValidationError('An account with this email already exists. Please log in instead.')
        return email

    def clean(self):
        cleaned = super().clean()
        password1, password2 = cleaned.get('password1'), cleaned.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'The two passwords don’t match.')
        elif password1:
            first, last = split_name(cleaned.get('full_name', ''))
            email = cleaned.get('email', '')
            candidate = User(username=email, email=email, first_name=first, last_name=last)
            try:
                password_validation.validate_password(password1, candidate)
            except forms.ValidationError as error:
                self.add_error('password1', error)
        return cleaned

    def save(self):
        first, last = split_name(self.cleaned_data['full_name'])
        email = self.cleaned_data['email']
        return User.objects.create_user(
            username=email, email=email, password=self.cleaned_data['password1'],
            first_name=first, last_name=last,
        )


class DetailsForm(forms.Form):
    full_name = forms.CharField(
        label='Full name', max_length=120, widget=forms.TextInput(attrs={'autocomplete': 'name'})
    )
    email = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={'autocomplete': 'email'}))

    def __init__(self, *args, user, **kwargs):
        self.user = user
        kwargs.setdefault('initial', {'full_name': user.get_full_name(), 'email': user.email})
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if email_taken(email, exclude_pk=self.user.pk):
            raise forms.ValidationError('Another account already uses this email.')
        return email

    def save(self):
        user, email = self.user, self.cleaned_data['email']
        if user.username.lower() == (user.email or '').lower():
            user.username = email  # accounts created by sign-up log in with their email
        user.email = email
        user.first_name, user.last_name = split_name(self.cleaned_data['full_name'])
        user.save()
        return user


class AddressForm(forms.ModelForm):
    two_columns = True
    full_width = {'address'}

    class Meta:
        model = Address
        fields = ['label', 'full_name', 'phone', 'city', 'address', 'is_default']
        labels = {
            'label': 'Address name (optional)',
            'full_name': 'Full name',
            'phone': 'Phone number',
            'city': 'City / Area',
            'address': 'Full address',
            'is_default': 'Use as my default delivery address',
        }
        help_texts = {'label': ''}
        widgets = {
            'label': forms.TextInput(attrs={'placeholder': 'e.g. Home, Work'}),
            'full_name': forms.TextInput(attrs={'autocomplete': 'name'}),
            'phone': forms.TextInput(attrs={'autocomplete': 'tel', 'inputmode': 'tel'}),
            'city': forms.TextInput(attrs={'autocomplete': 'address-level2'}),
            'address': forms.TextInput(attrs={
                'autocomplete': 'street-address', 'placeholder': 'Street, building, floor, nearby landmark',
            }),
        }

    def clean_phone(self):
        return clean_phone_number(self.cleaned_data['phone'])
