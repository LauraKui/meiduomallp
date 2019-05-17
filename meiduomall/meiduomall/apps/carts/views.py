from django.shortcuts import render
from django.views.generic import View
from django.http import HttpResponseForbidden, JsonResponse
from django_redis import get_redis_connection
import json, pickle, base64

from goods.models import SKU
from meiduomall.utils.response_code import RETCODE

"""
   {
   sku_id1: {'count': count, 'selected': True},

   }
"""

class CartView(View):
    def get(self, request):
        """查询购物车"""
        # 判度是否登陆
        user = request.user
        if user.is_authenticated:
            # 登录用户返回redis
            redis_conn = get_redis_connection('carts')
            cart_data = redis_conn.hgetall('carts_%s' % user.id)  # [sku_id: count, sku_id2: count]
            selected_data = redis_conn.smembers('selected_%s' % user.id)  # [sku_id1, sku_id2]
            cart_dict = {}
            # 要把redis中的数据包装成cookie的类型， 可以一并返回
            for sku_id_bt, count_bt in cart_data.items():
                cart_dict[int(sku_id_bt)] = {
                    'count': int(count_bt),
                    'selected': sku_id_bt in selected_data
                }


        # 用户没登录
        else:
            carts_str = request.COOKIES.get('carts')
            if carts_str:
                # 字符串转成字典
                cart_dict = pickle.loads(base64.b64decode(carts_str.encode()))

            else:
                return render(request, 'cart.html')

        sku_qs = SKU.objects.filter(id__in=cart_dict.keys())
        cart_skus = []
        for sku in sku_qs:
            dict_cart = {
                'id': sku.id,
                'name': sku.name,
                'price': str(sku.price),
                'count': cart_dict[sku.id]['count'],
                'default_image_url': sku.default_image.url,
                'selected': str(cart_dict[sku.id]['selected']),
                'amount': str(sku.price * cart_dict[sku.id]['count'])
            }
            cart_skus.append(dict_cart)
        context = {'cart_skus': cart_skus}

        return render(request, 'cart.html', context)

    def post(self, request):
        """新增购物车"""
        # 接收请求体参数
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')
        count = int(json_dict.get('count'))
        selected = json_dict.get('selected', True)
        # 校验
        if not all([sku_id, count]):
            return HttpResponseForbidden("缺少参数")
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return HttpResponseForbidden("没有此sku")
        try:
            count = int(count)
        except Exception:
            return HttpResponseForbidden("count参数有误")

        # 判断用户是否登陆
        user = request.user
        if user.is_authenticated:
        # 如果登陆， 存redis
            # 连接redis
            redis_conn = get_redis_connection('carts')
            pl = redis_conn.pipeline()
            # hash数据和set数据
            pl.hincrby('carts_%s' % user.id, sku_id, count)
            if selected:
                pl.sadd('selected_%s' % user.id, sku_id)
            pl.execute()
            # 返回
            return JsonResponse({'code':RETCODE.OK, 'errmsg': 'OK'})
        else:
            # 如果没登陆, 存cookie
            # 判断是否有cookie值
            """
            {
            sku_id1: {'count': count, 'selected': True},
            
            }
            """
            carts_str = request.COOKIES.get('carts')
            if carts_str:
                # 字符串转为字典
                carts_dict = pickle.loads(base64.b64decode(carts_str.encode()))
                # 有就继续判断是否有此商品
                # 有就+1

            else:
                carts_dict = {}

            if sku_id in carts_dict:
                oringin_count = carts_dict[sku_id]['count']
                count += oringin_count

             # 增加数据
            carts_dict[sku_id] = {
                'count': count,
                'selected': selected
            }
            # 字典转字符串
            carts_str = base64.b64encode(pickle.dumps(carts_dict)).decode()
            # 返回
            response = JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})
            response.set_cookie('carts', carts_str)
            return response

    def put(self, request):
        """修改购物车"""
        # 可以修改selected, count, 也需要知道sku_id， 前端请求体
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')
        count = int(json_dict.get('count'))
        selected = json_dict.get('selected')
        #校验
        if not all([sku_id, count]):
            return HttpResponseForbidden("缺少必传参数")
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return HttpResponseForbidden("没有此sku")
        try:
            count = int(count)
        except Exception:
            return HttpResponseForbidden("count参数有误")

        cart_sku = {
            'id': sku.id,
            'name': sku.name,
            'price': sku.price,
            'count': count,
            'default_image_url': sku.default_image.url,
            'selected': selected,
            'amount': sku.price * count
        }
        response = JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'cart_sku': cart_sku})

        user = request.user
        if user.is_authenticated:
            # 如果用户登录，1， 连接redis
            redis_conn = get_redis_connection('carts')
            pl = redis_conn.pipeline()
            # 2，hash中的set， 旧值覆盖新值
            pl.hset('carts_%s' % user.id, sku_id, count)
            # 3， 判断selected, 如果选中， 就增加sku_id, 否则删除
            if selected:
                pl.sadd('selected_%s' % user.id, sku_id)
            else:
                pl.srem('selected_%s' % user.id, sku_id)

            pl.execute()

        else:
            # 判断是否有cookie
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                # 字符串转字典
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                return HttpResponseForbidden("没有此cookie")

            # 将新值覆盖旧值
            cart_dict[sku_id] = {
                'count': count,
                'selected': selected
            }
            # 字典转字符串
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
            # 需要返回数据给前端， 所以要进行包装成字典
            # 根据js接收的数据， key 为cart_sku

            response.set_cookie('carts', cart_str)
        return response

    def delete(self, request):
        """删除数据"""
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')
        # 验证
        try:
            SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return HttpResponseForbidden("没有此sku")
        user = request.user
        response = JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})
        if user.is_authenticated:
            redis_conn = get_redis_connection('carts')
            pl = redis_conn.pipeline()
            # 删除购物车还有selected
            pl.hdel('carts_%s' % user.id, sku_id)
            pl.srem('selected_%s' % user.id, sku_id)
            pl.execute()
            return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})
        else:
            carts_str = request.COOKIES.get('carts')
            if carts_str:
                # 字符串转字典
                cart_dict = pickle.loads(base64.b64decode(carts_str.encode()))
            else:
                return HttpResponseForbidden("wu cookie")
            if sku_id in cart_dict:
                del cart_dict[sku_id]

            if len(cart_dict.keys()) == 0:
                response.delete_cookie('carts')
                return response

            # 字典转字符串
            carts_str = base64.b64encode(pickle.dumps(cart_dict)).decode()

            response.set_cookie('carts', carts_str)
            return response


class SelectedAll(View):
    """全选购物车"""
    def put(self, request):
        # 是否全选， 接收参数selected
        json_dict = json.loads(request.body.decode())
        selected = json_dict.get('selected')
        # 判断是否是布尔值
        if not isinstance(selected, bool):
            return HttpResponseForbidden("selected有误")
        # 判断是否是登录用户
        user = request.user
        response = JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})
        if user.is_authenticated:
            # 连接redis
            redis_conn = get_redis_connection('carts')
            # 获取redis数据
            carts_count = redis_conn.hgetall('carts_%s' % user.id)
            # 如果是全选， 把carts中的sku_id全加到selected中  ?
            if selected:
                redis_conn.sadd('selected_%s' % user.id, *carts_count.keys())
            # 否则把selected中的数据全删掉
            else:
                # redis_conn.srem('selected_%s' % user.id, *carts_count.keys())
                redis_conn.delete('selected_%s' % user.id)

        else:
            # 获取cookie
            cart_str = request.COOKIES.get('carts')
            # 判断是否有cookie
            if cart_str:
                # 有就字符串转字典
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
                # 没有就返回
            else:
                return JsonResponse({'code': RETCODE.OK, 'errmsg': '没有cookie'})
            # 如果是全选， 则把selected全改为True  ?
            if selected:
                for sku_id in cart_dict:
                    cart_dict[sku_id]['selected'] = selected
            # 如果不是， 则改为False
            else:
                for sku_id in cart_dict:
                    cart_dict[sku_id]['selected'] = selected
            # 字典转字符串
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
            # 返回

            # 设置cookie
            response.set_cookie('carts', cart_str)
        return response


class CartSimpleView(View):
    """简单购物车展示"""
    def get(self, request):
        user = request.user
        if user.is_authenticated:
            redis_conn = get_redis_connection('carts')
            # 要把购物车里面的商品都简单展示出来（遍历）， 无论选没选中
            carts_datas = redis_conn.hgetall('carts_%s' % user.id)
            selected_skus = redis_conn.smembers('selected_%s' % user.id)
            # 把数据封装成字典样式  ?
            cart_dict = {}
            for sku_id_bt, count_bt in carts_datas.items():
                cart_dict[int(sku_id_bt)] = {
                    'count': int(count_bt),
                    'selected': sku_id_bt in selected_skus
                }

            # 返回数据， 字典形式
        else:
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                # 字符串转字典
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                return JsonResponse({'code': RETCODE.DBERR, 'errmsg': '无此cookie'})

        cart_skus = []
        sku_qs = SKU.objects.filter(id__in=cart_dict.keys())
        for sku in sku_qs:
            data_dict = {
                'id': sku.id,
                'name': sku.name,
                'count': cart_dict[sku.id]['count'],
                'default_image_url': sku.default_image.url
            }
            cart_skus.append(data_dict)

        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'cart_skus': cart_skus})








