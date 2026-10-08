import uuid
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TestCase, TransactionTestCase
from django.core.exceptions import ValidationError
from django.urls import reverse
from .consumers import PrivateChatConsumer
from .models import CustomUser, Friendship, Message
from .validators import validate_password, validate_email
from core.asgi import application


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


class MessageHttpIdempotencyTests(TransactionTestCase):
    def setUp(self):
        self.sender = CustomUser.objects.create_user(
            email='http-sender@example.com',
            password='ValidP@ssw0rd',
            first_name='Sender',
            last_name='User',
        )
        self.recipient = CustomUser.objects.create_user(
            email='http-recipient@example.com',
            password='ValidP@ssw0rd',
            first_name='Recipient',
            last_name='User',
        )
        Friendship.objects.create(user_from=self.sender, user_to=self.recipient)
        Friendship.objects.create(user_from=self.recipient, user_to=self.sender)
        self.client.force_login(self.sender)
        self.client_message_id = str(uuid.uuid4())

    def test_repeating_ajax_send_returns_the_same_message(self):
        url = reverse('website:conversation', args=[self.recipient.pk])
        payload = {
            'message': 'Повторный запрос',
            'client_message_id': self.client_message_id,
        }
        headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}

        first_response = self.client.post(url, payload, **headers)
        retry_response = self.client.post(url, payload, **headers)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(retry_response.status_code, 200)
        self.assertEqual(first_response.json()['message_id'], retry_response.json()['message_id'])
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(retry_response.json()['message']['client_message_id'], self.client_message_id)

        history = self.client.get(
            reverse('website:messages_paginated', args=[self.recipient.pk])
        ).json()
        self.assertEqual(history['messages'][0]['client_message_id'], self.client_message_id)

        conflict_response = self.client.post(
            url,
            {'message': 'Другой текст', 'client_message_id': self.client_message_id},
            **headers,
        )
        self.assertEqual(conflict_response.status_code, 409)
        self.assertEqual(Message.objects.count(), 1)


class MessageWebSocketDeliveryTests(TransactionTestCase):
    def setUp(self):
        self.sender = CustomUser.objects.create_user(
            email='ws-sender@example.com',
            password='ValidP@ssw0rd',
            first_name='Sender',
            last_name='User',
        )
        self.recipient = CustomUser.objects.create_user(
            email='ws-recipient@example.com',
            password='ValidP@ssw0rd',
            first_name='Recipient',
            last_name='User',
        )
        Friendship.objects.create(user_from=self.sender, user_to=self.recipient)
        Friendship.objects.create(user_from=self.recipient, user_to=self.sender)
        self.client.force_login(self.sender)
        self.session_cookie = self.client.cookies['sessionid'].value

    async def test_send_broadcasts_persisted_message_and_acknowledges_request(self):
        communicator = WebsocketCommunicator(
            application,
            f'/ws/dm/{self.recipient.pk}/',
            headers=[(b'cookie', f'sessionid={self.session_cookie}'.encode())],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        client_message_id = str(uuid.uuid4())
        await communicator.send_json_to({
            'action': 'send',
            'text': 'Сообщение через WebSocket',
            'client_message_id': client_message_id,
        })
        first_event = await communicator.receive_json_from(timeout=2)
        second_event = await communicator.receive_json_from(timeout=2)
        events = {first_event['event']: first_event, second_event['event']: second_event}

        self.assertIn('message_created', events)
        self.assertIn('message_ack', events)
        self.assertEqual(events['message_created']['message']['id'], events['message_ack']['message']['id'])
        self.assertEqual(events['message_ack']['client_message_id'], client_message_id)
        self.assertEqual(await database_sync_to_async(Message.objects.count)(), 1)
        await communicator.disconnect()
