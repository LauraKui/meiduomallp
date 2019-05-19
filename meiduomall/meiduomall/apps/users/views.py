from django.shortcuts import render, redirect, render_to_response
from django.template import RequestContext
from django.urls import reverse
from django.views.generic import View
from django.http import HttpResponseForbidden, JsonResponse
from django.contrib.auth import login, authenticate, logout, mixins
from django_redis import get_redis_connection
from django.db import DatabaseError
from django.core.mail import send_mail
from django.core.paginator import Paginator
import re, random
import logging
import json

from django.conf import settings
from .models import User
from meiduomall.utils.response_code import RETCODE
from celery_tasks.email.tasks import send_verify_mail
from .utils import get_verify_url, check_token
from meiduomall.utils.view import LoginRequiredView
from .models import Address
from goods.models import SKU
from carts.utils import merge_cookie_cart_to_redis
from orders.models import OrderInfo, OrderGoods
from celery_tasks.sms.tasks import ccp_send_sms_code
from verifications.views import SmsCodeView
from verifications import constants

# Create your views here.

# 创建日志输出器对象
logger = logging.getLogger('django')


class Register(View):
    def get(self, request):
        return render(request, "register.html")

    def post(self, request):
        # 接收由表单发送过来的数据， 用post接收，以下6个元素是必须传的
        username = request.POST.get('username')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')
        mobile = request.POST.get('mobile')
        sms_code = request.POST.get('sms_code')
        allow = request.POST.get('allow')
        # 进行验证
        # all()用来验证传入的数据是否齐全，只要是none, False, '', 都表示不全
        #  allow如果勾选是'on'，否则是'None'
        if not all([username, password, password2, mobile, sms_code, allow]):
            return HttpResponseForbidden('输入不能为空')
        # 判断用户名是否符合标准
        if not re.match(r'^[a-zA-Z0-9_-]{5,20}$', username):
            return HttpResponseForbidden('请输入5-20的字符串')
        # 判断密码
        if not re.match(r'^[a-zA-Z0-9]{8,20}$', password):
            return HttpResponseForbidden('请输入8-20位的密码')

        if password2 != password:
            return HttpResponseForbidden('两次密码不相同')
        # 判断手机号
        if not re.match(r'^1[3456789]\d{9}$', mobile):
            return HttpResponseForbidden('请输入有效手机号')
        # 判断短信验证码
        redis_conn = get_redis_connection('verify_code')
        sms_code_server = redis_conn.get('sms: %s' % mobile)
        if sms_code_server is None or sms_code != sms_code_server.decode():
            return HttpResponseForbidden('短信验证码输入不正确')

        try:
            # 创建用户，使用User模型类里面的create_user()方法创建，里面封装了set_password()方法加密密码
            user = User.objects.create_user(
                # 只有此三项需要永久保存在数据库中的
                username=username,
                mobile=mobile,
                password=password

            )
            # 定义一个e对象来接收错误信息的内容
        except DatabaseError as e:
            # 把错误信息保存在日志中
            logger.error(e)
            return render(request, 'register.html', {'register_errmsg': '用户注册失败'})
        # 状态保持
        # 储存用户的id到session中记录它的登陆状态
        login(request, user)
        # 登陆成功重定向到首页
        # return redirect(reverse("contents:index"))
        response = redirect(request.GET.get('next', '/'))
        # 前端通过获取cookie值来取得username, 因此要设置cookie值
        response.set_cookie('username', user.username, max_age=settings.SESSION_COOKIE_AGE)
        return response


class CheckUserView(View):
    def get(self, request, username):
        count = User.objects.filter(username=username).count()
        return JsonResponse({'count': count, 'code': RETCODE.OK, 'errmsg': 'OK'})


class CheckMobileView(View):
    def get(self, request, mobile):
        count = User.objects.filter(mobile=mobile).count()
        return JsonResponse({'count': count, 'code': RETCODE.OK, 'errmsg': 'OK'})


class LoginView(View):
    """用户登录"""

    def get(self, request):
        return render(request, "login.html")

    def post(self, request):
        username = request.POST.get('username')
        password = request.POST.get('password')
        remembered = request.POST.get('remembered')

        if not all([username, password]):
            return HttpResponseForbidden("缺少传入参数")
        user = authenticate(username=username, password=password)
        if user is None:
            return render(request, 'login.html', {'account_errmsg': '用户名或密码错误'})

        login(request, user)


        if remembered != 'on':
            request.session.set_expiry(0)

        response = redirect(request.GET.get('next', '/'))
        # 前端通过获取cookie值来取得username, 因此要设置cookie值
        response.set_cookie('username', user.username, max_age=settings.SESSION_COOKIE_AGE)
        merge_cookie_cart_to_redis(request, user, response)
        return response


class LogoutView(View):
    """推出登录"""

    def get(self, request):
        logout(request)
        response = redirect(reverse("users:login"))
        response.delete_cookie('username')
        return response


class UserInfo(mixins.LoginRequiredMixin, View):
    def get(self, request):
        # 方法1：
        # user = request.user
        # 登录了直接到用户中心
        # if user.is_authenticated:
        #     return render(request, 'user_center_info.html')
        # 如果没有登录， 则跳转到登录页面， 且登录后再自动跳转到用户中心
        # else:
        #     return redirect('/login/?next=/info/')
        # 方法2：
        return render(request, 'user_center_info.html')


class EmailView(mixins.LoginRequiredMixin, View):
    def put(self, request):
        data = json.loads(request.body.decode())
        email = data.get('email')
        if not all([email]):
            return HttpResponseForbidden("缺少邮箱数据")
        if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return HttpResponseForbidden("邮箱格式有误")
        user = request.user
        user.email = email
        user.save()
        # 在此地需要进行邮件发送，异步
        verify_url = get_verify_url(user)
        send_verify_mail.delay(email, verify_url)
        # to_email = email
        # subject = "美多商城邮箱验证"
        # html_message = '<p>尊敬的用户您好！</p>' \
        #                '<p>感谢您使用美多商城。</p>' \
        #                '<p>您的邮箱为：%s 。请点击此链接激活您的邮箱：</p>' \
        #                '<p><a href="%s">%s<a></p>' % (to_email, verify_url, verify_url)
        # send_mail(subject, '', settings.EMAIL_FROM, [to_email], html_message=html_message)

        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})


class VerifyEmailView(View):
    def get(self, request):
        token = request.GET.get('token')
        user = check_token(token)
        if user is None:
            return HttpResponseForbidden('token无效')

        # 修改当前user.email_active=True
        user.email_active = True
        user.save()

        # 响应
        return redirect('/info/')


class AddressView(LoginRequiredView):
    """查数据也在此类视图中"""

    def get(self, request):
        user = request.user
        user_addr = Address.objects.filter(user=user, is_deleted=False)
        addr_list = []
        for addr in user_addr:
            addr_dict = {
                'id': addr.id,
                # 'user': addr.user,
                'title': addr.title,
                'receiver': addr.receiver,
                'province_id': addr.province_id,
                'province': addr.province.name,
                'city_id': addr.city_id,
                'city': addr.city.name,
                'district_id': addr.district_id,
                'district': addr.district.name,

                'place': addr.place,
                'mobile': addr.mobile,
                'tel': addr.tel,
                'email': addr.email
            }
            addr_list.append(addr_dict)
        content = {'addresses': addr_list, 'default_address_id': user.default_address_id}
        # print(content)
        return render(request, 'user_center_site.html', content)


class CreateAddrView(LoginRequiredView):
    def post(self, request):

        user = request.user
        count = Address.objects.filter(is_deleted=False, user=user).count()
        if count >= 20:
            return HttpResponseForbidden("用户收货地址达到上限")
        data_dict = json.loads(request.body.decode())
        title = data_dict.get('title')
        receiver = data_dict.get('receiver')
        province_id = data_dict.get('province_id')
        city_id = data_dict.get('city_id')
        district_id = data_dict.get('district_id')
        place = data_dict.get('place')
        mobile = data_dict.get('mobile')
        tel = data_dict.get('tel')
        email = data_dict.get('email')

        if not all([receiver, province_id, city_id, place, mobile, title]):
            return HttpResponseForbidden("缺少必传参数")
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return HttpResponseForbidden("请输入有效电话号码")
        if tel:
            if not re.match(r'^(0[0-9]{2,3}-)?([2-9][0-9]{6,7})+(-[0-9]{1,4})?$', tel):
                return HttpResponseForbidden('参数tel有误')
        if email:
            if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
                return HttpResponseForbidden('参数email有误')

        try:
            address = Address.objects.create(
                user=user,
                title=title,
                receiver=receiver,
                province_id=province_id,
                city_id=city_id,
                district_id=district_id,
                place=place,
                mobile=mobile,
                tel=tel,
                email=email
            )
            if user.default_address is None:
                user.default_address = address
                user.save()
        except Exception:
            return HttpResponseForbidden("地址错误")
        address_dict = {
            'id': address.id,
            # 'user': address.user,
            'title': address.title,
            'receiver': address.receiver,
            'province': address.province.name,
            'province_id': address.province_id,
            'city': address.city.name,
            'city_id': address.city_id,
            'district': address.district.name,
            'district_id': address.district_id,
            'place': address.place,
            'mobile': address.mobile,
            'tel': address.tel,
            'email': address.email
        }
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'address': address_dict})


class ChangeAddrView(LoginRequiredView):
    """修改和删除数据库"""

    def put(self, request, address_id):
        """修改"""
        # user = request.user
        try:
            address = Address.objects.get(id=address_id)
        except Address.DoesNotExist:
            return HttpResponseForbidden("没有此地址")
        data = json.loads(request.body.decode())

        title = data.get('title')
        receiver = data.get('receiver')
        province_id = data.get('province_id')
        city_id = data.get('city_id')
        district_id = data.get('district_id')
        place = data.get('place')
        mobile = data.get('mobile')
        tel = data.get('tel')
        email = data.get('email')

        if not all([receiver, province_id, city_id, place, mobile, title]):
            return HttpResponseForbidden("缺少必传参数")
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return HttpResponseForbidden("请输入有效电话号码")
        if tel:
            if not re.match(r'^(0[0-9]{2,3}-)?([2-9][0-9]{6,7})+(-[0-9]{1,4})?$', tel):
                return HttpResponseForbidden('参数tel有误')
        if email:
            if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
                return HttpResponseForbidden('参数email有误')

        Address.objects.filter(id=address_id).update(
            title=title,
            receiver=receiver,
            province_id=province_id,
            city_id=city_id,
            district_id=district_id,
            place=place,
            mobile=mobile,
            tel=tel,
            email=email
        )

        address = Address.objects.get(id=address_id)
        address_dict = {
            'id': address.id,
            'title': address.title,
            'receiver': address.receiver,
            'province': address.province.name,
            'province_id': address.province_id,
            'city': address.city.name,
            'city_id': address.city_id,
            'district': address.district.name,
            'district_id': address.district_id,
            'place': address.place,
            'mobile': address.mobile,
            'tel': address.tel,
            'email': address.email
        }
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'address': address_dict})

    def delete(self, request, address_id):
        """删除"""
        try:
            address = Address.objects.get(id=address_id)
        except Address.DoesNotExist:
            return HttpResponseForbidden("没有此地址")

        address.is_deleted = True
        address.save()
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})


class DefaultAddrView(LoginRequiredView):
    def put(self, request, address_id):
        user = request.user
        try:
            address = Address.objects.get(id=address_id)
        except Address.DoesNotExist:
            return HttpResponseForbidden("没有此地址")
        user.default_address = address
        user.save()
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})


class TitleChangeView(LoginRequiredView):
    def put(self, request, address_id):
        try:
            address = Address.objects.get(id=address_id)
        except Address.DoesNotExist:
            return HttpResponseForbidden("没有此地址")
        data = json.loads(request.body.decode())
        title = data.get('title')
        address.title = title
        address.save()
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})


class ModifyPassd(View):
    """修改密码"""
    def get(self, request):
        return render(request, 'user_center_pass.html')

    def post(self, request):
        # 接收请求体参数
        old_pwd = request.POST.get('old_pwd')
        new_pwd = request.POST.get('new_pwd')
        new_cpwd = request.POST.get('new_cpwd')
        # 验证
        if not all([old_pwd, new_pwd, new_cpwd]):
            return HttpResponseForbidden('缺少必传参数')
        user = request.user
        # 判断原密码是否正确
        if user.check_password(old_pwd) is False:
            return render(request, 'user_center_pass.html', {'origin_pwd_errmsg': '原始密码不正确'})
        # 验证新密码是否符合要求
        if not re.match(r'^[0-9A-Za-z]{8,20}$', new_pwd):
            return HttpResponseForbidden('请输入8-12位的密码')
        if new_cpwd != new_pwd:
            return HttpResponseForbidden('两次输入的密码不一致')

        # 修改密码
        user.set_password(new_pwd)
        user.save()

        # 退出登录， 回到登录界面
        logout(request)
        response = redirect('/login/')
        response.delete_cookie('username')
        return response


class HistoryView(View):  # 不mixins的原因：
    """历史浏览记录"""
    def post(self,request):
        """保存历史浏览记录"""
        user = request.user
        if not user.is_authenticated:
            return HttpResponseForbidden('无法查看浏览记录')
        # 接收
        data_dict = json.loads(request.body.decode())
        sku_id = data_dict.get('sku_id')
        # 验证
        try:
            SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return HttpResponseForbidden('没有此商品')

        redis_conn = get_redis_connection('history')
        pl = redis_conn.pipeline()
        # 去重
        pl.lrem('history_%s' % user.id, 0, sku_id)
        # 存储
        pl.lpush('history_%s' % user.id, sku_id)
        # 截取
        pl.ltrim('history_%s' % user.id, 0, 4)

        pl.execute()

        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})

    def get(self, request):
        """查看历史浏览记录"""
        # 从redis中拿数据
        user = request.user
        redis_conn = get_redis_connection('history')

        sku_ids_list = redis_conn.lrange('history_%s' % user.id, 0, -1)

        skus = []
        for sku_id in sku_ids_list:
            sku = SKU.objects.get(id=sku_id)
            history_dict = {
                'id': sku.id,
                'name': sku.name,
                'default_image_url': sku.default_image.url,
                'price': sku.price
                }
            skus.append(history_dict)
        # 返回
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'skus': skus})


class UserOrderInfoView(LoginRequiredView):
    """用户所有订单查看"""
    def get(self, request, page_num):
        user = request.user
        # 查询当前登录用户的所有订单
        order_qs = OrderInfo.objects.filter(user=user).order_by('-create_time')
        for order_model in order_qs:

            # 给每个订单多定义两个属性, 订单支付方式中文名字, 订单状态中文名字
            order_model.pay_method_name = OrderInfo.PAY_METHOD_CHOICES[order_model.pay_method - 1][1]
            order_model.status_name = OrderInfo.ORDER_STATUS_CHOICES[order_model.status - 1][1]
            # 再给订单模型对象定义sku_list属性,用它来包装订单中的所有商品
            order_model.sku_list = []

            # 获取订单中的所有商品
            order_good_qs = order_model.skus.all()
            # 遍历订单中所有商品查询集
            for good_model in order_good_qs:
                sku = good_model.sku  # 获取到订单商品所对应的sku
                sku.count = good_model.count  # 绑定它买了几件
                sku.amount = sku.price * sku.count  # 给sku绑定一个小计总额
                # 把sku添加到订单sku_list列表中
                order_model.sku_list.append(sku)

        # 创建分页器对订单数据进行分页
        # 创建分页对象
        paginator = Paginator(order_qs, 2)
        # 获取指定页的所有数据
        page_orders = paginator.page(page_num)
        # 获取总页数
        total_page = paginator.num_pages

        context = {
            'page_orders': page_orders,
            'page_num': page_num,
            'total_page': total_page
        }

        return render(request,'user_center_order.html',context)
        # return render_to_response( 'user_center_order.html', context)


class FindPassd(View):
    """找回密码视图一"""
    def get(self, request):
        """显示界面"""
        return render(request, 'find_password.html')


class AccountUser(View):
    """找回密码视图二"""
    def get(self, request, username):
        """输入用户名信息"""
        # http: // www.meiduo.site: 8000 / accounts / python / sms / token /?text = fkhs & image_code_id = 89f99980 - a935 - 48 ea - b05a - 99456448f413
        #   (sms, token, text, image_code_id是什么)
        # 接收路径参数用户名和查询字符串--参数验证码id
        uuid = request.GET.get('image_code_id')
        image_code_cli = request.GET.get('text')
        if not all([uuid, image_code_cli]):
            return HttpResponseForbidden('缺少必传参数')
        # 验证--是否有此用户
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return JsonResponse({'message': '没有此用户'})
        # 验证码是否正确
        redis_conn = get_redis_connection('verify_code')
        image_code_server = redis_conn.get('img: %s' % uuid)
        if image_code_server is None or image_code_cli.lower() != image_code_server.decode().lower():
            return JsonResponse({'message': '图形验证码不正确'})
        user_info = {'mobile': user.mobile}
        access_token = json.dumps(user_info)
        mobile = user.mobile[0:3] + '*****' + user.mobile[-3:]
        return JsonResponse({'mobile': mobile, 'access_token': access_token})


class VerifyUser(View):
    """找回密码视图三"""
    def get(self, request):
        """验证用户名"""
        # 接收查询字符串参数access_token
        access_token = request.GET.get('access_token')
        # 验证
        user_info = json.loads(access_token)
        try:
            user = User.objects.get(mobile=user_info['mobile'])
        except User.DoesNotExist:
            return JsonResponse({'data': '用户不存在'})
        # 发送短信验证码
            # 防止用户不停刷新页面重发短信， 规定短信一分钟只能发一次
        redis_conn = get_redis_connection('verify_code')
        pl = redis_conn.pipeline()
        flag = redis_conn.get('get_flag: %s' % user.mobile)
        if flag:
            return JsonResponse({'data': '访问过于频繁'})

        sms_code = '%06d' % random.randint(0, 999999)
        # 打印出sms_code的值
        logger.info(sms_code)
        # 保存短信验证码的值， 便于之后的校验
        pl.setex('sms: %s' % user.mobile, constants.SMS_CODE_REDIS_EXPIRY, sms_code)
        # 发送验证码
        # CCP().send_template_sms(mobile, [sms_code, constants.SMS_CODE_REDIS_EXPIRY // 60], 1)
        pl.setex('get_flag: %s' % user.mobile, constants.SMS_CODE_REDIS_EXPIRY // 5, 1)
        pl.execute()

        ccp_send_sms_code.delay(user.mobile, sms_code)

        return JsonResponse({'message': '短信发送成功'})


class VerifySms(View):
    """找回密码之视图3"""
    def get(self, request, username):
        """验证用户和短信验证码"""
        # 接收查询字符串参数sms_code,
        sms_code = request.GET.get('sms_code')
        # 验证用户名和查询字符串参数
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return JsonResponse({'data': '没有此用户'})
        redis_conn = get_redis_connection('verify_code')
        sms_code_server = redis_conn.get('sms: %s' % user.mobile)
        if sms_code_server is None or sms_code != sms_code_server.decode():
            return JsonResponse({'data': '短信验证码错误'})

        user_info = {'mobile': user.mobile}
        access_token = json.dumps(user_info)
        return JsonResponse({'user_id': user.id, 'access_token': access_token, 'message': 'ok'})


class ChangePassword(View):
    """找回密码之视图4"""
    def post(self, request, user_id):
        """修改密码"""
        json_dict = json.loads(request.body.decode())
        # 请求体获取新密码和再次输入的新密码
        new_password = json_dict.get('password')
        new_password2 = json_dict.get('password2')
        access_token = json_dict.get('access_token')

        if not all([new_password, new_password2, access_token]):
            return JsonResponse({'message': '缺少参数'})
        user_info = json.loads(access_token)
        if not user_info:
            return JsonResponse({'message': '数据错误'})
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse({'data': '没有此用户'})
        # 验证密码是否正则
        if not re.match(r'^[a-zA-Z0-9]{8,20}$', new_password):
            return JsonResponse({'message': '密码格式不正确'})
        # 验证前后密码是否一致
        if new_password2 != new_password:
            return JsonResponse({'message': '前后密码不一致'})
        # 修改密码
        user.set_password(new_password)
        user.save()
        # 重定向到登录界面
        return JsonResponse({'message': 'ok'})
