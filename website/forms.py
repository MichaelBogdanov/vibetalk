from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.utils.translation import gettext_lazy as _
from .models import *

class CustomUserCreationForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].widget.attrs.update({'placeholder': 'Введите вашу электронную почту'})
        self.fields['first_name'].widget.attrs.update({'placeholder': 'Введите ваше имя'})
        self.fields['last_name'].widget.attrs.update({'placeholder': 'Введите вашу фамилию'})
        self.fields['password1'].widget.attrs.update({'placeholder': 'Введите ваш пароль'})
        self.fields['password2'].widget.attrs.update({'placeholder': 'Повторите ваш пароль'})

    class Meta:
        model = CustomUser
        fields = ('email', 'first_name', 'last_name')
        labels = {
            'email': _('Электронная почта'),
            'first_name': _('Имя'),
            'last_name': _('Фамилия'),
        }

class CustomAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'placeholder': 'Введите вашу электронную почту'})
        self.fields['password'].widget.attrs.update({'placeholder': 'Введите ваш пароль'})

    class Meta:
        model = CustomUser
        fields = ('username', 'password')
        labels = {
            'username': _('Электронная почта'),
            'password': _('Пароль'),
        }

class ServerForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs.update({'placeholder': 'Введите название сервера'})
        self.fields['description'].widget.attrs.update({'placeholder': 'Введите описание сервера'})

    class Meta:
        model = Server
        fields = ['name', 'description', 'category', 'photo']

class PostForm(forms.ModelForm):
    class Meta:
        model = ServerPost
        fields = ['title', 'post']

        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Введите заголовок'}),
            'post': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Введите текст поста'}),
        }