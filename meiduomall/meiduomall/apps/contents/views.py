from django.shortcuts import render
from django.http import HttpResponse
from django.views.generic import View

from .models import ContentCategory, Content
from .utils import get_categories


class Index(View):
    def get(self, request):

        categories = get_categories()

        # 广告
        contents = {}
        contentcatagory = ContentCategory.objects.all()
        for category in contentcatagory:
            contents[category.key] = category.content_set.filter(status=True)



        context = {
            'categories': categories,
            'contents': contents
        }



        return render(request, 'index.html', context)


"""
catagories = {}
{
'1': {'channel':[一级数据], 'sub_cats':[二级数据]},
'2': {}....

}
"""