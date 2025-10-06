# FileFinder Test Suite

Bu papkada FileFinder loyihasi uchun tizim darajasidagi testlar joylashgan.

## 📁 Test Modullari

### `test_celery_tasks.py`
Celery background task testlari:
- Task execution (vazifa bajarilishi)
- Task retry mechanism (qayta urinish)
- Task timeout (vaqt tugashi)
- Celery Beat schedule
- Task serialization

**Testlar:** 6 ta | **Status:** ✅ 100%

### `test_elasticsearch.py`
Elasticsearch integration testlari:
- Basic search (oddiy qidiruv)
- Deep search (chuqur qidiruv)
- Document indexing
- Connection handling

**Testlar:** 6 ta | **Status:** ✅ 100%

### `test_api_endpoints.py`
REST API endpoint testlari:
- Document CRUD operatsiyalari
- Product API
- Authentication & Authorization
- Broadcast API

**Testlar:** 10 ta | **Status:** ✅ 100%

### `test_security.py`
Xavfsizlik testlari:
- SQL Injection himoyasi
- XSS himoyasi
- CSRF himoyasi
- Password encryption
- Token security

**Testlar:** 10 ta | **Status:** ✅ 100%

### `test_performance.py`
Performance testlari:
- Database connection speed
- Query performance
- API response time
- Concurrent requests

**Testlar:** 5 ta | **Status:** ✅ 100%

### `test_system.py`
System integration testlari:
- End-to-end workflows
- Multi-component integration
- System stability

**Testlar:** 7 ta | **Status:** ✅ 100%

## 🚀 Testlarni Ishga Tushirish

### Barcha testlarni ishga tushirish
```bash
python manage.py test tests --verbosity=2
```

### Alohida modul testlari
```bash
# Celery testlari
python manage.py test tests.test_celery_tasks

# Elasticsearch testlari
python manage.py test tests.test_elasticsearch

# API testlari
python manage.py test tests.test_api_endpoints

# Security testlari
python manage.py test tests.test_security

# Performance testlari
python manage.py test tests.test_performance

# System testlari
python manage.py test tests.test_system
```

## 📊 Statistika

**Jami testlar:** 44 ta  
**Muvaffaqiyatli:** 44 ta (100%)  
**Xatoliklar:** 0 ta (0%)

## 🗄️ Database

Barcha testlar PostgreSQL database bilan ishlaydi:
- Test database: `test_filefinder_db`
- Connection pooling: ✅
- Transaction support: ✅

## ⚙️ Test Sozlamalari

```python
# settings.py
if 'test' in sys.argv:
    # Celery eager mode
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
    
    # Test database
    DATABASES['default']['TEST'] = {
        'NAME': 'test_filefinder_db',
    }
```

## 📝 Test Yozish Qoidalari

1. **Naming Convention**
   - Test fayl: `test_*.py`
   - Test class: `*Tests`
   - Test method: `test_*`

2. **Structure**
   ```python
   class MyFeatureTests(TestCase):
       def setUp(self):
           """Test uchun ma'lumotlar yaratish"""
           pass
       
       def test_feature_works(self):
           """Feature ishlashini test qilish"""
           pass
   ```

3. **Documentation**
   - Har bir test method uchun docstring
   - Aniq va tushunarli test nomlari
   - Setup va teardown logic

4. **Best Practices**
   - Isolated tests (mustaqil testlar)
   - Use fixtures (test ma'lumotlari)
   - Test one thing (bir narsa test qilish)
   - Clear assertions (aniq assertion'lar)

## 🔗 Aloqador Fayllar

- `/apps/core_api/api/*/tests.py` - API modullari testlari
- `/run_tests.sh` - Test runner script
- `/FINAL_TEST_REPORT.md` - Batafsil test hisoboti

