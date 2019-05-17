from django.conf import settings

from itsdangerous import TimedJSONWebSignatureSerializer as Serializer, BadData


def save_openid(openid):
    """把openid通过加密方式保存起来"""
    serializer = Serializer(secret_key=settings.SECRET_KEY, expires_in=600)
    data = {"openid": openid}
    openid_signore = serializer.dumps(data)  # 返回的是byte类型
    return openid_signore.decode()


def check_openid(openid_signore):
    """解密openid"""
    serializer = Serializer(secret_key=settings.SECRET_KEY, expires_in=600)
    try:
        # 解密后的数据类型也是字典， 不是openid
        data = serializer.loads(openid_signore)
    except BadData:
        return None
    return data.get('openid')
