from haystack import indexes

from .models import SKU


class SKUIndex(indexes.SearchIndex, indexes.Indexable):
    """SKU索引数据模型类"""
    # text固定
    text = indexes.CharField(document=True, use_template=True)

    def get_model(self): # 固定llsls
        """返回建立索引的模型类"""
        # SKU可变， 根据想要通过什么来建立索引
        return SKU

    def index_queryset(self, using=None):
        """返回要建立索引的数据查询集"""
        return self.get_model().objects.filter(is_launched=True)