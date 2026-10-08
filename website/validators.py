from django.core.exceptions import ValidationError
import re


# Валидатор электронного адреса
def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        raise ValidationError('Некорректный формат электронной почты.')


# Валидатор пароля
def validate_password(value):
    if len(value) < 8:
        raise ValidationError('Пароль должен содержать не менее 8 символов.')
    if not re.search(r'\d', value):
        raise ValidationError('Пароль должен содержать хотя бы одну цифру.')
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
        raise ValidationError('Пароль должен содержать хотя бы один специальный символ.')


class PasswordRequirementsValidator:
    """Adapt the project's password rules to Django's validator interface."""

    def validate(self, password, user=None):
        validate_password(password)

    def get_help_text(self):
        return 'Пароль должен содержать не менее 8 символов, цифру и специальный символ.'
