from rest_framework import serializers
from .models import Document, Product, DocumentImage

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'title', 'parsed_content', 'slug']

class DocumentSerializer(serializers.ModelSerializer):
    product = ProductSerializer()
    images = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ['id', 'parse_file_url', 'completed', 'product', 'images', 'created_at']

    def get_images(self, obj):
        request = self.context.get('request')
        images = obj.images.all()[:5]
        urls = []
        for di in images:
            url = di.image.url
            if request is not None:
                url = request.build_absolute_uri(url)
            urls.append({'page': di.page_number, 'url': url})
        return urls


class DocumentImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentImage
        fields = ['page_number', 'image']

class SearchResultSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    slug = serializers.CharField()
    parsed_content = serializers.CharField()
    document_id = serializers.CharField()
    score = serializers.FloatField()
