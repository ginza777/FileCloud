from rest_framework import serializers
from django.contrib.auth import get_user_model
from apps.bot.models import User, Broadcast, BroadcastRecipient, SubscribeChannel, Location
from apps.files.models import SearchQuery, Document, Product, SiteToken, ParseProgress

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model"""
    full_name = serializers.SerializerMethodField()
    is_online = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'full_name',
            'email', 'is_active', 'is_staff', 'is_superuser', 'is_online',
            'date_joined', 'last_login'
        ]
        read_only_fields = ['id', 'date_joined', 'last_login', 'is_online']
    
    def get_full_name(self, obj):
        return f"{obj.first_name or ''} {obj.last_name or ''}".strip()
    
    def get_is_online(self, obj):
        from django.utils import timezone
        from datetime import timedelta
        return obj.last_login and obj.last_login > timezone.now() - timedelta(minutes=5)


class UserDetailSerializer(UserSerializer):
    """Detailed serializer for User with related data"""
    
    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields


class SubscribeChannelSerializer(serializers.ModelSerializer):
    """Serializer for SubscribeChannel model"""
    subscriber_count = serializers.SerializerMethodField()
    
    class Meta:
        model = SubscribeChannel
        fields = [
            'id', 'channel_username', 'channel_id', 'channel_link',
            'active', 'private', 'subscriber_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'subscriber_count']
    
    def get_subscriber_count(self, obj):
        # This would need to be implemented based on your bot's logic
        return 0


class LocationSerializer(serializers.ModelSerializer):
    """Serializer for Location model"""
    user_username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = Location
        fields = [
            'id', 'user', 'user_username', 'latitude', 'longitude',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class SearchQuerySerializer(serializers.ModelSerializer):
    """Serializer for SearchQuery model"""
    user_username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = SearchQuery
        fields = [
            'id', 'user', 'user_username', 'query_text', 'is_deep_search',
            'found_results', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class BroadcastRecipientSerializer(serializers.ModelSerializer):
    """Serializer for BroadcastRecipient model"""
    user_username = serializers.CharField(source='user.username', read_only=True)
    broadcast_id = serializers.IntegerField(source='broadcast.id', read_only=True)
    
    class Meta:
        model = BroadcastRecipient
        fields = [
            'id', 'broadcast', 'broadcast_id', 'user', 'user_username',
            'status', 'sent_at', 'error_message'
        ]
        read_only_fields = ['id', 'sent_at']


class BroadcastSerializer(serializers.ModelSerializer):
    """Serializer for Broadcast model"""
    recipients = BroadcastRecipientSerializer(many=True, read_only=True)
    total_recipients = serializers.SerializerMethodField()
    sent_count = serializers.SerializerMethodField()
    failed_count = serializers.SerializerMethodField()
    pending_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Broadcast
        fields = [
            'id', 'status', 'scheduled_time', 'from_chat_id', 'message_id',
            'total_recipients', 'sent_count', 'failed_count', 'pending_count',
            'recipients', 'created_at'
        ]
        read_only_fields = ['id', 'from_chat_id', 'message_id', 'created_at']
    
    def get_total_recipients(self, obj):
        return obj.recipients.count()
    
    def get_sent_count(self, obj):
        return obj.recipients.filter(status=BroadcastRecipient.Status.SENT).count()
    
    def get_failed_count(self, obj):
        return obj.recipients.filter(status=BroadcastRecipient.Status.FAILED).count()
    
    def get_pending_count(self, obj):
        return obj.recipients.filter(status=BroadcastRecipient.Status.PENDING).count()


class BroadcastCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating Broadcast"""
    
    class Meta:
        model = Broadcast
        fields = ['status', 'scheduled_time']
    
    def validate_scheduled_time(self, value):
        from django.utils import timezone
        if value and value < timezone.now():
            raise serializers.ValidationError("Scheduled time cannot be in the past")
        return value


# Files app serializers
class DocumentSerializer(serializers.ModelSerializer):
    """Serializer for Document model"""
    
    class Meta:
        model = Document
        fields = [
            'id', 'parse_file_url', 'file_path', 'download_status', 'parse_status',
            'index_status', 'telegram_status', 'delete_status', 'completed',
            'telegram_file_id', 'created_at', 'updated_at', 'json_data'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProductSerializer(serializers.ModelSerializer):
    """Serializer for Product model"""
    document_info = DocumentSerializer(source='document', read_only=True)
    
    class Meta:
        model = Product
        fields = [
            'id', 'title', 'parsed_content', 'slug', 'document', 'document_info',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SiteTokenSerializer(serializers.ModelSerializer):
    """Serializer for SiteToken model"""
    
    class Meta:
        model = SiteToken
        fields = [
            'id', 'name', 'token', 'auth_token', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ParseProgressSerializer(serializers.ModelSerializer):
    """Serializer for ParseProgress model"""
    
    class Meta:
        model = ParseProgress
        fields = [
            'id', 'last_page', 'total_pages_parsed', 'last_run_at', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


# Statistics serializers
class UserStatsSerializer(serializers.Serializer):
    """Serializer for user statistics"""
    total_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    admin_users = serializers.IntegerField()
    blocked_users = serializers.IntegerField()
    users_by_language = serializers.DictField()
    recent_users = UserSerializer(many=True)


class BroadcastStatsSerializer(serializers.Serializer):
    """Serializer for broadcast statistics"""
    total_broadcasts = serializers.IntegerField()
    pending_broadcasts = serializers.IntegerField()
    sent_broadcasts = serializers.IntegerField()
    failed_broadcasts = serializers.IntegerField()
    total_recipients = serializers.IntegerField()
    successful_deliveries = serializers.IntegerField()
    failed_deliveries = serializers.IntegerField()


class SearchStatsSerializer(serializers.Serializer):
    """Serializer for search statistics"""
    total_searches = serializers.IntegerField()
    deep_searches = serializers.IntegerField()
    regular_searches = serializers.IntegerField()
    average_results = serializers.FloatField()
    popular_queries = serializers.ListField(child=serializers.DictField())


class LocationStatsSerializer(serializers.Serializer):
    """Serializer for location statistics"""
    total_locations = serializers.IntegerField()
    unique_users_with_location = serializers.IntegerField()
    recent_locations = LocationSerializer(many=True)


class DocumentStatsSerializer(serializers.Serializer):
    """Serializer for document statistics"""
    total_documents = serializers.IntegerField()
    completed_documents = serializers.IntegerField()
    pending_documents = serializers.IntegerField()
    failed_documents = serializers.IntegerField()
    total_products = serializers.IntegerField()
    recent_documents = DocumentSerializer(many=True)
