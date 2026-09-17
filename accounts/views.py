from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from store.models import Order

from .forms import AddressForm, DetailsForm, LoginForm, SignupForm
from .models import Address


def _safe_next(request):
    url = request.POST.get('next') or request.GET.get('next') or ''
    if url and url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return url
    return ''


def _guest_orders(request):
    """Orders placed as a guest from this browser (tracked by store.views._place_order)."""
    return Order.objects.filter(number__in=request.session.get('placed_orders', []), user__isnull=True)


def claim_guest_orders(request, user):
    """Attach this browser's guest orders to `user` and save the latest delivery address."""
    orders = _guest_orders(request)
    latest = orders.order_by('-created_at').first()
    if latest is None:
        return 0
    Address.remember(user, latest)
    return orders.update(user=user)


class StoreLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if claim_guest_orders(self.request, form.get_user()):
            messages.success(self.request, 'Your recent order was added to your account.')
        return response


def signup(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    latest = _guest_orders(request).order_by('-created_at').first()
    initial = {'full_name': latest.full_name, 'email': latest.email} if latest else {}
    form = SignupForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        message = 'Welcome to Teffaha! Your account is ready.'
        if claim_guest_orders(request, user):
            message += ' Your order and delivery address were saved to it.'
        messages.success(request, message)
        return redirect(_safe_next(request) or 'accounts:dashboard')
    return render(request, 'accounts/signup.html', {'form': form, 'next': _safe_next(request)})


@login_required
def dashboard(request):
    return render(request, 'accounts/dashboard.html', {
        'orders': request.user.orders.prefetch_related('items')[:30],
        'addresses': request.user.addresses.all(),
    })


def _form_page(request, form, title, submit_label):
    return render(request, 'accounts/form_page.html', {
        'form': form, 'title': title, 'submit_label': submit_label, 'next': _safe_next(request),
    })


@login_required
def edit_details(request):
    form = DetailsForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Your details were updated.')
        return redirect('accounts:dashboard')
    return _form_page(request, form, 'Your details', 'Save changes')


class StorePasswordChangeView(PasswordChangeView):
    template_name = 'accounts/form_page.html'
    success_url = reverse_lazy('accounts:dashboard')
    extra_context = {'title': 'Change password', 'submit_label': 'Update password'}

    def form_valid(self, form):
        messages.success(self.request, 'Your password was changed.')
        return super().form_valid(form)


@login_required
def address_form(request, pk=None):
    address = get_object_or_404(Address, pk=pk, user=request.user) if pk else Address(user=request.user)
    form = AddressForm(request.POST or None, instance=address)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Address saved.')
        return redirect(_safe_next(request) or reverse('accounts:dashboard') + '#addresses')
    return _form_page(request, form, 'Edit address' if pk else 'Add an address', 'Save address')


@require_POST
@login_required
def address_delete(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    was_default = address.is_default
    address.delete()
    replacement = request.user.addresses.first()
    if was_default and replacement:
        replacement.save()  # promotes it to the default address
    messages.success(request, 'Address removed.')
    return redirect(reverse('accounts:dashboard') + '#addresses')


@require_POST
@login_required
def address_make_default(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    address.is_default = True
    address.save()
    return redirect(reverse('accounts:dashboard') + '#addresses')


@login_required
def order_detail(request, number):
    order = get_object_or_404(
        Order.objects.prefetch_related('items__product__images__color'), number=number, user=request.user
    )
    return render(request, 'accounts/order_detail.html', {'order': order})
