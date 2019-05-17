from django.shortcuts import render
from django.views.generic import View
from django.http import HttpResponseNotFound, JsonResponse, HttpResponseForbidden
from django.core.paginator import Paginator
from django.utils import timezone


from contents.utils import get_categories
from .utils import get_breadcrumb
from .models import GoodsCategory, SKU, GoodsVisitCount
from meiduomall.utils.response_code import RETCODE


class ListView(View):

    def get(self, request, category_id, page_num):

        categories = get_categories()

        try:
            category = GoodsCategory.objects.get(id=category_id)
        except GoodsCategory.DoesNotExist:
            return HttpResponseNotFound("没有此类商品")

        sort = request.GET.get('sort', 'default')
        if sort == 'price':
            sort_field = 'price'
        elif sort == 'hot':
            sort_field = '-sales'
        else:
            sort_field = 'create_time'

        # 获取三级类下所有sku
        sku_qs = category.sku_set.filter(is_launched=True).order_by(sort_field)

        paginator = Paginator(sku_qs, 5)
        page_skus = paginator.page(page_num)
        total_page = paginator.num_pages

        breadcrumb = get_breadcrumb(category)

        context = {
            'categories': categories,   # 频道分类
            'breadcrumb': breadcrumb,   # 面包屑导航
            'sort': sort,               # 排序字段
            'category': category,       # 第三级分类
            'page_skus': page_skus,     # 分页后数据
            'total_page': total_page,   # 总页数
            'page_num': page_num,
        }


        return render(request, 'list.html', context)


class HotView(View):
    def get(self, request, category_id):
        try:
            category = GoodsCategory.objects.get(id=category_id)
        except GoodsCategory.DoesNotExist:
            return HttpResponseNotFound("没有此类商品")

        hots_qs = category.sku_set.filter(is_launched=True).order_by('-sales')[0:2]
        hot_skus = []
        for hot in hots_qs:
            hot_dict = {
                'id': hot.id,
                'default_image_url': hot.default_image.url,
                'name': hot.name,
                'price': hot.price
            }
            hot_skus.append(hot_dict)

        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'hot_skus': hot_skus})


class DetailView(View):
    """商品详情页面"""
    def get(self, request, sku_id):
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return render(request, '404.html')
        # 通过sku获取三级目录商品
        category = sku.category

        # categories = get_categories()

        # breadcrumb = get_breadcrumb(category)

        spu = sku.spu

        # 1, 获得当前sku的规格
        current_sku_spec_qs = sku.specs.order_by('spec_id')
        current_sku_option_ids = []
        for current_sku_spec in current_sku_spec_qs:
            current_sku_option_ids.append(current_sku_spec.option_id)

        # 2, 获得spu的所有规格包装
        # 获得所有spu下的sku
        sku_qs = spu.sku_set.all()
        # {(8,11): 3, (8,12): 4....}
        all_spec_dict = {}
        for every_sku in sku_qs:
            # 查每个sku对应的规格
            every_sku_spec_qs = every_sku.specs.order_by('spec_id')
            every_sku_option_ids = []
            for every_sku_spec in every_sku_spec_qs:
                every_sku_option_ids.append(every_sku_spec.option_id)
                all_spec_dict[tuple(every_sku_option_ids)] = every_sku.id


        # 3, 与 sku_id进行绑定
        # 获取此商品对应spu的所有规格名称
        spu_spec_qs = spu.specs.order_by('id')
        # 遍历spu的所有规格得到每一个规格， 其属性就是每个规格对应的所有规格值，
        for index, spu_spec in enumerate(spu_spec_qs):
            spu_option_qs = spu_spec.options.all()
            temp_option_ids = current_sku_option_ids[:]
            for option in spu_option_qs:
                temp_option_ids[index] = option.id
                option.sku_id = all_spec_dict.get(tuple(temp_option_ids))

            spu_spec.spu_option = spu_option_qs

        context ={

            'categories': get_categories(),
            'breadcrumb': get_breadcrumb(category),
            'sku':sku,
            'spu_spec_qs': spu_spec_qs,
            'spu': spu,
            'category':category

        }
        return render(request, 'detail.html', context)


class VisitView(View):
    """商品类浏览记录"""
    def post(self, request, category_id):
        # 校验category_id是否存在
        try:
            category = GoodsCategory.objects.get(id=category_id)
        except GoodsCategory.DoesNotExist:
            return HttpResponseForbidden("此商品不存在")

        today_date = timezone.now()

        try:
            visit_count = GoodsVisitCount.objects.get(category=category, date=today_date)
        except GoodsVisitCount.DoesNotExist:
            # 如果访问记录不存在，说明今天是第一次访问，新建记录并保存访问量。
            visit_count = GoodsVisitCount(
                category=category
            )

        visit_count.count += 1
        visit_count.save()
        return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})






    # 如果访问记录存在，说明今天不是第一次访问，不新建记录，访问量直接累加。
