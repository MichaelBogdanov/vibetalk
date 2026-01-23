from django.contrib import admin
from .models import *

# Register your models here.
admin.site.register(CustomUser)
admin.site.register(Friendship)
admin.site.register(ServerCategory)
admin.site.register(Server)
admin.site.register(ServerMember)
admin.site.register(Message)
admin.site.register(ServerPost)
admin.site.register(ServerRoom)