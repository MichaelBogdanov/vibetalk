from django.core.files.storage import FileSystemStorage
from django.conf import settings

class PrivateMediaStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs['location'] = settings.PRIVATE_MEDIA_ROOT
        super().__init__(*args, **kwargs)
        
