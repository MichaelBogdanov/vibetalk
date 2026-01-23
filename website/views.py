import os
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.http import FileResponse, Http404
from pathlib import Path

from django.urls import reverse
from .forms import *
from .models import *
import mimetypes
from django.utils.text import slugify


# Create your views here.
def login_required(view):
    def wrapper(*args, **kwargs):
        if args[0].user.is_authenticated:
            return view(*args, **kwargs)
        else:
            return redirect('website:login')
    return wrapper

def register(request):
    data = {
        'title': 'Регистрация'
    }
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('website:home')
    else:
        form = CustomUserCreationForm()
    data['form'] = form
    return render(request, 'registration/register.html', data)

def login_view(request):
    data = {
        'title': 'Вход'
    }
    if request.method == 'POST':
        form = CustomAuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('/')
    else:
        form = CustomAuthenticationForm()
    data['form'] = form
    return render(request, 'registration/login.html', data)

def logout_view(request):
    logout(request)
    return redirect('website:login')

@login_required
def index(request):
    data = {
        'my_servers': [elem.server for elem in ServerMember.objects.filter(member=request.user)],
        'title': 'Главная'
    }
    return render(request, "index.html", data)

@login_required
def me(request):
    data = {
        'my_servers': [elem.server for elem in ServerMember.objects.filter(member=request.user)],
        'title': 'Мои сообщения',
        'friends': request.user.get_friends(),
        'send_invitations': request.user.get_send_invitations(),
        'received_invitations': request.user.get_received_invitations()
    }
    return render(request, "me.html", data)

@login_required
def servers(request, id=None):
    data = {
        'my_servers': [elem.server for elem in ServerMember.objects.filter(member=request.user)],
        'title': 'Сервера',
        'servers': [i for i in Server.objects.all() if not ServerMember.objects.filter(server=i, member=request.user) and not i.is_private],
        'server_categories': ServerCategory.objects.all(),
        'selected_category': id
    }
    if id:
        data['servers'] = [server for server in data['servers'] if server.category == id]
    return render(request, "servers.html", data)

@login_required
def search_users(request):
    if request.method == 'GET' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        query = request.GET.get('q')
        if query:
            # Поиск пользователей по имени или фамилии
            users = CustomUser.objects.filter(Q(email__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query)).exclude(pk=request.user.pk)
            results = []
            for user in users:
                if user not in request.user.get_friends() and \
                user not in request.user.get_send_invitations() and \
                request.user not in user.get_send_invitations():
                    results.append({'id': user.id, 'name': f'{user.first_name} {user.last_name}', 'email': user.email})
            return JsonResponse(results, encoder=DjangoJSONEncoder, safe=False)
    return JsonResponse({}, safe=False)

@login_required
def add_friend(request):
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        user_id = request.POST.get('user_id')
        if user_id:
            try:
                user_to = CustomUser.objects.get(pk=user_id)
                user_from = request.user
                Friendship.objects.create(user_from=user_from, user_to=user_to)
                return JsonResponse({'status': 'ok'})
            except CustomUser.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Пользователь не найден'})
    return JsonResponse({'status': 'error', 'message': 'Неверный метод запроса'})

@login_required
def cancel_friend_request(request, user_id):
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            friendship = Friendship.objects.get(user_from=request.user, user_to_id=user_id)
            friendship.delete()
            return JsonResponse({'message': 'Заявка успешно отменена'}, status=200)
        except Friendship.DoesNotExist:
            return JsonResponse({'error': 'Не найдена заявка на дружбу'}, status=404)
    return JsonResponse({'status': 'error', 'message': 'Неверный метод запроса'})

@login_required
def messages_paginated(request, peer_id):
    user = request.user
    try:
        peer = CustomUser.objects.get(pk=peer_id)
    except CustomUser.DoesNotExist:
        return JsonResponse({'error': 'Пользователь не найден'}, status=404)

    # проверка прав (взаимная дружба)
    if not (Friendship.objects.filter(user_from=user, user_to=peer).exists() and
            Friendship.objects.filter(user_from=peer, user_to=user).exists()):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    limit = min(int(request.GET.get('limit', 100)), 500)
    before = request.GET.get('before', None)

    qs = Message.objects.filter(
        (Q(sender=user) & Q(recipient=peer)) | (Q(sender=peer) & Q(recipient=user))
    )
    
    if before:
        qs = qs.filter(id__lt=int(before))

    messages = list(qs.order_by('-id')[:limit])
    messages.reverse()

    data = []
    for m in messages:
        # Формируем информацию о файле
        file_info = None
        if m.uploaded_file:
            mime_type, encoding = mimetypes.guess_type(m.uploaded_file.name)
            file_info = {
                'url': reverse('website:get_message_file', args=[m.id]),
                'filename': m.uploaded_file.name.split('/')[-1],
                'size': m.uploaded_file.size,
                'is_image': mime_type and mime_type.startswith('image/') if mime_type else False
            }
        
        data.append({
            'id': m.id,
            'sender': m.sender_id,
            'message': m.message,
            'timestamp': m.timestamp.isoformat(),
            'file': file_info  # Используем объект, а не строку
        })

    return JsonResponse({'messages': data})

@login_required
def get_messages(request, user_id):
    messages = Message.objects.filter(
        (Q(sender=request.user) & Q(recipient=user_id)) |
        (Q(sender=user_id) & Q(recipient=request.user))
    ).order_by('timestamp')

    messages_data = []
    for message in messages:
        # Формируем информацию о файле
        file_info = None
        if message.uploaded_file:
            mime_type, encoding = mimetypes.guess_type(message.uploaded_file.name)
            file_info = {
                'url': reverse('website:get_message_file', args=[message.id]),
                'filename': message.uploaded_file.name.split('/')[-1],
                'size': message.uploaded_file.size,
                'is_image': mime_type and mime_type.startswith('image/') if mime_type else False
            }
        
        messages_data.append({
            'id': message.id,
            'sender': message.sender.id,
            'message': message.message,
            'timestamp': message.timestamp.isoformat(),
            'file': file_info  # Используем объект, а не строку
        })

    return JsonResponse({'messages': messages_data})

@login_required
def conversation(request, user_id):
    if request.method == 'POST':
        recipient_id = request.POST.get('recipient')
        message_text = request.POST.get('message')
        uploaded_file = request.FILES.get('file_upload')
        
        recipient = CustomUser.objects.get(id=recipient_id)
        message = Message(
            sender=request.user,
            recipient=recipient,
            message=message_text,
            uploaded_file=uploaded_file,
        )
        
        # Сохраняем оригинальное имя файла
        if uploaded_file:
            message.original_filename = uploaded_file.name
        
        message.save()
        
        # Отправляем уведомление через WebSocket
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        
        channel_layer = get_channel_layer()
        group_name = _dm_group_name(request.user.id, recipient_id)
        
        # Формируем информацию о файле
        file_info = None
        if message.uploaded_file:
            mime_type, _ = mimetypes.guess_type(message.uploaded_file.name)
            file_info = {
                'url': f"{reverse('website:get_message_file', args=[message.id])}",
                'download_url': f"{reverse('website:get_message_file', args=[message.id])}?download=true",
                'filename': message.uploaded_file.name.split('/')[-1],
                'size': message.uploaded_file.size,
                'is_image': mime_type and mime_type.startswith('image/') if mime_type else False
            }
        
        # Отправляем событие через WebSocket
        async_to_sync(channel_layer.group_send)(
            group_name,
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
        
        # Если это AJAX запрос, возвращаем JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'ok', 
                'message_id': message.id,
                'file_info': file_info
            })
        
        return redirect('website:conversation', user_id=recipient_id)
    
    # GET запрос
    friend = CustomUser.objects.get(id=user_id)
    if not Friendship.objects.filter(user_from=request.user, user_to=friend).exists():
        return HttpResponseForbidden()
    
    data = {
        'my_servers': [elem.server for elem in ServerMember.objects.filter(member=request.user)],
        'title': f'Чат: {friend.first_name} {friend.last_name}',
        'friends': request.user.get_friends(),
        'friend': friend,
    }
    return render(request, 'conversation.html', data)

def _dm_group_name(user_a_id, user_b_id):
    """Генерация имени группы для WebSocket"""
    a = int(user_a_id)
    b = int(user_b_id)
    low, high = (a, b) if a <= b else (b, a)
    return f"dm_{low}_{high}"

@login_required
def get_message_file(request, message_id):
    try:
        from .models import Message
        msg = Message.objects.get(id=message_id)
    except Message.DoesNotExist:
        raise Http404("Файл не найден")

    # Проверяем, что пользователь — участник диалога
    if request.user != msg.sender and request.user != msg.recipient:
        raise Http404("Файл не найден")

    # Проверяем, что есть файл
    if not msg.uploaded_file:
        raise Http404("Файл не найден")

    try:
        # Полный путь к файлу
        file_path = os.path.join(settings.PRIVATE_MEDIA_ROOT, msg.uploaded_file.name)
        
        # Проверяем существование файла
        if not os.path.exists(file_path):
            raise Http404("Файл не найден на диске")
        
        # Определяем MIME-тип
        mime_type, encoding = mimetypes.guess_type(file_path)
        
        # Открываем файл
        file = open(file_path, 'rb')
        
        # Создаем response
        response = FileResponse(file)
        
        # Устанавливаем Content-Type
        if mime_type:
            response['Content-Type'] = mime_type
        
        # Используем оригинальное имя файла, если оно сохранено
        if msg.original_filename:
            filename = msg.original_filename
        else:
            # Иначе пытаемся извлечь из пути
            filename = os.path.basename(msg.uploaded_file.name)
            # Пытаемся восстановить оригинальное имя
            if '_' in filename:
                parts = filename.split('_')
                if len(parts) > 1 and '.' in parts[-1]:
                    filename = parts[-1]
        
        # Очищаем имя файла от специальных символов
        import urllib.parse
        filename = urllib.parse.quote(filename)
        
        # Если это не изображение или запрошено скачивание - отдаем как вложение
        if not mime_type or not mime_type.startswith('image/') or request.GET.get('download'):
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
        else:
            response['Content-Disposition'] = f'inline; filename="{filename}"'
        
        return response
    except Exception as e:
        print(f"Ошибка при загрузке файла: {e}")
        raise Http404("Ошибка при загрузке файла")

@login_required
def get_file_info(request, message_id):
    """Возвращает информацию о файле для фронтенда"""
    try:
        msg = Message.objects.get(id=message_id)
    except Message.DoesNotExist:
        return JsonResponse({'error': 'Файл не найден'}, status=404)

    # Проверяем, что пользователь — участник диалога
    if request.user != msg.sender and request.user != msg.recipient:
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)

    if not msg.uploaded_file:
        return JsonResponse({'error': 'Файл не найден'}, status=404)

    file_path = Path(settings.PRIVATE_MEDIA_ROOT) / msg.uploaded_file.name
    mime_type, encoding = mimetypes.guess_type(str(file_path))
    
    filename = msg.uploaded_file.name.split('/')[-1]
    
    return JsonResponse({
        'filename': filename,
        'is_image': mime_type and mime_type.startswith('image/'),
        'mime_type': mime_type,
        'size': msg.uploaded_file.size,
        'url': reverse('website:get_message_file', args=[message_id]),
        'download_url': f"{reverse('website:get_message_file', args=[message_id])}?download=true"
    })

@login_required
def server(request, server_id):
    # Получаем текущий сервер
    try:
        server = Server.objects.get(id=server_id)
    except Server.DoesNotExist:
        return HttpResponse("Сервер не найден")
    
    # Проверяем, является ли пользователь участником этого сервера
    if not ServerMember.objects.filter(server=server, member=request.user).exists():
        return HttpResponse("Вы не являетесь участником данного сервера")

    # Обрабатываем POST-запрос
    if request.method == 'POST':
        form = PostForm(request.POST)
        if form.is_valid():
            new_post = form.save(commit=False)
            new_post.server = server
            new_post.sender = request.user
            new_post.save()
            return redirect(f'/server/{server.id}/')  # Переадресация на страницу сервера после создания поста
    else:
        form = PostForm()
    data = {
        'my_servers': [elem.server for elem in ServerMember.objects.filter(member=request.user)],
        'server': Server.objects.get(id=server_id),
        'form': form
    }
    data['title'] = data['server'].name
    data['posts'] = ServerPost.objects.filter(server=data['server'])
    data['rooms'] = ServerRoom.objects.filter(server=data['server'])
    return render(request, 'server.html', data)

@login_required
def join_server(request, server_id):
    if request.method == 'POST':
        try:
            server = Server.objects.get(id=server_id)
        except Server.DoesNotExist:
            return redirect('website:servers')  # перенаправление на страницу ошибки

        user = request.user
        
        # Проверяем, уже является ли пользователь участником данного сервера
        if not ServerMember.objects.filter(member=user, server=server).exists():
            participant = ServerMember(member=user, server=server)
            participant.save()
            
            # Перенаправляем на страницу успеха
            return redirect(f'/server/{server.id}')
    
    # Если был GET-запрос или ошибка при добавлении участника, перенаправляем обратно
    return redirect('website:servers')

@login_required
def create_server(request):
    if request.method == 'POST':
        form = ServerForm(request.POST, request.FILES)
        if form.is_valid():
            new_server = form.save(commit=False)
            new_server.owner = request.user
            new_server.save()
            join_server(request, new_server.id)
            return redirect('website:server', new_server.id)
    else:
        form = ServerForm()
    
    context = {
        'my_servers': [elem.server for elem in ServerMember.objects.filter(member=request.user)],
        'form': form,
    }
    return render(request, 'create_server.html', context)

@login_required
def create_room(request):
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        server = Server.objects.get(id=request.POST.get('server_id'))
        if server:
            try:
                ServerRoom.objects.create(server=server)
                return JsonResponse({'status': 'ok'})
            except CustomUser.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Сервер не найден'})
    return JsonResponse({'status': 'error', 'message': 'Неверный метод запроса'})

@login_required
def room(request, room_id=None, user_id=None):
    data = {
        'AppID': settings.ZEGOCLOUD_APPID,
        'ServerSecret': settings.ZEGOCLOUD_SERVERSECRET
    }
    if room_id:
        # Если пользователь участник сервера
        server = ServerRoom.objects.get(id=room_id).server
        if not ServerMember.objects.filter(server=server, member=request.user).exists():
            return HttpResponse('Вы не можете присоединиться к данному разговору')
        data['room'] = ServerRoom.objects.get(id=room_id).id
        data['logout_redirect'] = f"/server/{server.id}"
        data['title'] = server.name
    else:
        # Если пользователи друзья
        if not (Friendship.objects.filter(user_from=request.user, user_to=CustomUser.objects.get(id=user_id)).exists() and Friendship.objects.filter(user_from=CustomUser.objects.get(id=user_id), user_to=request.user).exists()):
            return HttpResponse('Вы не можете присоединиться к данному разговору')
        data['room'] = "_".join(sorted([request.user.email, CustomUser.objects.get(id=user_id).email]))
        data['logout_redirect'] = f'/conversation/{user_id}'
        data['title'] = f"Разговор: {CustomUser.objects.get(id=user_id)}"
    return render(request, 'room.html', data)

