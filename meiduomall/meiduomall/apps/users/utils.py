from django.contrib.auth.backends import ModelBackend
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer,BadData
import re

from .models import User
from django.conf import settings

def get_user_by_account(account):
    try:
        if re.match(r'^[a-zA-Z0-9_-]{5,20}$', account):
            user = User.objects.get(username=account)
        else:
            user = User.objects.get(mobile=account)
    except User.DoesNotExit:
        return None
    else:
        return user


class UsernameMobileAuthBackend(ModelBackend):
    """自定义Django认证后端类"""
    def authenticate(self, request, username=None, password=None, **kwargs):
        user = get_user_by_account(username)

        if user and user.check_password(password):
            return user


def get_verify_url(user):
    # verify_url = 'http://www.meiduo.site:8000/emails/verification/?token=2'
    serializer = Serializer(secret_key=settings.SECRET_KEY, expires_in=3600)
    data = {'user_id': user.id, 'user_email': user.email}
    data_dealed = serializer.dumps(data).decode()
    verify_url = settings.EMAIL_VERIFY_URL + '?token=' + data_dealed
    return verify_url


def check_token(token):

    serializer = Serializer(secret_key=settings.SECRET_KEY, expires_in=3600)
    try:
        data = serializer.loads(token)
    except BadData:
        return None
    else:
        user_id = data.get('user_id')
        user_email = data.get('user_email')

    try:
        user = User.objects.get(id=user_id, email=user_email)
    except User.DoesNotExist:
        return None
    else:
        return user