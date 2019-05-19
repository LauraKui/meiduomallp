
from django.views.generic import View
# Create your views here.
from meiduomall.libs.captcha.captcha import captcha
from django_redis import get_redis_connection
from django.http import HttpResponse, JsonResponse
import random
from celery_tasks.sms.yuntongxun.sms import CCP
from meiduomall.utils.response_code import RETCODE
import logging
from . import constants
from celery_tasks.sms.tasks import ccp_send_sms_code


logger = logging.getLogger('django')


class ImageCodeView(View):
    def get(self, request, uuid):
        name, text, image = captcha.generate_captcha()
        redis_conn = get_redis_connection('verify_code')
        redis_conn.setex('img: %s' % uuid, constants.IMAGE_CODE_REDIS_EXPIRY, text)
        return HttpResponse(image, content_type='image/png')


class SmsCodeView(View):
    def get(self, request, mobile):

        # 防止用户不停刷新页面重发短信， 规定短信一分钟只能发一次
        redis_conn = get_redis_connection('verify_code')
        pl = redis_conn.pipeline()
        flag = redis_conn.get('get_flag: %s' % mobile)
        if flag:
            return JsonResponse({'code': RETCODE.THROTTLINGERR, 'errmsg': '访问过于频繁'})

        image_code_cli = request.GET.get('image_code')
        uuid = request.GET.get('uuid')
        if all([image_code_cli, uuid]) is False:
            return JsonResponse({'code': RETCODE.NECESSARYPARAMERR, 'errmsg': '缺少必传参数'})

        image_code_server =  redis_conn.get('img: %s' % uuid)
        # 在数据库获取图片验证码后立即删掉， 防止一直输入相同的验证码，恶意点击发送短信
        redis_conn.delete('img: %s' % uuid)
        if image_code_server is None or image_code_cli.lower() != image_code_server.decode().lower():
            return JsonResponse({'code': RETCODE.IMAGECODEERR, 'errmsg': '图形验证码不正确'})
        sms_code = '%06d' % random.randint(0, 999999)
        # 打印出sms_code的值
        logger.info(sms_code)
        # 保存短信验证码的值， 便于之后的校验
        pl.setex('sms: %s' % mobile, constants.SMS_CODE_REDIS_EXPIRY, sms_code)
        # 发送验证码
        # CCP().send_template_sms(mobile, [sms_code, constants.SMS_CODE_REDIS_EXPIRY // 60], 1)
        pl.setex('get_flag: %s' % mobile, constants.SMS_CODE_REDIS_EXPIRY // 5, 1)
        pl.execute()

        ccp_send_sms_code.delay(mobile, sms_code)

        return JsonResponse({'code': RETCODE.OK, 'errmsg': '短信发送成功'})
