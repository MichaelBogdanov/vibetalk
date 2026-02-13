from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.conf import settings
from .validators import validate_password
from django.utils.translation import gettext_lazy as _
import django
from django.utils.translation import gettext
django.utils.translation.ugettext = gettext
from fontawesome_5.fields import IconField
from .storage import PrivateMediaStorage


# Create your models here.
class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Поле электронной почты обязательно')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        return self.create_user(email, password, **extra_fields)

class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(_('электронная почта'), unique=True)
    first_name = models.CharField(_('имя'), max_length=30)
    last_name = models.CharField(_('фамилия'), max_length=30)
    
    password = models.CharField(
        max_length=128,
        validators=[validate_password]
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_friends(self):
        friendships_as_initiator = Friendship.objects.filter(user_from=self)
        friendships_as_acceptor = Friendship.objects.filter(user_to=self)
        friends = []
        for friendship in friendships_as_initiator:
            friend = friendship.user_to
            if any(friendships_as_acceptor.filter(user_from=friend)):
                friends.append(friend)
        return friends

    def get_send_invitations(self):
        invitations = [friendship.user_to for friendship in Friendship.objects.filter(user_from=self) if friendship.user_to not in self.get_friends() and friendship.user_to != self]
        return invitations

    def get_received_invitations(self):
        invitations = [friendship.user_from for friendship in Friendship.objects.filter(user_to=self) if friendship.user_from not in self.get_friends() and friendship.user_from != self]
        return invitations

    class Meta:
        verbose_name = 'пользователя'
        verbose_name_plural = 'Пользователи'

class Friendship(models.Model):
    user_from = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='friendships_from')
    user_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='friendships_to')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user_from} с {self.user_to}'

    class Meta:
        verbose_name = 'заявку в друзья'
        verbose_name_plural = 'Заявки дружбы'

class ServerCategory(models.Model):
    name = models.CharField('Название', unique=True, max_length=128)
    description = models.TextField('Описание', blank=True, max_length=256)
    icon = IconField('Иконка Font Awesome', blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'категорию'
        verbose_name_plural = 'Категории серверов'

class Server(models.Model):
    name = models.CharField('Название', unique=True, max_length=256)
    description = models.TextField('Описание', blank=True, max_length=1024)
    category = models.ForeignKey(ServerCategory, on_delete=models.PROTECT, verbose_name='Категория')
    photo = models.ImageField('Аватарка', upload_to='servers/')
    owner = models.ForeignKey(CustomUser, models.PROTECT)
    is_private = models.BooleanField('Приватность', default=False)

    def __str__(self):
        return ("[Приватный] " if self.is_private else "") + self.name
    
    class Meta:
        verbose_name = 'сервер'
        verbose_name_plural = 'Сервера'

class ServerMember(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, verbose_name='Сервер')
    member = models.ForeignKey(CustomUser, on_delete=models.CASCADE, verbose_name='Участник')

    class Meta:
        verbose_name = 'участника'
        verbose_name_plural = 'Участники серверов'
        unique_together = ('server', 'member')

    def __str__(self):
        return f'{self.server}: {self.member}'

class ServerPost(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, verbose_name='Сервер')
    sender = models.ForeignKey(CustomUser, on_delete=models.CASCADE, verbose_name='Отправитель')
    title = models.CharField('Заголовок поста', max_length=256)
    post = models.TextField('Пост', max_length=1024)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'({self.server.name}) Пост #{self.id} от {self.sender.email}'

    class Meta:
        verbose_name = 'пост'
        verbose_name_plural = 'Посты серверов'
        ordering = ['-timestamp']

class ServerRoom(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, verbose_name='Сервер')

    def __str__(self):
        return f'({self.server.name}) Комната #{self.id}'

    class Meta:
        verbose_name = 'комнату'
        verbose_name_plural = 'Комнаты серверов'

class Message(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_messages')
    message = models.TextField('Сообщение', null=True, max_length=8192)
    timestamp = models.DateTimeField(auto_now_add=True)
    uploaded_file = models.FileField(
        upload_to='chat_files',
        storage=PrivateMediaStorage(),
        null=True,
        blank=True
    )
    original_filename = models.CharField(max_length=255, blank=True, null=True)  # Новое поле

    def save(self, *args, **kwargs):
        # Сохраняем оригинальное имя файла при сохранении
        if self.uploaded_file and not self.original_filename:
            self.original_filename = self.uploaded_file.name
        super().save(*args, **kwargs)

    def __str__(self):
        return ('[Файл]' if self.uploaded_file else '') + f'Сообщение от {self.sender} к {self.recipient} ({self.timestamp})'

    class Meta:
        verbose_name = 'сообщение'
        verbose_name_plural = 'Сообщения'
        indexes = [
            models.Index(fields=['sender', 'recipient', 'id']),
            models.Index(fields=['recipient', 'sender', 'id']),
        ]