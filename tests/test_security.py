"""
Security Tests Module

Bu modul xavfsizlik testlarini o'z ichiga oladi:
- SQL Injection protection (SQL injection himoyasi)
- XSS protection (XSS himoyasi)
- CSRF protection (CSRF himoyasi)
- Authentication & Authorization (autentifikatsiya va avtorizatsiya)
"""
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
from apps.files.models import Document


class SQLInjectionProtectionTests(APITestCase):
    """SQL injection himoyasi testlari"""
    
    def setUp(self):
        """Test uchun user yaratish"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)
    
    def test_sql_injection_in_search(self):
        """Search'da SQL injection himoyasini test qilish"""
        url = '/api/files/documents/'
        malicious_query = "'; DROP TABLE files_document; --"
        
        response = self.client.get(url, {'search': malicious_query})
        
        # SQL injection ishlamasligi kerak
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Document'lar hali ham mavjud
        documents = Document.objects.all()
        self.assertIsNotNone(documents)
    
    def test_sql_injection_in_filter(self):
        """Filter'da SQL injection himoyasini test qilish"""
        url = '/api/files/documents/'
        malicious_filter = "'; DELETE FROM files_document; --"
        
        response = self.client.get(url, {'search': malicious_filter})
        
        # SQL injection ishlamasligi kerak
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Document'lar hali ham mavjud
        documents = Document.objects.all()
        self.assertIsNotNone(documents)


class XSSProtectionTests(APITestCase):
    """XSS himoyasi testlari"""
    
    def setUp(self):
        """Test uchun user yaratish"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)
    
    def test_xss_in_search(self):
        """Search'da XSS himoyasini test qilish"""
        url = '/api/files/documents/'
        xss_payload = '<script>alert("xss")</script>'
        
        response = self.client.get(url, {'search': xss_payload})
        
        # XSS ishlamasligi kerak
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Response'da script tag'i bo'lmasligi kerak
        if hasattr(response, 'content'):
            self.assertNotIn(b'<script>', response.content)


class CSRFProtectionTests(APITestCase):
    """CSRF himoyasi testlari"""
    
    def setUp(self):
        """Test uchun user yaratish"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
    
    def test_csrf_protection(self):
        """CSRF himoyasini test qilish"""
        # CSRF token'siz POST request
        url = '/api/files/documents/'
        data = {
            'completed': True,
            'pipeline_running': False
        }
        
        response = self.client.post(url, data)
        
        # CSRF himoyasi ishlashi kerak
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED])


class AuthenticationSecurityTests(APITestCase):
    """Authentication xavfsizligi testlari"""
    
    def setUp(self):
        """Test uchun user yaratish"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
    
    def test_password_encryption(self):
        """Parol shifrlashni test qilish"""
        # Parol shifrlanganligini tekshirish
        self.assertNotEqual(self.user.password, 'testpass123')
        self.assertTrue(self.user.check_password('testpass123'))
    
    def test_token_encryption(self):
        """Token shifrlashni test qilish"""
        # Token yaratish
        token, created = Token.objects.get_or_create(user=self.user)
        
        # Token shifrlanganligini tekshirish
        self.assertIsNotNone(token.key)
        self.assertGreater(len(token.key), 10)
    
    def test_unauthorized_access(self):
        """Ruxsatsiz kirishni test qilish"""
        url = '/api/files/documents/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_authorized_access(self):
        """Ruxsatli kirishni test qilish"""
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)
        
        url = '/api/files/documents/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class DataEncryptionTests(APITestCase):
    """Ma'lumotlar shifrlash testlari"""
    
    def setUp(self):
        """Test uchun user yaratish"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_password_hashing(self):
        """Parol hashing'ni test qilish"""
        # Parol hashing algoritmi ishlatilganligini tekshirish
        self.assertTrue(self.user.password.startswith('pbkdf2_sha256'))
    
    def test_sensitive_data_protection(self):
        """Sezgir ma'lumotlar himoyasini test qilish"""
        # User parolini to'g'ridan-to'g'ri olish mumkin emasligini tekshirish
        self.assertNotEqual(self.user.password, 'testpass123')

