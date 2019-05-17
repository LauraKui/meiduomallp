from django.shortcuts import render
from django.views.generic import View
from django_redis import get_redis_connection
from decimal import Decimal
from django.http import HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.db import transaction
import json

from meiduomall.utils.view import LoginRequiredView
from users.models import Address
from goods.models import SKU
from .models import OrderGoods, OrderInfo
from meiduomall.utils.response_code import RETCODE


class OrdersSettle(LoginRequiredView):
    """结算订单"""
    def get(self, request):

        user = request.user
        # 获取当前用户的所有收获地址
        addresses = Address.objects.filter(user=user, is_deleted=False)
        addresses = addresses if addresses.exists() else None
        # 连接redis
        redis_conn = get_redis_connection('carts')
        carts_data = redis_conn.hgetall('carts_%s' % user.id)
        selected_skus = redis_conn.smembers('selected_%s' % user.id)
        # print(carts_data)
        # 要展示被选中的商品
        # 将被选中的商品的sku_id和count包装在字典里
        cart_dict = {}
        for sku_id_bt in selected_skus:
            cart_dict[int(sku_id_bt)] = int(carts_data[sku_id_bt])

        total_count = 0
        total_amount = Decimal('0.00')
        sku_qs = SKU.objects.filter(id__in=cart_dict.keys())
        for sku in sku_qs:
            count = cart_dict[sku.id]
            sku.count = count
            sku.amount = sku.price * count

            total_count += count
            total_amount += sku.price * count

        freight = Decimal('10.00')

        context = {
            'addresses': addresses,
            'skus': sku_qs,
            'total_count': total_count,
            'total_amount': total_amount,
            'freight': freight,
            'payment_amount': total_amount + freight
        }
        return render(request, 'place_order.html', context)


class OrdersCommit(View):
    """提交订单"""
    def post(self, request):
        json_dict = json.loads(request.body.decode())
        address_id = json_dict.get('address_id')
        pay_method = json_dict.get('pay_method')
        # 校验
        if not all([address_id, pay_method]):
            return HttpResponseForbidden("缺少必传参数")

        # 校验address
        try:
            address = Address.objects.get(id=address_id)
        except Address.DoesNotExist:
            return HttpResponseForbidden('没有此地址')
        # 校验支付方式
        if pay_method not in [OrderInfo.PAY_METHODS_ENUM.get("CASH"), OrderInfo.PAY_METHODS_ENUM.get("ALIPAY")]:
            return HttpResponseForbidden('支付方式有误')
        user = request.user
        # 生成订单编号（年月日+ 用户id）
        order_id = timezone.now().strftime('%Y%m%d%H%M%S') + '%09d' % user.id
        # 订单状态， 根据支付方式显示对应的订单状态（货到付款->代发货；线上支付->代付款）
        status = OrderInfo.ORDER_STATUS_ENUM.get('UNPAID') if OrderInfo.PAY_METHODS_ENUM.get('ALIPAY') else OrderInfo.ORDER_STATUS_ENUM.get('UNSEND')
        # 增加事物
        with transaction.atomic():
            # 创建事物保存点
            save_id = transaction.savepoint()
            # 保险给以下加一个try,只要中间任意一处出现错误，就回滚
            try:
                # 保存订单信息
                order = OrderInfo.objects.create(
                    order_id=order_id,
                    user=user,
                    address=address,
                    total_count=0,
                    total_amount=Decimal('0.00'),
                    freight=Decimal('10.00'),
                    pay_method=pay_method,
                    status=status

                    )
                # 保存订单商品的准备
                # redis数据库获取值
                redis_conn = get_redis_connection('carts')
                carts_data = redis_conn.hgetall('carts_%s' % user.id)
                selected_skus = redis_conn.smembers('selected_%s' % user.id)
                # 封装下单的商品为一个字典
                cart_dict = {}
                for sku_id_bt in selected_skus:
                    cart_dict[int(sku_id_bt)] = int(carts_data[sku_id_bt])

                # 查出生成订单的对应sku集群， 并遍历
                sku_qs = SKU.objects.filter(id__in=cart_dict.keys())
                for sku in sku_qs:
                    while True:
                        buy_count = cart_dict[sku.id]

                        origin_stock = sku.stock
                        origin_sales = sku.sales
                        # import time
                        # time.sleep(4)
                        # 判断库存是否足够
                        if buy_count > origin_stock:
                            # 开启事物， 如果到这边存在库存不足这个bug， 则全部回滚回到此前状态
                            transaction.savepoint_rollback(save_id)

                            return JsonResponse({'code': RETCODE.STOCKERR, 'errmsg': '库存不够'})

                        # 更新sku的库存和销量
                        new_stock = origin_stock - buy_count
                        new_sales = origin_sales + buy_count

                        # # 保存新的sku库存和销量
                        # sku.stock = new_stock
                        # sku.sales = new_sales
                        # sku.save()
                        result = SKU.objects.filter(id=sku.id, stock=origin_stock).update(stock=new_stock,sales=new_sales)
                        # 为0则有人抢资源， 则如果库存不为0则继续尝试下单
                        if result == 0:
                            continue

                        # 更新spu的销量（利用外健）
                        sku.spu.sales += buy_count
                        sku.spu.save()

                        OrderGoods.objects.create(
                            order=order,
                            sku=sku,
                            count=buy_count,
                            price=sku.price
                        )

                        # 总计和总额的累加  ？
                        order.total_count += buy_count
                        order.total_amount += (buy_count * sku.price)
                        break

                order.total_amount = order.total_amount + order.freight
                order.save()


            except Exception:
                transaction.savepoint_rollback(save_id)
                return JsonResponse({'code': RETCODE.DBERR, 'errmsg': '下单失败'})
            else:
                transaction.savepoint_commit(save_id)
        # 把购物车中的已购买的产品删除
        pl = redis_conn.pipeline()
        pl.hdel('carts_%s' % user.id, *selected_skus)
        pl.delete('selected_%s')
        pl.execute()

        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'order_id': order_id})


class OrdersSuccess(LoginRequiredView):
    def get(self, request):
        payment_amount = request.GET.get('payment_amount')
        order_id = request.GET.get('order_id')
        pay_method = request.GET.get('pay_method')
        # 验证
        try:
            OrderInfo.objects.get(order_id=order_id, pay_method=pay_method, total_amount=payment_amount)
        except OrderInfo.DoesNotExist:
            return JsonResponse({'code': RETCODE.OK, 'errmsg': '参数有误'})

        context = {
            'payment_amount': payment_amount,
            'order_id': order_id,
            'pay_method':pay_method
        }
        return render(request, 'order_success.html', context)


class CommentView(View):  # 查看评价不需要登录
    """评价订单"""
    def get(self, request):
        # 接收, 根据js得出是查询字符串参数及get请求方法
        order_id = request.GET.get('order_id')
        # 验证
        try:
            order = OrderInfo.objects.get(order_id=order_id, user=request.user, status=OrderInfo.ORDER_STATUS_ENUM['UNCOMMENT'])
        except OrderInfo.DoesNotExist:
            return HttpResponseForbidden('没有此id')
        uncomment_goods_list = []
        # 获取此订单对应的所有商品
        order_goods_qs = order.skus.filter(is_commented=False)
        for order_goods in order_goods_qs:
            sku = order_goods.sku
            uncomment_goods_list.append({
                'order_id': order_id,  # 根据后面保存评价信息时，要求传入， 所以此处要传
                'sku_id': sku.id,
                'price': str(sku.price),
                'default_image_url': sku.default_image.url,
                'name': sku.name,
                'score': order_goods.score,
                'comment': order_goods.comment,
                'is_anonymous': str(order_goods.is_anonymous),
                'is_comment': str(order_goods.is_commented)
            })

        context = {'uncomment_goods_list': uncomment_goods_list}

        return render(request, 'goods_judge.html', context)

    def post(self, request):
        """保存订单评价"""
        user = request.user
        # 接收参数
        json_dict = json.loads(request.body.decode())
        order_id = json_dict.get('order_id')
        sku_id = json_dict.get('sku_id')
        comment = json_dict.get('comment')
        score = json_dict.get('score')
        is_anonymous = json_dict.get('is_anonymous')
        # 校验
        if not all([order_id, sku_id, comment, score]):
            return HttpResponseForbidden('缺少必传参数')
        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user, status=OrderInfo.ORDER_STATUS_ENUM['UNCOMMENT'])
        except OrderInfo.DoesNotExist:
            return HttpResponseForbidden('订单错误')
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return HttpResponseForbidden('没有此sku')
        if isinstance(is_anonymous, bool) is False:
            return HttpResponseForbidden('信息错误')

        # 保存订单评价信息
        OrderGoods.objects.filter(order_id=order_id, sku_id=sku_id, is_commented=False).update(
            comment=comment,
            score=score,
            is_anonymous=is_anonymous,
            is_commented=True
        )
        # 修改sku, spu的评价数量
        sku.comments += 1
        sku.save()

        sku.spu.comments += 1
        sku.spu.save()
        # 判断订单中的商品是否都评价完成， 如果是则把订单状态改为已完成
        if OrderGoods.objects.filter(order_id=order_id, is_commented=False).count() == 0:
            order.status = OrderInfo.ORDER_STATUS_ENUM['FINISHED']
            order.save()
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})


class GoodsComment(View):
    """订单详情页面展示评价"""
    def get(self, request, sku_id):
        # 验证
        try:
            SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return HttpResponseForbidden("没有此sku")
        # 向数据库查询数据, 找是sku_id的所有商品
        order_goods_qs = OrderGoods.objects.filter(sku_id=sku_id, is_commented=True).order_by('-create_time')
        comment_list = []
        for order_goods in order_goods_qs:
            # 获取当前商品的所有订单评价用户名
            username = order_goods.order.user.username
            comment_list.append({
                'comment': order_goods.comment,
                'score': order_goods.score,
                'username': (username[0] + '***' + username[-1]) if order_goods.is_anonymous is True else username
            })
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'comment_list': comment_list})

