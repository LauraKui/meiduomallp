from goods.models import GoodsChannel


def get_categories():
    categories = {}
    goods_channel_qs = GoodsChannel.objects.order_by('group_id', 'sequence')

    for channel in goods_channel_qs:
        group_id = channel.group_id
        if group_id not in categories:
            categories[group_id] = {"channels": [], "sub_cats": []}
        cat1 = channel.category  # 为什么可以得到第一级的数据，具体是哪些数据
        cat1.url = channel.url
        categories[group_id]['channels'].append(cat1)
        # 获取第二级
        cat2_qs = cat1.subs.all()
        for cat2 in cat2_qs:
            cat3_qs = cat2.subs.all()
            cat2.sub_cats = cat3_qs
            categories[group_id]['sub_cats'].append(cat2)

    return categories