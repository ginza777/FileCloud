from rest_framework import serializers
from .models import Document, Product

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'title', 'parsed_content', 'slug']

class DocumentSerializer(serializers.ModelSerializer):
    product = ProductSerializer()

    class Meta:
        model = Document
        fields = ['id', 'parse_file_url', 'completed', 'product', 'created_at']

class SearchResultSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    slug = serializers.CharField()
    parsed_content = serializers.CharField()
    document_id = serializers.CharField()
    score = serializers.FloatField()
