import uuid
from asgiref.sync import async_to_sync
from django.test import TestCase, TransactionTestCase
from django.core.exceptions import ValidationError
from .consumers import PrivateChatConsumer
from .models import CustomUser, Message
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
            validate_password("PasswordWithoutDigits!")

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


class MessageIdempotencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.sender = CustomUser.objects.create_user(
            email='sender@example.com',
            password='ValidP@ssw0rd',
            first_name='Sender',
            last_name='User',
        )
        self.recipient = CustomUser.objects.create_user(
            email='recipient@example.com',
            password='ValidP@ssw0rd',
            first_name='Recipient',
            last_name='User',
        )
        self.consumer = PrivateChatConsumer()

    def test_retry_with_same_client_id_returns_saved_message(self):
        client_message_id = uuid.uuid4()

        first_message, first_created = async_to_sync(self.consumer._create_message)(
            self.sender.pk,
            self.recipient.pk,
            'Привет',
            client_message_id,
        )
        retry_message, retry_created = async_to_sync(self.consumer._create_message)(
            self.sender.pk,
            self.recipient.pk,
            'Привет',
            client_message_id,
        )

        self.assertTrue(first_created)
        self.assertFalse(retry_created)
        self.assertEqual(retry_message.pk, first_message.pk)
        self.assertEqual(Message.objects.count(), 1)

    def test_reusing_client_id_for_different_message_is_rejected(self):
        client_message_id = uuid.uuid4()
        async_to_sync(self.consumer._create_message)(
            self.sender.pk,
            self.recipient.pk,
            'Первый текст',
            client_message_id,
        )

        conflicting_message, created = async_to_sync(self.consumer._create_message)(
            self.sender.pk,
            self.recipient.pk,
            'Другой текст',
            client_message_id,
        )

        self.assertIsNone(conflicting_message)
        self.assertFalse(created)
        self.assertEqual(Message.objects.count(), 1)
