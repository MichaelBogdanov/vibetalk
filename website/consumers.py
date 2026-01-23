import json
import mimetypes
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Message, CustomUser, Friendship
from django.urls import reverse
from django.conf import settings

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
        action = content.get("action")
        
        if action == "send":
            text = content.get("text", "").strip()
            if not text:
                return
            
            # Создаем сообщение в базе
            message = await self._create_message(self.user.id, self.peer_id, text)
            
            # Формируем информацию о файле
            file_info = await self._get_file_info(message)
            
            # Отправляем всем участникам чата
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "chat.event",
                    "event": "message_created",
                    "message": {
                        "id": message.id,
                        "sender": message.sender_id,
                        "recipient": message.recipient_id,
                        "message": message.message,
                        "timestamp": message.timestamp.isoformat(),
                        "file": file_info
                    }
                }
            )

    async def chat_event(self, event):
        await self.send_json(event)

    @database_sync_to_async
    def _is_allowed(self, user_id, peer_id):
        user_fwd = Friendship.objects.filter(user_from_id=user_id, user_to_id=peer_id).exists()
        peer_fwd = Friendship.objects.filter(user_from_id=peer_id, user_to_id=user_id).exists()
        return user_fwd and peer_fwd

    @database_sync_to_async
    def _create_message(self, sender_id, recipient_id, text):
        sender = CustomUser.objects.get(pk=sender_id)
        recipient = CustomUser.objects.get(pk=recipient_id)
        
        message = Message.objects.create(
            sender=sender, 
            recipient=recipient, 
            message=text
        )
        return message

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
            'is_image': mime_type and mime_type.startswith('image/') if mime_type else False
        }