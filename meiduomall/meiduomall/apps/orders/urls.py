from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^orders/settlement/$', views.OrdersSettle.as_view(), name='settlement'),
    url(r'^orders/commit/$', views.OrdersCommit.as_view(), name='commit'),
    url(r'^orders/success/$', views.OrdersSuccess.as_view(), name='success'),
    url(r'^orders/comment/$', views.CommentView.as_view(), name='comment'),
    url(r'^comments/(?P<sku_id>\d+)/$', views.GoodsComment.as_view(), name='goodscomment'),

]
