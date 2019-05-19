from django.db import models
from meiduomall.utils.models import BaseModel

# Create your models here.


class OauthQQUser(BaseModel):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, verbose_name='用户')
    openid = models.CharField(max_length=64, verbose_name='openid', db_index=True)

    class Meta:
        db_table = 'tb_oauth_qq'
        verbose_name = 'QQ登录用户数据'
        verbose_name_plural = verbose_name


class SinaUser(BaseModel):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, verbose_name='用户')
    uid = models.CharField(max_length=64, verbose_name='uid', db_index=True)

    class Meta:
        db_table = 'tb_oauth_sina'
        verbose_name = '微博登录用户数据'
        verbose_name_plural = verbose_name