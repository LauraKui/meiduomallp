#!/usr/bin/env python

from django.shortcuts import render
from django.conf import settings
from django.template import loader
import os
import sys
import django

sys.path.insert(0, '../')
# 添加
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "meiduomall.settings.dev")

django.setup()

from goods.models import SKU
from contents.utils import get_categories
from goods.utils import get_breadcrumb


def generate_detail_html(sku_id):
    sku = SKU.objects.get(id=sku_id)

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

    context = {

        'categories': get_categories(),
        'breadcrumb': get_breadcrumb(category),
        'sku': sku,
        'spu_spec_qs': spu_spec_qs,
        'spu': spu,
        'category': category

    }

    template = loader.get_template('detail.html')
    html_text = template.render(context)
    file_path = os.path.join(settings.STATICFILES_DIRS[0], 'detail/' + str(sku_id) + '.html')
    with open(file_path, 'w') as f:
        f.write(html_text)


if __name__ == '__main__':

    sku_qs = SKU.objects.all()
    for sku in sku_qs:
        print(sku.id)
        generate_detail_html(sku.id)
