
from django.shortcuts import render, redirect
from django.views.generic import View
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth import login
from QQLoginTool.QQtool import OAuthQQ
from django_redis import get_redis_connection
from sinaweibopy3.sinaweibopy3 import APIClient
import logging
import re

from meiduomall.utils.response_code import RETCODE
from .models import OauthQQUser
from django.conf import settings
from .utils import save_openid, check_openid
from .models import OauthQQUser, SinaUser
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

        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'login_url': login_url})


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


class OauthSinaUser(View):
    """微博授权登录"""
    def get(self, request):
        # 点击微博到第三方界面： 带有client_id, client_secret, client_redirect_uri的url
        # 确定next的路径
        # 运用微博SDK中的方法
        # SINA_CLIENT_ID = '2909755640'
        # SINA_CLIENT_SECRET = 'eb2192950073abf631b6c48e98f0bdf1'
        # SINA_REDIRECT_URI = 'http://www.meiduo.site:8000/oauth/sina/user'
        sina = APIClient(
            app_key=settings.SINA_CLIENT_ID,
            app_secret=settings.SINA_CLIENT_SECRET,
            redirect_uri=settings.SINA_REDIRECT_URI,
            )
        authorize_url = sina.get_authorize_url()

        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'authorize_url': authorize_url})


class SinaBack(View):
    """微博回调"""
    def get(self, request):
        """接收回调中的参数， 返回回调页面"""
        # 回到绑定页面时 http: // www.meiduo.site: 8000 / oauth / sina / user?code = 34
        # b11e226f122366816257c6db916d3d

        # 到微博授权登录的时候， 地址url为带着回调地址，client_id的路由

        # 接收参数， 查询字符串参数
        code = request.GET.get('code')
        # 验证
        # 创建对象
        sina = APIClient(
            app_key=settings.SINA_CLIENT_ID,
            app_secret=settings.SINA_CLIENT_SECRET,
            redirect_uri=settings.SINA_REDIRECT_URI,
        )
        # 通过code获取access_token
        result = sina.request_access_token(code)
        access_token = result.access_token
        # uid怎么获取？
        uid = result.uid
        # 查询数据库中是否有uid, 有就重定向到首页， 没有就到注册界面完成简单注册
        try:
            sina_model = SinaUser.objects.get(uid=uid)
        except SinaUser.DoesNotExist:
            # 没有先保存uid, 需要加密
            uid = save_openid(uid)
            context = {"uid": uid, 'access_token': access_token}
            return render(request, 'oauth_callback.html', context)
        else:
            user = sina_model.user
            login(request, user)
            response = redirect('/')

            response.set_cookie('username', user.username, max_age=settings.SESSION_COOKIE_AGE)
            merge_cookie_cart_to_redis(request, user, response)
            return response

    def post(self, request):
        mobile = request.POST.get('mobile')
        password = request.POST.get('password')
        sms_code = request.POST.get('sms_code')
        uid = request.POST.get('uid')
        if not all([mobile, password, sms_code, uid]):
            return HttpResponseForbidden("缺少必传参数")
        # 此页面类似注册页面, 所以也要对输入的数据进行校验是否符合要求
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return HttpResponseForbidden('手机号无效')
        if not re.match(r'^[a-zA-Z0-9]{8,20}$', password):
            return HttpResponseForbidden("请输入8-20位密码")
        # 由于图形验证码已经在获取短信验证码那里验证过了, 所以下面只要验证短信验证码
        redis_conn = get_redis_connection('verify_code')
        sms_code_server = redis_conn.get('sms: %s' % mobile)
        if sms_code_server is None or sms_code != sms_code_server.decode():
            return HttpResponseForbidden("短信验证码已过期或输入不正确")
        #接下来验证openid

        uid = check_openid(uid)
        if uid is None:
            return HttpResponseForbidden("uid无效")

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

        SinaUser.objects.create(
            user=user,
            uid=uid
        )
        login(request, user)
        response = redirect('/')
        response.set_cookie('username', user.username, max_age=settings.SESSION_COOKIE_AGE)
        merge_cookie_cart_to_redis(request, user, response)
        return response


