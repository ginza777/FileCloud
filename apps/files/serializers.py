from rest_framework import serializers
from .models import Document, Product, DocumentImage

MAX_PREVIEW_IMAGES = 5

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'title', 'parsed_content', 'slug']

class DocumentSerializer(serializers.ModelSerializer):
    product = ProductSerializer()
    images = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            'id',
            'parse_file_url',
            'completed',
            'product',
            'images',
            'page_count',
            'file_size',
            'created_at'
        ]

    def get_images(self, obj):
        queryset = obj.images.order_by('page_number')[:MAX_PREVIEW_IMAGES]
        serializer = DocumentImageSerializer(
            queryset,
            many=True,
            context=self.context
        )
        return serializer.data


class DocumentImageSerializer(serializers.ModelSerializer):
    small_url = serializers.SerializerMethodField()
    large_url = serializers.SerializerMethodField()

    class Meta:
        model = DocumentImage
        fields = ['page_number', 'small_url', 'large_url']

    def _absolute_url(self, request, image_field):
        if not image_field:
            return None
        url = image_field.url
        return request.build_absolute_uri(url) if request else url

    def get_small_url(self, obj):
        request = self.context.get('request')
        return self._absolute_url(request, obj.image_small)

    def get_large_url(self, obj):
        request = self.context.get('request')
        return self._absolute_url(request, obj.image_large)

class SearchResultSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    slug = serializers.CharField()
    parsed_content = serializers.CharField()
    document_id = serializers.CharField()
    score = serializers.FloatField()
