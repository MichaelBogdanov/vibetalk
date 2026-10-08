import json
import mimetypes
import logging
import uuid
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Message, CustomUser, Friendship
from django.urls import reverse
from django.conf import settings
from .storage import INLINE_IMAGE_MIME_TYPES

logger = logging.getLogger(__name__)

def _dm_group_name(user_a_id, user_b_id):
    a = int(user_a_id)
    b = int(user_b_id)
    low, high = (a, b) if a <= b else (b, a)
    return f"dm_{low}_{high}"

class PrivateChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or self.user.is_anonymous:
            await self.close()
            return

        self.peer_id = int(self.scope["url_route"]["kwargs"]["peer_id"])
        peer_exists = await database_sync_to_async(lambda: CustomUser.objects.filter(pk=self.peer_id).exists())()
        if not peer_exists:
            await self.close()
            return

        allowed = await self._is_allowed(self.user.id, self.peer_id)
        if not allowed:
            await self.close()
            return

        self.group_name = _dm_group_name(self.user.id, self.peer_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            return

        action = content.get("action")
        
        if action == "send":
            text = content.get("text")
            if not isinstance(text, str):
                return

            text = text.strip()
            if not text or len(text) > 8192:
                return

            if not await self._is_allowed(self.user.id, self.peer_id):
                await self.close(code=4403)
                return

            raw_client_message_id = content.get("client_message_id")
            if raw_client_message_id is None:
                client_message_id = None
            else:
                try:
                    client_message_id = uuid.UUID(str(raw_client_message_id))
                except (ValueError, TypeError, AttributeError):
                    await self.send_json({
                        "event": "message_error",
                        "client_message_id": raw_client_message_id,
                        "error": "Некорректный идентификатор сообщения",
                    })
                    return
            
            # Создаем сообщение в базе
            message, created = await self._create_message(
                self.user.id,
                self.peer_id,
                text,
                client_message_id,
            )
            if message is None:
                await self.send_json({
                    "event": "message_error",
                    "client_message_id": str(client_message_id),
                    "error": "Идентификатор уже использован для другого сообщения",
                })
                return
            
            # Формируем информацию о файле
            file_info = await self._get_file_info(message)

            message_data = {
                "id": message.id,
                "sender": message.sender_id,
                "recipient": message.recipient_id,
                "message": message.message,
                "timestamp": message.timestamp.isoformat(),
                "file": file_info,
                "client_message_id": str(client_message_id) if client_message_id else None,
            }

            # Повторная отправка с тем же UUID безопасна: получатель увидит тот же
            # сохраненный объект, а клиент сможет убрать зависшую заглушку.
            try:
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        "type": "chat.event",
                        "event": "message_created",
                        "message": message_data,
                    }
                )
            except Exception:
                logger.exception(
                    "Не удалось разослать сообщение %s после сохранения в БД",
                    message.id,
                )

            if client_message_id:
                await self.send_json({
                    "event": "message_ack",
                    "client_message_id": str(client_message_id),
                    "created": created,
                    "message": message_data,
                })

    async def chat_event(self, event):
        await self.send_json(event)

    @database_sync_to_async
    def _is_allowed(self, user_id, peer_id):
        user_fwd = Friendship.objects.filter(user_from_id=user_id, user_to_id=peer_id).exists()
        peer_fwd = Friendship.objects.filter(user_from_id=peer_id, user_to_id=user_id).exists()
        return user_fwd and peer_fwd

    @database_sync_to_async
    def _create_message(self, sender_id, recipient_id, text, client_message_id=None):
        defaults = {
            "recipient_id": recipient_id,
            "message": text,
        }
        if client_message_id is None:
            return Message.objects.create(
                sender_id=sender_id,
                **defaults,
            ), True

        message, created = Message.objects.get_or_create(
            sender_id=sender_id,
            client_message_id=client_message_id,
            defaults=defaults,
        )
        if (
            message.recipient_id != recipient_id
            or message.message != text
            or message.uploaded_file
        ):
            return None, False
        return message, created

    @database_sync_to_async
    def _get_file_info(self, message):
        if not message.uploaded_file:
            return None
        
        mime_type, encoding = mimetypes.guess_type(message.uploaded_file.name)
        
        # Используем абсолютный URL для файла
        file_url = f"{settings.SITE_URL}{reverse('website:get_message_file', args=[message.id])}"
        download_url = f"{file_url}?download=true"
        
        return {
            'url': file_url,
            'download_url': download_url,
            'filename': message.uploaded_file.name.split('/')[-1],
            'size': message.uploaded_file.size,
            'is_image': mime_type in INLINE_IMAGE_MIME_TYPES
        }
