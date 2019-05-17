from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^carts/$', views.CartView.as_view(), name='addcarts'),
    url(r'^carts/selection/$', views.SelectedAll.as_view(), name='selection'),
    url(r'^carts/simple/$', views.CartSimpleView.as_view(), name='simple'),
]
