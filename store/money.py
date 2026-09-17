from decimal import Decimal


def format_money(amount, currency='$'):
    """12 -> "$12", 12.5 -> "$12.50"."""
    amount = Decimal(amount or 0)
    text = f'{amount:,.0f}' if amount == amount.to_integral() else f'{amount:,.2f}'
    return f'{currency}{text}'
