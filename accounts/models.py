from django.conf import settings
from django.db import models

ADDRESS_FIELDS = ('full_name', 'phone', 'city', 'address')


class Address(models.Model):
    """A delivery address saved to a customer account."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='addresses', on_delete=models.CASCADE)
    label = models.CharField(max_length=40, blank=True, help_text='e.g. Home, Work')
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30)
    city = models.CharField('city / area', max_length=80)
    address = models.CharField(max_length=255)
    is_default = models.BooleanField('default address', default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_default', '-created_at']
        verbose_name_plural = 'addresses'

    def __str__(self):
        return f'{self.label or self.city} — {self.full_name}'

    def save(self, *args, **kwargs):
        # A customer with saved addresses always has exactly one default.
        if not Address.objects.filter(user_id=self.user_id, is_default=True).exclude(pk=self.pk).exists():
            self.is_default = True
        super().save(*args, **kwargs)
        if self.is_default:
            Address.objects.filter(user_id=self.user_id, is_default=True).exclude(pk=self.pk).update(is_default=False)

    @classmethod
    def remember(cls, user, source):
        """Save the delivery details of `source` (e.g. an order) unless the
        customer already has an identical address."""
        values = {name: getattr(source, name).strip() for name in ADDRESS_FIELDS}
        match = cls.objects.filter(user=user, **{f'{k}__iexact': v for k, v in values.items()}).first()
        return match or cls.objects.create(user=user, **values)
