from django.core.files.storage import FileSystemStorage
from django.conf import settings

INLINE_IMAGE_MIME_TYPES = frozenset({
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/avif',
})


class PrivateMediaStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs['location'] = settings.PRIVATE_MEDIA_ROOT
        super().__init__(*args, **kwargs)
        
