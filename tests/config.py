"""
Test Configuration Module
==========================

Bu modul barcha testlar uchun umumiy konfiguratsiyalarni o'z ichiga oladi.
Barcha test sozlamalari .env faylidan o'qiladi.
"""

import os
from django.conf import settings


class TestConfig:
    """Test sozlamalari uchun konfiguratsiya class"""
    
    # Bot test sozlamalari
    TEST_BOT_TOKEN = os.getenv('TEST_BOT_TOKEN', 'test_token_for_testing')
    TEST_CHANNEL_ID = os.getenv('TEST_CHANNEL_ID', '-1001234567890')
    TEST_CHANNEL_USERNAME = os.getenv('TEST_CHANNEL_USERNAME', '@testchannel')
    
    # API test sozlamalari
    TEST_API_BASE_URL = os.getenv('TEST_API_BASE_URL', 'http://localhost:8000')
    
    # Database test sozlamalari
    TEST_DATABASE_NAME = 'test_filefinder_db'
    
    # User test sozlamalari
    TEST_USERNAME = os.getenv('TEST_USERNAME', 'testuser')
    TEST_PASSWORD = os.getenv('TEST_PASSWORD', 'testpass123')
    TEST_EMAIL = os.getenv('TEST_EMAIL', 'test@example.com')
    
    # Elasticsearch test sozlamalari
    TEST_ES_INDEX = os.getenv('TEST_ES_INDEX', 'test_documents')
    
    # Celery test sozlamalari
    TEST_CELERY_EAGER = True
    TEST_CELERY_BROKER = 'memory://'
    
    @classmethod
    def get_test_token(cls):
        """Test token'ni olish"""
        return cls.TEST_BOT_TOKEN
    
    @classmethod
    def get_test_channel_id(cls):
        """Test channel ID'ni olish"""
        return cls.TEST_CHANNEL_ID
    
    @classmethod
    def get_test_channel_username(cls):
        """Test channel username'ni olish"""
        return cls.TEST_CHANNEL_USERNAME
    
    @classmethod
    def get_test_user_credentials(cls):
        """Test user credentials'ni olish"""
        return {
            'username': cls.TEST_USERNAME,
            'password': cls.TEST_PASSWORD,
            'email': cls.TEST_EMAIL
        }
    
    @classmethod
    def print_config(cls):
        """Test konfiguratsiyasini chiqarish"""
        print("\n" + "="*50)
        print("TEST KONFIGURATSIYASI")
        print("="*50)
        print(f"Bot Token: {cls.TEST_BOT_TOKEN[:20]}...")
        print(f"Channel ID: {cls.TEST_CHANNEL_ID}")
        print(f"Channel Username: {cls.TEST_CHANNEL_USERNAME}")
        print(f"API Base URL: {cls.TEST_API_BASE_URL}")
        print(f"Database: {cls.TEST_DATABASE_NAME}")
        print(f"Test User: {cls.TEST_USERNAME}")
        print("="*50 + "\n")


# Test konfiguratsiyasi singleton
test_config = TestConfig()

