from store.models import Order


def manager(request):
    """Badge counts for the store manager's sidebar (manager pages only)."""
    match = getattr(request, 'resolver_match', None)
    if not match or match.app_name != 'manager' or not request.user.is_staff:
        return {}
    return {'new_order_count': Order.objects.filter(status=Order.Status.NEW).count()}
