import uuid
from datetime import timedelta
from unittest.mock import patch
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import Client, TestCase, TransactionTestCase
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from .consumers import PrivateChatConsumer
from .models import CustomUser, Friendship, Message, ZegoCloudConfiguration
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


class FriendListOrderingTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='owner@example.com',
            password='ValidP@ssw0rd',
            first_name='Owner',
            last_name='User',
        )
        self.old_friend = self._create_friend('old@example.com', 'Old')
        self.active_friend = self._create_friend('active@example.com', 'Active')
        self.new_friend = self._create_friend('new@example.com', 'New')

    def _create_friend(self, email, first_name):
        friend = CustomUser.objects.create_user(
            email=email,
            password='ValidP@ssw0rd',
            first_name=first_name,
            last_name='Friend',
        )
        Friendship.objects.create(user_from=self.user, user_to=friend)
        Friendship.objects.create(user_from=friend, user_to=self.user)
        return friend

    def _set_friendship_activity(self, friend, timestamp):
        Friendship.objects.filter(user_from=self.user, user_to=friend).update(created_at=timestamp)
        Friendship.objects.filter(user_from=friend, user_to=self.user).update(created_at=timestamp)

    def test_friends_are_ordered_by_latest_message_or_friendship_event(self):
        now = timezone.now()
        self._set_friendship_activity(self.old_friend, now - timedelta(days=4))
        self._set_friendship_activity(self.active_friend, now - timedelta(days=5))
        self._set_friendship_activity(self.new_friend, now)

        Message.objects.create(
            sender=self.user,
            recipient=self.old_friend,
            message='Старое сообщение',
        )
        Message.objects.filter(sender=self.user, recipient=self.old_friend).update(
            timestamp=now - timedelta(days=2)
        )
        Message.objects.create(
            sender=self.active_friend,
            recipient=self.user,
            message='Недавнее сообщение',
        )
        Message.objects.filter(sender=self.active_friend, recipient=self.user).update(
            timestamp=now - timedelta(hours=1)
        )

        self.assertEqual(
            [friend.pk for friend in self.user.get_friends()],
            [self.new_friend.pk, self.active_friend.pk, self.old_friend.pk],
        )


class FriendInvitationTests(TestCase):
    def test_received_invitation_is_visible_until_friendship_is_mutual(self):
        owner = CustomUser.objects.create_user(
            email='invitation-owner@example.com',
            password='ValidP@ssw0rd',
            first_name='Owner',
            last_name='User',
        )
        inviter = CustomUser.objects.create_user(
            email='inviter@example.com',
            password='ValidP@ssw0rd',
            first_name='Inviter',
            last_name='User',
        )
        Friendship.objects.create(user_from=inviter, user_to=owner)

        self.assertEqual(owner.get_received_invitations(), [inviter])

        Friendship.objects.create(user_from=owner, user_to=inviter)

        self.assertEqual(owner.get_received_invitations(), [])


class PrivateCallExitTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='caller@example.com',
            password='ValidP@ssw0rd',
            first_name='Caller',
            last_name='User',
        )
        self.peer = CustomUser.objects.create_user(
            email='callee@example.com',
            password='ValidP@ssw0rd',
            first_name='Callee',
            last_name='User',
        )
        Friendship.objects.create(user_from=self.user, user_to=self.peer)
        Friendship.objects.create(user_from=self.peer, user_to=self.user)
        ZegoCloudConfiguration.objects.create(app_id='12345', server_secret='test-secret')
        self.client.force_login(self.user)

    @patch('website.views.generate_token04', return_value='test-token')
    def test_private_call_leave_redirect_returns_to_conversation_page(self, generate_token):
        response = self.client.get(reverse('website:conversation', args=[self.peer.pk]) + 'talk/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['call_config']['logout_redirect'],
            reverse('website:conversation', args=[self.peer.pk]),
        )


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

    def test_repeating_file_upload_with_same_id_stores_one_message(self):
        storage = Message._meta.get_field('uploaded_file').storage
        url = reverse('website:conversation', args=[self.recipient.pk])
        headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}

        with (
            patch.object(storage, 'exists', return_value=False),
            patch.object(storage, '_save', return_value='chat_files/note.txt') as save_file,
            patch.object(storage, 'size', return_value=9),
        ):
            responses = []
            for _ in range(2):
                responses.append(self.client.post(
                    url,
                    {
                        'message': 'Файл в личном чате',
                        'client_message_id': self.client_message_id,
                        'file_upload': SimpleUploadedFile('note.txt', b'file body'),
                    },
                    **headers,
                ))

            self.assertEqual([response.status_code for response in responses], [200, 200])
            self.assertEqual(responses[0].json()['message_id'], responses[1].json()['message_id'])
            self.assertEqual(Message.objects.count(), 1)
            self.assertEqual(save_file.call_count, 1)


class MessageDeleteTests(TransactionTestCase):
    def setUp(self):
        self.sender = CustomUser.objects.create_user(
            email='delete-sender@example.com',
            password='ValidP@ssw0rd',
            first_name='Sender',
            last_name='User',
        )
        self.recipient = CustomUser.objects.create_user(
            email='delete-recipient@example.com',
            password='ValidP@ssw0rd',
            first_name='Recipient',
            last_name='User',
        )
        Friendship.objects.create(user_from=self.sender, user_to=self.recipient)
        Friendship.objects.create(user_from=self.recipient, user_to=self.sender)
        self.client.force_login(self.sender)
        self.message = Message.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message='Удаляемое сообщение',
            uploaded_file='chat_files/attachment.txt',
        )
        self.delete_url = reverse(
            'website:delete_message',
            args=[self.recipient.pk, self.message.pk],
        )

    def test_delete_is_idempotent_hides_message_and_removes_attachment(self):
        storage = Message._meta.get_field('uploaded_file').storage

        with patch.object(storage, 'delete') as delete_file:
            first_response = self.client.post(self.delete_url)
            second_response = self.client.post(self.delete_url)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(second_response.json()['already_deleted'])
        delete_file.assert_called_once_with('chat_files/attachment.txt')

        self.message.refresh_from_db()
        self.assertTrue(self.message.is_deleted)
        self.assertFalse(self.message.uploaded_file)

        history = self.client.get(
            reverse('website:messages_paginated', args=[self.recipient.pk])
        )
        self.assertEqual(history.json()['messages'], [])
        self.assertEqual(
            self.client.get(reverse('website:get_message_file', args=[self.message.pk])).status_code,
            404,
        )

    def test_cannot_delete_a_message_sent_by_the_other_participant(self):
        incoming = Message.objects.create(
            sender=self.recipient,
            recipient=self.sender,
            message='Чужое сообщение',
        )
        url = reverse('website:delete_message', args=[self.recipient.pk, incoming.pk])

        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)
        incoming.refresh_from_db()
        self.assertFalse(incoming.is_deleted)

    def test_storage_failure_leaves_message_available_for_retry(self):
        storage = Message._meta.get_field('uploaded_file').storage

        with patch.object(storage, 'delete', side_effect=OSError('storage unavailable')):
            response = self.client.post(self.delete_url)

        self.assertEqual(response.status_code, 500)
        self.message.refresh_from_db()
        self.assertFalse(self.message.is_deleted)
        self.assertEqual(self.message.uploaded_file.name, 'chat_files/attachment.txt')


class MessageEditTests(TransactionTestCase):
    def setUp(self):
        self.sender = CustomUser.objects.create_user(
            email='edit-sender@example.com',
            password='ValidP@ssw0rd',
            first_name='Sender',
            last_name='User',
        )
        self.recipient = CustomUser.objects.create_user(
            email='edit-recipient@example.com',
            password='ValidP@ssw0rd',
            first_name='Recipient',
            last_name='User',
        )
        Friendship.objects.create(user_from=self.sender, user_to=self.recipient)
        Friendship.objects.create(user_from=self.recipient, user_to=self.sender)
        self.client.force_login(self.sender)
        self.message = Message.objects.create(
            sender=self.sender,
            recipient=self.recipient,
            message='Исходный текст',
        )
        self.edit_url = reverse(
            'website:edit_message',
            args=[self.recipient.pk, self.message.pk],
        )

    def test_sender_can_edit_text_and_history_returns_updated_value(self):
        response = self.client.post(self.edit_url, {
            'message': '  Обновлённый текст  ',
            'expected_message': 'Исходный текст',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['message']['message'], 'Обновлённый текст')
        self.message.refresh_from_db()
        self.assertEqual(self.message.message, 'Обновлённый текст')
        history = self.client.get(
            reverse('website:messages_paginated', args=[self.recipient.pk])
        )
        self.assertEqual(history.json()['messages'][0]['message'], 'Обновлённый текст')

    def test_stale_edit_is_rejected_without_overwriting_newer_text(self):
        self.message.message = 'Новое значение'
        self.message.save(update_fields=['message'])

        response = self.client.post(self.edit_url, {
            'message': 'Устаревшее значение',
            'expected_message': 'Исходный текст',
        })

        self.assertEqual(response.status_code, 409)
        self.message.refresh_from_db()
        self.assertEqual(self.message.message, 'Новое значение')

    def test_cannot_edit_another_participants_message(self):
        incoming = Message.objects.create(
            sender=self.recipient,
            recipient=self.sender,
            message='Чужое сообщение',
        )
        url = reverse('website:edit_message', args=[self.recipient.pk, incoming.pk])

        response = self.client.post(url, {
            'message': 'Подмена',
            'expected_message': 'Чужое сообщение',
        })

        self.assertEqual(response.status_code, 404)
        incoming.refresh_from_db()
        self.assertEqual(incoming.message, 'Чужое сообщение')

    def test_text_cannot_be_cleared_when_message_has_no_file(self):
        response = self.client.post(self.edit_url, {
            'message': '   ',
            'expected_message': 'Исходный текст',
        })

        self.assertEqual(response.status_code, 400)
        self.message.refresh_from_db()
        self.assertEqual(self.message.message, 'Исходный текст')

    def test_editing_caption_keeps_existing_attachment(self):
        self.message.uploaded_file = 'chat_files/edit-attachment.txt'
        self.message.message = 'Подпись'
        self.message.save(update_fields=['uploaded_file', 'message'])

        response = self.client.post(self.edit_url, {
            'message': '',
            'expected_message': 'Подпись',
        })

        self.assertEqual(response.status_code, 200)
        self.message.refresh_from_db()
        self.assertEqual(self.message.message, '')
        self.assertEqual(self.message.uploaded_file.name, 'chat_files/edit-attachment.txt')


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
        message_ids = set()
        for _ in range(2):
            await communicator.send_json_to({
                'action': 'send',
                'text': 'Сообщение через WebSocket',
                'client_message_id': client_message_id,
            })
            received_events = [
                await communicator.receive_json_from(timeout=2),
                await communicator.receive_json_from(timeout=2),
            ]
            events = {event['event']: event for event in received_events}

            self.assertIn('message_created', events)
            self.assertIn('message_ack', events)
            self.assertEqual(events['message_created']['message']['id'], events['message_ack']['message']['id'])
            self.assertEqual(events['message_ack']['client_message_id'], client_message_id)
            message_ids.add(events['message_ack']['message']['id'])

        self.assertEqual(len(message_ids), 1)
        self.assertEqual(await database_sync_to_async(Message.objects.count)(), 1)
        await communicator.disconnect()

    async def test_http_delete_notifies_chat_without_closing_websocket(self):
        message = await database_sync_to_async(Message.objects.create)(
            sender=self.sender,
            recipient=self.recipient,
            message='Удаляемое сообщение',
        )
        communicator = WebsocketCommunicator(
            application,
            f'/ws/dm/{self.recipient.pk}/',
            headers=[(b'cookie', f'sessionid={self.session_cookie}'.encode())],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        response = await database_sync_to_async(self.client.post)(
            reverse('website:delete_message', args=[self.recipient.pk, message.pk])
        )
        self.assertEqual(response.status_code, 200)
        deleted_event = await communicator.receive_json_from(timeout=2)
        self.assertEqual(deleted_event['event'], 'message_deleted')
        self.assertEqual(deleted_event['message_id'], message.pk)

        await communicator.send_json_to({
            'action': 'send',
            'text': 'Сообщение после удаления',
            'client_message_id': str(uuid.uuid4()),
        })
        next_events = {
            (await communicator.receive_json_from(timeout=2))['event'],
            (await communicator.receive_json_from(timeout=2))['event'],
        }
        self.assertEqual(next_events, {'message_created', 'message_ack'})
        await communicator.disconnect()

    async def test_http_edit_broadcasts_updated_message_without_closing_websocket(self):
        message = await database_sync_to_async(Message.objects.create)(
            sender=self.sender,
            recipient=self.recipient,
            message='До изменения',
        )
        sender_communicator = WebsocketCommunicator(
            application,
            f'/ws/dm/{self.recipient.pk}/',
            headers=[(b'cookie', f'sessionid={self.session_cookie}'.encode())],
        )
        recipient_client = Client()
        await database_sync_to_async(recipient_client.force_login)(self.recipient)
        recipient_session_cookie = recipient_client.cookies['sessionid'].value
        recipient_communicator = WebsocketCommunicator(
            application,
            f'/ws/dm/{self.sender.pk}/',
            headers=[(b'cookie', f'sessionid={recipient_session_cookie}'.encode())],
        )
        sender_connected, _ = await sender_communicator.connect()
        recipient_connected, _ = await recipient_communicator.connect()
        self.assertTrue(sender_connected)
        self.assertTrue(recipient_connected)

        response = await database_sync_to_async(self.client.post)(
            reverse('website:edit_message', args=[self.recipient.pk, message.pk]),
            {'message': 'После изменения', 'expected_message': 'До изменения'},
        )
        self.assertEqual(response.status_code, 200)
        sender_edit_event = await sender_communicator.receive_json_from(timeout=2)
        recipient_edit_event = await recipient_communicator.receive_json_from(timeout=2)
        for edited_event in (sender_edit_event, recipient_edit_event):
            self.assertEqual(edited_event['event'], 'message_edited')
            self.assertEqual(edited_event['message']['id'], message.pk)
            self.assertEqual(edited_event['message']['message'], 'После изменения')

        await sender_communicator.send_json_to({
            'action': 'send',
            'text': 'Сообщение после изменения',
            'client_message_id': str(uuid.uuid4()),
        })
        next_events = {
            (await sender_communicator.receive_json_from(timeout=2))['event'],
            (await sender_communicator.receive_json_from(timeout=2))['event'],
        }
        self.assertEqual(next_events, {'message_created', 'message_ack'})
        self.assertEqual(
            (await recipient_communicator.receive_json_from(timeout=2))['event'],
            'message_created',
        )
        await sender_communicator.disconnect()
        await recipient_communicator.disconnect()
