from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import View


class LoginRequiredView(LoginRequiredMixin, View):
    """需要判断是否需要登录类试图根本"""
    pass