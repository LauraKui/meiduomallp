from django_redis import get_redis_connection
import pickle, base64


def merge_cookie_cart_to_redis(request, user, response):
    """合并数据库"""
    # 获取cookie
    cart_str = request.COOKIES.get('carts')
    if cart_str:
        # 字符串转字典
        cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
    else:
        return
    # 连接redis
    redis_conn = get_redis_connection('carts')
    pl = redis_conn.pipeline()
    # 把 cookie中的sku_id 和 count 保存到cookie中
    for sku_id in cart_dict:

        pl.hset('carts_%s' % user.id, sku_id, cart_dict[sku_id]['count'])
        if cart_dict[sku_id]['selected']:
            pl.sadd('selected_%s' % user.id, sku_id)
        else:
            pl.srem('selected_%s' % user.id, sku_id)

    pl.execute()
    response.delete_cookie('cart')

