#!/usr/bin/env python3
"""
Comprehensive API tests for FileFinder application
Tests all API endpoints including top downloads, search, view count, and download count
"""

import os
import sys
import django
import requests
import json
from datetime import datetime

# Add the project directory to Python path
sys.path.append('/app')

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.files.models import Document, Product
from django.conf import settings

class APITester:
    def __init__(self, base_url=None):
        self.base_url = base_url or getattr(settings, 'MAIN_URL', 'http://localhost:8000')
        self.session = requests.Session()
        self.test_results = []
        
    def log_test(self, test_name, success, message="", response_data=None):
        """Log test results"""
        result = {
            'test_name': test_name,
            'success': success,
            'message': message,
            'timestamp': datetime.now().isoformat(),
            'response_data': response_data
        }
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {message}")
        
        if response_data and not success:
            print(f"   Response: {response_data}")
    
    def test_top_downloads_api(self):
        """Test the top downloads API endpoint"""
        print("\n🔍 Testing Top Downloads API...")
        
        try:
            url = f"{self.base_url}/api/files/api/top-downloads/"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Validate response structure
                if 'results' in data and 'total' in data:
                    results = data['results']
                    total = data['total']
                    
                    if isinstance(results, list) and len(results) <= 9:
                        # Check if results have required fields
                        if results:
                            first_result = results[0]
                            required_fields = ['id', 'title', 'view_count', 'download_count', 'file_size', 'created_at', 'document_id', 'telegram_file_id']
                            
                            missing_fields = [field for field in required_fields if field not in first_result]
                            
                            if not missing_fields:
                                self.log_test(
                                    "Top Downloads API", 
                                    True, 
                                    f"Returned {len(results)} files, total: {total}"
                                )
                                
                                # Test sorting by download count
                                if len(results) > 1:
                                    sorted_by_downloads = all(
                                        results[i]['download_count'] >= results[i+1]['download_count'] 
                                        for i in range(len(results)-1)
                                    )
                                    self.log_test(
                                        "Top Downloads Sorting", 
                                        sorted_by_downloads, 
                                        "Files sorted by download count" if sorted_by_downloads else "Files not properly sorted"
                                    )
                            else:
                                self.log_test(
                                    "Top Downloads API Structure", 
                                    False, 
                                    f"Missing fields: {missing_fields}"
                                )
                        else:
                            self.log_test(
                                "Top Downloads API", 
                                True, 
                                "No files found (empty results)"
                            )
                    else:
                        self.log_test(
                            "Top Downloads API Count", 
                            False, 
                            f"Expected max 9 results, got {len(results)}"
                        )
                else:
                    self.log_test(
                        "Top Downloads API Structure", 
                        False, 
                        "Missing 'results' or 'total' in response"
                    )
            else:
                self.log_test(
                    "Top Downloads API", 
                    False, 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
                
        except Exception as e:
            self.log_test(
                "Top Downloads API", 
                False, 
                f"Exception: {str(e)}"
            )
    
    def test_search_api(self):
        """Test the search API endpoint"""
        print("\n🔍 Testing Search API...")
        
        # Test cases
        test_queries = [
            "iqtisod",  # Should find economics-related files
            "matematika",  # Should find math-related files
            "nonexistent_query_xyz123",  # Should return empty results
            "",  # Should return error for empty query
        ]
        
        for query in test_queries:
            try:
                url = f"{self.base_url}/api/files/api/search/"
                params = {'q': query} if query else {}
                response = self.session.get(url, params=params, timeout=10)
                
                if query == "":
                    # Empty query should return error
                    if response.status_code == 400:
                        self.log_test(
                            f"Search API (Empty Query)", 
                            True, 
                            "Correctly returned error for empty query"
                        )
                    else:
                        self.log_test(
                            f"Search API (Empty Query)", 
                            False, 
                            f"Expected 400 error, got {response.status_code}"
                        )
                else:
                    if response.status_code == 200:
                        data = response.json()
                        
                        if 'results' in data and 'total' in data:
                            results = data['results']
                            total = data['total']
                            
                            if isinstance(results, list):
                                if results:
                                    # Check result structure
                                    first_result = results[0]
                                    required_fields = ['id', 'title', 'view_count', 'download_count', 'file_size']
                                    missing_fields = [field for field in required_fields if field not in first_result]
                                    
                                    if not missing_fields:
                                        self.log_test(
                                            f"Search API ('{query}')", 
                                            True, 
                                            f"Found {len(results)} results, total: {total}"
                                        )
                                    else:
                                        self.log_test(
                                            f"Search API Structure ('{query}')", 
                                            False, 
                                            f"Missing fields: {missing_fields}"
                                        )
                                else:
                                    self.log_test(
                                        f"Search API ('{query}')", 
                                        True, 
                                        "No results found (expected for some queries)"
                                    )
                            else:
                                self.log_test(
                                    f"Search API ('{query}')", 
                                    False, 
                                    "Results is not a list"
                                )
                        else:
                            self.log_test(
                                f"Search API ('{query}')", 
                                False, 
                                "Missing 'results' or 'total' in response"
                            )
                    else:
                        self.log_test(
                            f"Search API ('{query}')", 
                            False, 
                            f"HTTP {response.status_code}: {response.text[:200]}"
                        )
                        
            except Exception as e:
                self.log_test(
                    f"Search API ('{query}')", 
                    False, 
                    f"Exception: {str(e)}"
                )
    
    def test_view_count_api(self):
        """Test the view count increment API"""
        print("\n🔍 Testing View Count API...")
        
        # Get a product ID to test with
        product = Product.objects.filter(document__completed=True).first()
        
        if not product:
            self.log_test(
                "View Count API", 
                False, 
                "No completed products found for testing"
            )
            return
        
        product_id = product.id
        original_view_count = product.view_count
        
        try:
            url = f"{self.base_url}/api/files/api/{product_id}/view/"
            response = self.session.post(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('success') == True:
                    # Check if view count actually increased
                    product.refresh_from_db()
                    new_view_count = product.view_count
                    
                    if new_view_count > original_view_count:
                        self.log_test(
                            f"View Count API (Product {product_id})", 
                            True, 
                            f"View count increased from {original_view_count} to {new_view_count}"
                        )
                    else:
                        self.log_test(
                            f"View Count API (Product {product_id})", 
                            False, 
                            f"View count did not increase: {original_view_count} -> {new_view_count}"
                        )
                else:
                    self.log_test(
                        f"View Count API (Product {product_id})", 
                        False, 
                        f"API returned success=False: {data}"
                    )
            else:
                self.log_test(
                    f"View Count API (Product {product_id})", 
                    False, 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
                
        except Exception as e:
            self.log_test(
                f"View Count API (Product {product_id})", 
                False, 
                f"Exception: {str(e)}"
            )
    
    def test_download_count_api(self):
        """Test the download count increment API"""
        print("\n🔍 Testing Download Count API...")
        
        # Get a product ID to test with
        product = Product.objects.filter(document__completed=True).first()
        
        if not product:
            self.log_test(
                "Download Count API", 
                False, 
                "No completed products found for testing"
            )
            return
        
        product_id = product.id
        original_download_count = product.download_count
        
        try:
            url = f"{self.base_url}/api/files/api/{product_id}/download/"
            response = self.session.post(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('success') == True:
                    # Check if download count actually increased
                    product.refresh_from_db()
                    new_download_count = product.download_count
                    
                    if new_download_count > original_download_count:
                        self.log_test(
                            f"Download Count API (Product {product_id})", 
                            True, 
                            f"Download count increased from {original_download_count} to {new_download_count}"
                        )
                    else:
                        self.log_test(
                            f"Download Count API (Product {product_id})", 
                            False, 
                            f"Download count did not increase: {original_download_count} -> {new_download_count}"
                        )
                else:
                    self.log_test(
                        f"Download Count API (Product {product_id})", 
                        False, 
                        f"API returned success=False: {data}"
                    )
            else:
                self.log_test(
                    f"Download Count API (Product {product_id})", 
                    False, 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
                
        except Exception as e:
            self.log_test(
                f"Download Count API (Product {product_id})", 
                False, 
                f"Exception: {str(e)}"
            )
    
    def test_main_page(self):
        """Test the main page loads correctly"""
        print("\n🔍 Testing Main Page...")
        
        try:
            url = f"{self.base_url}/"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                content = response.text
                
                # Check for key elements
                checks = [
                    ("HTML title", "FaylTop" in content),
                    ("Top Fayllar section", "Top Fayllar" in content),
                    ("Search functionality", "searchInput" in content),
                    ("API base URL", "{{ MAIN_URL }}" in content or self.base_url in content),
                    ("Telegram bot link", "t.me/fayltop_bot" in content),
                ]
                
                all_passed = True
                for check_name, check_result in checks:
                    if check_result:
                        print(f"   ✅ {check_name}")
                    else:
                        print(f"   ❌ {check_name}")
                        all_passed = False
                
                self.log_test(
                    "Main Page", 
                    all_passed, 
                    "All page elements present" if all_passed else "Some page elements missing"
                )
            else:
                self.log_test(
                    "Main Page", 
                    False, 
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
                
        except Exception as e:
            self.log_test(
                "Main Page", 
                False, 
                f"Exception: {str(e)}"
            )
    
    def run_all_tests(self):
        """Run all API tests"""
        print("🚀 Starting FileFinder API Tests")
        print(f"📍 Testing against: {self.base_url}")
        print(f"⏰ Started at: {datetime.now().isoformat()}")
        
        # Run all tests
        self.test_main_page()
        self.test_top_downloads_api()
        self.test_search_api()
        self.test_view_count_api()
        self.test_download_count_api()
        
        # Summary
        print("\n" + "="*60)
        print("📊 TEST SUMMARY")
        print("="*60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result['success'])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if not result['success']:
                    print(f"   - {result['test_name']}: {result['message']}")
        
        print(f"\n⏰ Completed at: {datetime.now().isoformat()}")
        
        return self.test_results

def main():
    """Main function to run tests"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test FileFinder API endpoints')
    parser.add_argument('--url', default=None, help='Base URL to test against')
    parser.add_argument('--local', action='store_true', help='Test against localhost:8000')
    parser.add_argument('--production', action='store_true', help='Test against https://fayltop.cloud')
    
    args = parser.parse_args()
    
    # Determine base URL
    if args.production:
        base_url = 'https://fayltop.cloud'
    elif args.local:
        base_url = 'http://localhost:8000'
    elif args.url:
        base_url = args.url
    else:
        base_url = None  # Will use settings.MAIN_URL
    
    # Run tests
    tester = APITester(base_url)
    results = tester.run_all_tests()
    
    # Exit with error code if any tests failed
    failed_count = sum(1 for result in results if not result['success'])
    sys.exit(failed_count)

if __name__ == "__main__":
    main()