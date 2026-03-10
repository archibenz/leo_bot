import re

PHONE_PATTERN = re.compile(r"^\+?\d{10,15}$")


def is_valid_phone(phone: str) -> bool:
    return bool(PHONE_PATTERN.match(phone.strip()))
