from django.shortcuts import render
from django.http import HttpResponseForbidden, JsonResponse
from alipay import AliPay
from django.conf import settings
import os

from meiduomall.utils.view import LoginRequiredView
from orders.models import OrderInfo, OrderGoods
from meiduomall.utils.response_code import RETCODE
from .models import Payment
# Create your views here.


class PaymentView(LoginRequiredView):
    """第一个试图， 拼接好支付宝登录连接"""
    def get(self, request, order_id):
        # 验证
        try:
            order = OrderInfo.objects.get(order_id=order_id, user=request.user, status=OrderInfo.ORDER_STATUS_ENUM['UNPAID'])
        except OrderInfo.DoesNotExist:
            return HttpResponseForbidden("此订单错误")

        # 创建支付宝对象
        alipay = AliPay(
            appid=settings.ALIPAY_APPID,
            app_notify_url=None,  # 默认回调函数
            app_private_key_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys/app_private_key.pem'),
            alipay_public_key_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys/alipay_public_key.pem'),
            sign_type="RSA2",
            debug=settings.ALIPAY_DEBUG,

            )

        # 调用它的方法api_alipay_trade_page_pay得到支付链接后面的查询参数部分
        order_string = alipay.api_alipay_trade_page_pay(
            subject='美多商城%s' % order_id,  # subject: 标题， 由美多商城和订单号组成
            out_trade_no=order_id,
            total_amount=str(order.total_amount),  # total_amount是Decimal类型， 此处会报错， 需要转换
            return_url=settings.ALIPAY_RETURN_URL
        )
        # 支付url 拼接 查询参数
        # 沙箱环境链接: 'https://openapi.alipaydev.com/gateway.do' + '?' + order_string
        # 真实环境链接: 'https://openapi.alipay.com/gateway.do' + '?' + order_string
        # 根据js得知需要返回一个alipay_url
        alipay_url = settings.ALIPAY_URL + '?' + order_string  # 支付宝登录支付连接地址
        # 返回
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'alipay_url': alipay_url})


class PaymentStatus(LoginRequiredView):
    """第二类试图， 校验支付结果， 修改订单状态"""
    def get(self, request):
        # 获取查询参数
        query_dict = request.GET
        # 将传过来的数据转成字典
        data = query_dict.dict()
        # 将sign中的键删除, pop删除键返回值
        sign = data.pop('sign')
        # 创建alipay对象
        alipay = AliPay(
            appid=settings.ALIPAY_APPID,
            app_notify_url=None,  # 默认回调函数
            app_private_key_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys/app_private_key.pem'),
            alipay_public_key_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                'keys/alipay_public_key.pem'),
            sign_type="RSA2",
            debug=settings.ALIPAY_DEBUG,

        )
        # 当在显示支付成功的页面重复刷新，会报错， 原因是再刷新即重新请求一遍， 就会把支付成功的信息再保存一遍， 但是trade_id是唯一的， 不能重复， 因此此处要加try
        # 使用verify方法
        success = alipay.verify(data, sign)
        if success:
            order_id = data.get('out_trade_no')
            trade_id = data.get('trade_no')
            # 保存支付宝交易号和订单号
            try:
                Payment.objects.get(order_id=order_id, trade_id=trade_id)
            except Payment.DoesNotExist:
                Payment.objects.create(
                    order_id=order_id,
                    trade_id=trade_id
                )
            # 更改订单信息的数据状态--把未支付改为未评价
                OrderInfo.objects.filter(user=request.user, order_id=order_id, status=OrderInfo.ORDER_STATUS_ENUM['UNPAID']).update(status=OrderInfo.ORDER_STATUS_ENUM['UNCOMMENT'])
            # 返回
            return render(request, 'pay_success.html', {'trade_id': trade_id})
        else:
            return HttpResponseForbidden('请求错误')