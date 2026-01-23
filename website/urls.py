from django.urls import path
from .views import *


app_name = "website"

urlpatterns = [
    path('', me, name='home'),
    path('login/', login_view, name='login'),
    path('register/', register, name='register'),
    path('logout/', logout_view, name='logout'),
    path('servers/', servers, name='servers'),
    path('servers/<int:id>', servers, name='servers'),
    path('search/', search_users, name='search_users'),
    path('add-friend/', add_friend, name='add_friend'),
    path('cancel-friend-request/<int:user_id>/', cancel_friend_request, name='cancel_friend_request'),
    path('conversation/<int:user_id>/talk/', room),
    path('conversation/<int:user_id>/', conversation, name='conversation'),
    path('get_messages/<int:user_id>/', get_messages, name='get_messages'),
    path('api/dm/<int:peer_id>/messages/', messages_paginated, name='messages_paginated'),
    path('message/file/<int:message_id>/', get_message_file, name='get_message_file'),
    path('message/file/<int:message_id>/info/', get_file_info, name='get_file_info'),
    path('server/<int:server_id>/', server, name="server"),
    path('join_server/<int:server_id>/', join_server, name='join_server'),
    path('create_server/', create_server, name='create_server'),
    path('room/<int:room_id>/', room, name='room'),
    path('create_room/', create_room, name='create_room')
]
