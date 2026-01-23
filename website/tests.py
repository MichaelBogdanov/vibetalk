from django.test import TestCase
from django.core.exceptions import ValidationError
from .validators import validate_password, validate_email


class EmailValidatorTests(TestCase):
    def test_valid_emails(self):
        # Проверяем, что корректные адреса проходят валидацию
        valid_emails = [
            'example@example.com',
            'firstname.lastname@example.co.uk',
            'email+tagging@example.com',
            '1234567890@example.com',
            'email.address-with-dash@example.com'
        ]
        
        for email in valid_emails:
            try:
                validate_email(email)
            except ValidationError:
                self.fail(f'Адрес "{email}" должен быть корректным, но это не так.')

    def test_invalid_emails(self):
        invalid_emails = [
            'plainaddress',
            '#@%^%#$@#$@#.com',
            '@example.com',
            'Joe Smith <email@example.com>',
            'email.example.com',
            'email@example@example.com',
            '.emailexample.com',
            'email.example.com',
            'email..email@examplecom',
            'あいうえお@examplecom',
            'email@-examplecom',
            'email111.222.333.44444',
            'emailexample..com'
        ]
        
        for email in invalid_emails:
            with self.assertRaises(ValidationError):
                validate_email(email)


class PasswordValidatorTests(TestCase):
    def test_valid_password(self):
        # Проверяем, что пароль проходит валидацию
        try:
            validate_password("ValidP@ssw0rd")
        except ValidationError as e:
            self.fail(f"Пароль не прошел валидацию: {e}")

    def test_short_password(self):
        # Проверяем, что короткий пароль вызывает ошибку
        with self.assertRaises(ValidationError):
            validate_password("Short")

    def test_no_digit_password(self):
        # Проверяем, что пароль без цифры вызывает ошибку
        with self.assertRaises(ValidationError):
            validate_password("NoDigitPassword")

    def test_no_special_char_password(self):
        # Проверяем, что пароль без специального символа вызывает ошибку
        with self.assertRaises(ValidationError):
            validate_password("NoSpecialChar123")

    def test_empty_password(self):
        # Проверяем, что пустой пароль вызывает ошибку
        with self.assertRaises(ValidationError):
            validate_password("")

    def test_whitespace_only_password(self):
        # Проверяем, что пароль состоящий только из пробелов вызывает ошибку
        with self.assertRaises(ValidationError):
            validate_password("     ")
