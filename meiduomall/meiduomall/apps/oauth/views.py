
from django.shortcuts import render, redirect
from django.views.generic import View
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth import login
from QQLoginTool.QQtool import OAuthQQ
from django_redis import get_redis_connection
import logging
import re

from meiduomall.utils.response_code import RETCODE
from .models import OauthQQUser
from django.conf import settings
from .utils import save_openid, check_openid
from .models import OauthQQUser
from users.models import User
from carts.utils import merge_cookie_cart_to_redis

# Create your views here.

logger = logging.getLogger('django')

class OauthQQ(View):
    def get(self, request):
        next = request.GET.get('next', '/')
        # QQ_CLIENT_ID = '101518219'
        # QQ_CLIENT_SECRET = '418d84ebdc7241efb79536886ae95224'
        # QQ_REDIRECT_URI = 'http://www.meiduo.site:8000/oauth_callback'
        oauth = OAuthQQ(
                    client_id=settings.QQ_CLIENT_ID,
                    client_secret=settings.QQ_CLIENT_SECRET,
                    redirect_uri=settings.QQ_REDIRECT_URI,
                    state=next
                    )
        login_url = oauth.get_qq_url()

        return JsonResponse({'code':RETCODE.OK, 'errmsg': 'OK', 'login_url': login_url})


class OauthCallBack(View):
    def get(self, request):
        code = request.GET.get('code')
        state = request.GET.get('state', '/')
        oauth = OAuthQQ(
            client_id=settings.QQ_CLIENT_ID,
            client_secret=settings.QQ_CLIENT_SECRET,
            redirect_uri=settings.QQ_REDIRECT_URI,
        )

        try:
            access_token = oauth.get_access_token(code)
            openid = oauth.get_open_id(access_token)
        except Exception as e:
            logger.error(e)
            return JsonResponse({'code': RETCODE.SERVERERR, 'errmsg': '服务器发生错误'})

        try:
            oauth_model = OauthQQUser.objects.get(openid=openid)
        except OauthQQUser.DoesNotExist:
            # 没有查到openid, 说明是新用户,先把openid保存在前端的隐藏标签中
            openid = save_openid(openid)
            context = {"openid": openid}
            return render(request, 'oauth_callback.html', context)
        else:
            user = oauth_model.user
            login(request, user)
            response = redirect(state)

            response.set_cookie('username', user.username, max_age=settings.SESSION_COOKIE_AGE)
            merge_cookie_cart_to_redis(request, user, response)
            return response

    def post(self, request):
        mobile = request.POST.get('mobile')
        password = request.POST.get('password')
        sms_code = request.POST.get('sms_code')
        openid = request.POST.get('openid')
        if not all([mobile, password, sms_code, openid]):
            return HttpResponseForbidden("缺少必传参数")
        # 此页面类似注册页面, 所以也要对输入的数据进行校验是否符合要求
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return HttpResponseForbidden("请输入有效的电话号码")
        if not re.match(r'^[a-zA-Z0-9]{8,20}$', password):
            return HttpResponseForbidden("请输入8-20位密码")
        # 由于图形验证码已经在获取短信验证码那里验证过了, 所以下面只要验证短信验证码
        redis_conn = get_redis_connection('verify_code')
        sms_code_server = redis_conn.get('sms: %s' % mobile)
        if sms_code_server is None or sms_code != sms_code_server.decode():
            return HttpResponseForbidden("短信验证码已过期或输入不正确")
        #接下来验证openid

        openid = check_openid(openid)
        if openid is None:
            return HttpResponseForbidden("openid无效")

        # 用手机号查询数据库看是否是新用户
        try:
            user = User.objects.get(mobile=mobile)
        except User.DoesNotExist:
            # 没查到说明是需要注册的新用户
            user = User.objects.create_user(
                username=mobile,
                password=password,
                mobile=mobile
            )
        else:
            if user.check_password(password) is False:
                return HttpResponseForbidden("密码不正确")

        OauthQQUser.objects.create(
            user=user,
            openid=openid
        )
        login(request, user)
        response = redirect(request.GET.get('state'))
        response.set_cookie('username', user.username, max_age=settings.SESSION_COOKIE_AGE)
        merge_cookie_cart_to_redis(request, user, response)
        return response



