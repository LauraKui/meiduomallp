"""meiduo_mall URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import url, include
from django.contrib import admin
from .views import Register, CheckUserView, CheckMobileView, LoginView, LogoutView, UserInfo
from . import views
urlpatterns = [
    url(r'^register/', Register.as_view(), name="register"),
    url(r'^usernames/(?P<username>[a-zA-Z0-9_-]{5,20})/count/$', CheckUserView.as_view(), name='checkusername'),
    url(r'^mobiles/(?P<mobile>1[3-9]\d{9})/count/$', CheckMobileView.as_view(), name='checkmobile'),
    url(r'^login/$', LoginView.as_view(), name="login"),
    url(r'^logout/$', LogoutView.as_view(), name="logout"),
    url(r'^info/$', UserInfo.as_view(), name="info"),
    url(r'^emails/$', views.EmailView.as_view(), name='email'),
    url(r'^emails/verification/$', views.VerifyEmailView.as_view(), name='emveri'),
    url(r'^addresses/create/$', views.CreateAddrView.as_view(), name='createaddr'),
    url(r'^addresses/$', views.AddressView.as_view(), name='address'),
    url(r'^addresses/(?P<address_id>\d+)/$', views.ChangeAddrView.as_view(), name='change'),
    url(r'^addresses/(?P<address_id>\d+)/default/$', views.DefaultAddrView.as_view(), name='default'),
    url(r'^addresses/(?P<address_id>\d+)/title/$', views.TitleChangeView.as_view(), name='title'),
    url(r'^password/$', views.ModifyPassd.as_view(), name='password'), # 修改密码
    # 用户浏览记录
    url(r'^browse_histories/$', views.HistoryView.as_view(), name='history'),
    url(r'^orders/info/(?P<page_num>\d+)/$', views.UserOrderInfoView.as_view(), name='orderinfo'),

        ]
