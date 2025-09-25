#!/usr/bin/env python3
"""
Debug script for FaylTop application
Checks if the main page loads files correctly
"""

import requests
import json
import sys

def debug_main_page():
    """Debug the main page file loading"""
    base_url = "http://127.0.0.1:8000"
    
    print("🔍 Debugging FaylTop Main Page...")
    print(f"📍 Testing: {base_url}")
    
    # Test 1: Check main page loads
    print("\n1. Testing main page...")
    try:
        response = requests.get(base_url, timeout=10)
        if response.status_code == 200:
            print("   ✅ Main page loads successfully")
            
            # Check if API_BASE is correct
            if "127.0.0.1:8000" in response.text:
                print("   ✅ API_BASE correctly set to 127.0.0.1:8000")
            else:
                print("   ❌ API_BASE not set correctly")
                
        else:
            print(f"   ❌ Main page failed: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Main page error: {e}")
        return False
    
    # Test 2: Check API endpoint
    print("\n2. Testing API endpoint...")
    try:
        api_url = f"{base_url}/api/files/api/top-downloads/"
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            file_count = len(data.get('results', []))
            print(f"   ✅ API returns {file_count} files")
            
            if file_count > 0:
                print("   ✅ Files are available")
                print(f"   📄 Sample file: {data['results'][0]['title'][:50]}...")
            else:
                print("   ⚠️  No files found in database")
        else:
            print(f"   ❌ API failed: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ API error: {e}")
        return False
    
    # Test 3: Check static files
    print("\n3. Testing static files...")
    try:
        icon_url = f"{base_url}/static/icon.png"
        response = requests.head(icon_url, timeout=10)
        
        if response.status_code == 200:
            print("   ✅ FaylTop logo accessible")
        else:
            print(f"   ❌ Logo not accessible: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Static file error: {e}")
    
    # Test 4: Check pagination
    print("\n4. Testing pagination...")
    try:
        response = requests.get(base_url, timeout=10)
        if response.status_code == 200:
            content = response.text
            
            # Check for pagination elements
            pagination_checks = [
                ("Pagination container", "paginationContainer" in content),
                ("Pagination div", "id=\"pagination\"" in content),
                ("Generate pagination function", "generatePagination" in content),
                ("Change page function", "changePage" in content),
            ]
            
            all_passed = True
            for check_name, check_result in pagination_checks:
                if check_result:
                    print(f"   ✅ {check_name}")
                else:
                    print(f"   ❌ {check_name}")
                    all_passed = False
            
            if all_passed:
                print("   ✅ Pagination functionality ready")
            else:
                print("   ⚠️  Some pagination elements missing")
                
    except Exception as e:
        print(f"   ❌ Pagination test error: {e}")
    
    # Test 5: Check deep search functionality
    print("\n5. Testing deep search...")
    try:
        response = requests.get(base_url, timeout=10)
        if response.status_code == 200:
            content = response.text
            
            # Check for deep search elements
            deep_search_checks = [
                ("Search mode toggle buttons", "regularModeBtn" in content),
                ("Deep mode button", "deepModeBtn" in content),
                ("Search button", "searchBtn" in content),
                ("Search info text", "searchInfo" in content),
                ("Mode toggle functionality", "setSearchMode" in content),
                ("Sport mode CSS", "sport-mode" in content),
                ("Sport mode functions", "activateSportMode" in content),
                ("Sport mode indicator", "SPORT MODE" in content),
                ("Deep mode effects", "deep-mode-active" in content),
                ("Search button transitions", "search-btn-deep" in content),
            ]
            
            all_passed = True
            for check_name, check_result in deep_search_checks:
                if check_result:
                    print(f"   ✅ {check_name}")
                else:
                    print(f"   ❌ {check_name}")
                    all_passed = False
            
            if all_passed:
                print("   ✅ Deep search functionality ready")
            else:
                print("   ⚠️  Some deep search elements missing")
                
    except Exception as e:
        print(f"   ❌ Deep search test error: {e}")
    
    print("\n🎉 Debug complete!")
    print("\nPagination Features:")
    print("• 9 files per page")
    print("• Previous/Next buttons")
    print("• Page numbers with ellipsis")
    print("• Smooth scrolling to file grid")
    print("• Works with search results")
    print("\nDeep Search Features:")
    print("• Regular search: File name only")
    print("• Deep search: File content + name")
    print("• Tooltips on hover")
    print("• Search type indicators")
    print("• Responsive button design")
    print("\nIf files still don't appear:")
    print("1. Check browser console for JavaScript errors")
    print("2. Verify you're accessing http://127.0.0.1:8000 (not localhost)")
    print("3. Try refreshing the page")
    print("4. Check if JavaScript is enabled in your browser")
    
    return True

if __name__ == "__main__":
    debug_main_page()
