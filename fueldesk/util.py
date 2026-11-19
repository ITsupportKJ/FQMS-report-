"""Small helpers shared by every module."""


def clean_card(value) -> str:
    """Normalise a card number: 7700067739.0 / ' 7700067739 ' -> '7700067739'.
    Anything empty or NaN becomes ''."""
    if value is None:
        return ""
    try:
        if value != value:          # NaN
            return ""
    except Exception:               # pd.NA and friends
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def card_problem(card: str):
    """Return a human-readable problem with a card number, or None if fine."""
    if not card:
        return "Card number is empty."
    if not card.isdigit():
        return f"Card number '{card}' must contain digits only."
    if len(card) < 5:
        return f"Card number '{card}' is too short."
    return None


def card_warning(card: str):
    """Soft check: FQMS cards normally have 10 digits."""
    if card.isdigit() and len(card) != 10:
        return f"Card {card} has {len(card)} digits (FQMS cards normally have 10) - check for a typo."
    return None
