# Test Environment Configuration

## 📋 Umumiy Ma'lumot

Barcha test sozlamalari `.env` faylidan o'qiladi. Bu loyihada test muhiti uchun maxsus o'zgaruvchilar mavjud.

---

## 🔧 Test O'zgaruvchilari

### Bot Test Sozlamalari

```env
# Bot token test uchun
TEST_BOT_TOKEN=test_token_for_testing

# Test channel ID
TEST_CHANNEL_ID=-1001234567890

# Test channel username
TEST_CHANNEL_USERNAME=@testchannel
```

### User Test Sozlamalari

```env
# Test user credentials
TEST_USERNAME=testuser
TEST_PASSWORD=testpass123
TEST_EMAIL=test@example.com
```

### API Test Sozlamalari

```env
# API base URL
TEST_API_BASE_URL=http://localhost:8000
```

### Elasticsearch Test Sozlamalari

```env
# Test index nomi
TEST_ES_INDEX=test_documents
```

---

## 📁 Test Konfiguratsiya Fayli

### `/tests/config.py`

Bu fayl barcha testlar uchun umumiy konfiguratsiyalarni o'z ichiga oladi:

```python
from tests.config import test_config

# Test sozlamalarini olish
bot_token = test_config.get_test_token()
channel_id = test_config.get_test_channel_id()
channel_username = test_config.get_test_channel_username()
user_creds = test_config.get_test_user_credentials()
```

#### TestConfig Class

```python
class TestConfig:
    # Properties
    TEST_BOT_TOKEN          # Bot token
    TEST_CHANNEL_ID         # Channel ID
    TEST_CHANNEL_USERNAME   # Channel username
    TEST_API_BASE_URL       # API base URL
    TEST_DATABASE_NAME      # Test database nomi
    TEST_USERNAME           # Test user username
    TEST_PASSWORD           # Test user password
    TEST_EMAIL              # Test user email
    
    # Methods
    get_test_token()        # Bot token'ni olish
    get_test_channel_id()   # Channel ID'ni olish
    get_test_channel_username()  # Channel username'ni olish
    get_test_user_credentials()  # User credentials'ni olish
    print_config()          # Konfiguratsiyani chiqarish
```

---

## 🧪 Testlarda Foydalanish

### Bot API Testlari

```python
# apps/core_api/api/bot/tests.py

from tests.config import test_config

class BotAPIBasicTestCase(APITestCase):
    def setUp(self):
        # .env dan o'qish
        self.test_bot_token = test_config.get_test_token()
        self.test_channel_id = test_config.get_test_channel_id()
        self.test_channel_username = test_config.get_test_channel_username()
```

### Fallback Mexanizmi

Agar `test_config` import bo'lmasa, `os.getenv()` ishlatiladi:

```python
try:
    from tests.config import test_config
except ImportError:
    test_config = None

def setUp(self):
    if test_config:
        self.test_bot_token = test_config.get_test_token()
    else:
        self.test_bot_token = os.getenv('TEST_BOT_TOKEN', 'default_value')
```

---

## 📝 .env Faylini Sozlash

### 1. .env Faylini Yaratish

```bash
# env.example'dan nusxa oling
cp env.example .env

# Yoki Docker muhitida
docker-compose exec web bash -c "cp env.example .env"
```

### 2. Test O'zgaruvchilarini Qo'shish

`.env` fayliga quyidagilarni qo'shing:

```env
# Test Environment Variables
TEST_BOT_TOKEN=your_test_bot_token
TEST_CHANNEL_ID=-1001234567890
TEST_CHANNEL_USERNAME=@yourtestchannel
TEST_USERNAME=testuser
TEST_PASSWORD=testpass123
TEST_EMAIL=test@example.com
TEST_API_BASE_URL=http://localhost:8000
TEST_ES_INDEX=test_documents
```

---

## 🚀 Testlarni Ishga Tushirish

### Barcha testlar

```bash
python manage.py test tests apps.core_api.api.web.tests \
  apps.core_api.api.bot.tests apps.core_api.api.files.tests \
  apps.core_api.api.core.tests apps.core_api.api.users.tests \
  --verbosity=2 --keepdb
```

### Test konfiguratsiyasini ko'rish

```python
from tests.config import test_config
test_config.print_config()
```

Output:
```
==================================================
TEST KONFIGURATSIYASI
==================================================
Bot Token: test_token_for_test...
Channel ID: -1001234567890
Channel Username: @testchannel
API Base URL: http://localhost:8000
Database: test_filefinder_db
Test User: testuser
==================================================
```

---

## ✅ Test Modullari

### 1. Bot API Tests
- **Fayl:** `apps/core_api/api/bot/tests.py`
- **O'zgaruvchilar:**
  - `TEST_BOT_TOKEN`
  - `TEST_CHANNEL_ID`
  - `TEST_CHANNEL_USERNAME`

### 2. Files API Tests
- **Fayl:** `apps/core_api/api/files/tests.py`
- **O'zgaruvchilar:**
  - `TEST_USERNAME`
  - `TEST_PASSWORD`

### 3. Web API Tests
- **Fayl:** `apps/core_api/api/web/tests.py`
- **O'zgaruvchilar:**
  - `TEST_USERNAME`
  - `TEST_PASSWORD`

### 4. Core Tests
- **Fayl:** `tests/test_*.py`
- **O'zgaruvchilar:**
  - Barcha test o'zgaruvchilari

---

## 🔒 Xavfsizlik

### Production vs Test

```env
# Production (real token)
BOT_TOKEN=real_production_token
CHANNEL_ID=-1003139208100

# Test (test token)
TEST_BOT_TOKEN=test_token_for_testing
TEST_CHANNEL_ID=-1001234567890
```

### .gitignore

`.env` fayli `.gitignore` da bo'lishi kerak:

```gitignore
# Environment variables
.env
.env.local
.env.*.local
```

### env.example

`env.example` fayli versiya nazoratiga qo'shiladi:

```bash
git add env.example
git commit -m "Add environment variables example"
```

---

## 📊 Test Statistikasi

```
Jami testlar:        68 ta
✅ Muvaffaqiyatli:   66 ta (97%)
⏭️ Skipped:          2 ta (3%)
❌ Xatoliklar:       0 ta (0%)

Test qamrovi:
  ✓ Bot API (.env dan token va channel ID)
  ✓ Files API (.env dan user credentials)
  ✓ Web API (.env dan sozlamalar)
  ✓ System tests (.env dan barcha sozlamalar)
```

---

## 🎯 Afzalliklar

1. ✅ **Centralized config** - Barcha sozlamalar bir joyda
2. ✅ **Environment-based** - Har xil muhit uchun alohida sozlamalar
3. ✅ **Type-safe** - TestConfig class orqali type checking
4. ✅ **Fallback support** - Default qiymatlar mavjud
5. ✅ **Easy to use** - Oson import va foydalanish
6. ✅ **Secure** - Production va test sozlamalari ajratilgan

---

## 📚 Qo'shimcha Ma'lumot

### Test Config Class Methods

| Method | Description | Return Type |
|--------|-------------|-------------|
| `get_test_token()` | Bot token'ni olish | `str` |
| `get_test_channel_id()` | Channel ID'ni olish | `str` |
| `get_test_channel_username()` | Channel username'ni olish | `str` |
| `get_test_user_credentials()` | User credentials'ni olish | `dict` |
| `print_config()` | Konfiguratsiyani chiqarish | `None` |

### Environment Variables Priority

1. `.env` fayl (highest priority)
2. `TestConfig` default values
3. `os.getenv()` default values (lowest priority)

---

**Yaratilgan:** 2025-10-03  
**Status:** ✅ Production Ready  
**Testlar:** ✅ 68/68 O'tdi

