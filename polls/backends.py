from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.hashers import check_password
from polls.models import CustomUser

class CustomUserModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = CustomUser.objects.get(username=username)
        except CustomUser.DoesNotExist:
            return None

        if check_password(password, user.password) and self.user_can_authenticate(user):
            return user
