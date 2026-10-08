from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import (
    CommonPasswordValidator,
    MinimumLengthValidator,
    NumericPasswordValidator,
    UserAttributeSimilarityValidator,
)
import re


# Валидатор электронного адреса
def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        raise ValidationError('Некорректный формат электронной почты')


# Валидатор пароля
def validate_password(value):
    if len(value) < 8:
        raise ValidationError('Пароль должен содержать не менее 8 символов')
    validate_password_characters(value)


def validate_password_characters(value):
    if not re.search(r'\d', value):
        raise ValidationError('Пароль должен содержать хотя бы одну цифру')
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
        raise ValidationError('Пароль должен содержать хотя бы один специальный символ')


class RussianMinimumLengthValidator(MinimumLengthValidator):
    def get_error_message(self):
        return f'Пароль должен содержать не менее {self.min_length} символов'

    def get_help_text(self):
        return self.get_error_message()


class RussianUserAttributeSimilarityValidator(UserAttributeSimilarityValidator):
    def get_error_message(self):
        return 'Пароль слишком похож на ваши личные данные'


class RussianCommonPasswordValidator(CommonPasswordValidator):
    def get_error_message(self):
        return 'Этот пароль часто используют'


class RussianNumericPasswordValidator(NumericPasswordValidator):
    def get_error_message(self):
        return 'Пароль не может состоять только из цифр'


class PasswordRequirementsValidator:
    """Adapt the project's password rules to Django's validator interface."""

    def validate(self, password, user=None):
        validate_password_characters(password)

    def get_help_text(self):
        return 'Пароль должен содержать цифру и специальный символ'
