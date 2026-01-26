from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Подключение по паре пользователей: ws://.../ws/dm/<peer_user_id>/
    re_path(r"ws/dm/(?P<peer_id>\d+)/?$", consumers.PrivateChatConsumer.as_asgi()),
]
