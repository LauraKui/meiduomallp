from django.template import loader
from django.conf import settings
from django.shortcuts import render
import os

from .utils import get_categories
from .models import ContentCategory


def generate_static_index_html():
    """生成静态的首页文件"""

    # 先获取要渲染的数据（首页静态数据有三级目录， 广告）
    categories = get_categories()
    # 广告
    contents = {}
    contentcatagory = ContentCategory.objects.all()
    for category in contentcatagory:
        contents[category.key] = category.content_set.filter(status=True)

    # 渲染模板
    context = {
        'categories': categories,
        'contents': contents
    }

    # # 生成模板文件
    # template = loader.get_template('index.html')
    # # 渲染首页html字符串
    # html_text = template.render(context)
    response = render(None, 'detail.html', context)
    html_text = response.content.decode()
    file_path = os.path.join(settings.STATICFILES_DIRS[0], 'index.html')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(html_text)
