
from django.shortcuts import render
from django.views.generic import View
from meiduomall.utils.view import LoginRequiredView
from django.http import JsonResponse, HttpResponseForbidden
from django.core.cache import cache
# Create your views here.

from .models import Area
from meiduomall.utils.response_code import RETCODE


class GetAreasView(LoginRequiredView):
    def get(self, request):
        global areas_dicts
        area_id = request.GET.get('area_id')
        if area_id is None:
            province_list = cache.get('province_list')
            if not province_list:
                province_info = Area.objects.filter(parent_id=None)
                province_list = []
                for province in province_info:
                    pro_dict = {
                        'id':province.id,
                        'name': province.name
                    }
                    province_list.append(pro_dict)
                cache.set('province_list', province_list, 3600)
            return JsonResponse({'code':RETCODE.OK, 'errmsg': 'OK', 'province_list': province_list})
        else:
            # 是市级或区级
            sub_list = cache.get('areas_data_%s' % area_id)
            if not sub_list:
                try:
                    parent_model = Area.objects.get(id=area_id)
                except Area.DoesNotExist:
                    return HttpResponseForbidden("找不到此地方")

                sub_model = parent_model.subs.all()
                sub_list = []
                for sub_place in sub_model:
                    # 市或区的
                    place_dict = {
                        'id': sub_place.id,
                        'name': sub_place.name
                    }

                    sub_list.append(place_dict)

                areas_dicts = {
                    'id': parent_model.id,
                    'name': parent_model.name,
                    'subs':sub_list
                    }
                cache.set('areas_data_%s' % area_id, areas_dicts, 3600)
            return JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'sub_data': areas_dicts})
