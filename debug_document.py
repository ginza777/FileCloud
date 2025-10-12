#!/usr/bin/env python3
"""
Debug script to understand document completion logic
"""

import os
import sys
import django

# Add the project directory to Python path
sys.path.append('/Users/sherzamon/Desktop/projects/FileFinder')

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.files.models import Document

def analyze_document_completion():
    """Analyze why a document might not be completing"""
    
    print("=== DOCUMENT COMPLETION ANALYSIS ===")
    print()
    
    # Check if we can find the specific document
    try:
        doc = Document.objects.get(id="4c1ac486-79c7-4972-82d8-a5525b052c35")
        print(f"✅ Document found: {doc.id}")
    except Document.DoesNotExist:
        print("❌ Document not found in local database")
        return
    
    print(f"📄 Document Details:")
    print(f"   - ID: {doc.id}")
    print(f"   - Download Status: {doc.download_status}")
    print(f"   - Parse Status: {doc.parse_status}")
    print(f"   - Index Status: {doc.index_status}")
    print(f"   - Telegram Status: {doc.telegram_status}")
    print(f"   - Delete Status: {doc.delete_status}")
    print(f"   - Completed: {doc.completed}")
    print(f"   - Pipeline Running: {doc.pipeline_running}")
    print(f"   - Telegram File ID: {doc.telegram_file_id}")
    print(f"   - Created At: {doc.created_at}")
    print(f"   - Updated At: {doc.updated_at}")
    
    # Check product relationship
    if hasattr(doc, 'product') and doc.product:
        product = doc.product
        print(f"📦 Product Details:")
        print(f"   - Product ID: {product.id}")
        print(f"   - Title: {product.title[:100]}...")
        print(f"   - Has Parsed Content: {bool(product.parsed_content)}")
        print(f"   - Parsed Content Length: {len(product.parsed_content) if product.parsed_content else 0}")
        print(f"   - Blocked: {product.blocked}")
        if product.blocked:
            print(f"   - Blocked Reason: {product.blocked_reason}")
    else:
        print("❌ No product associated with this document")
    
    print()
    print("=== COMPLETION LOGIC ANALYSIS ===")
    
    # Check completion conditions
    all_statuses_completed = (
        doc.download_status == 'completed' and
        doc.parse_status == 'completed' and
        doc.index_status == 'completed' and
        doc.telegram_status == 'completed' and
        doc.delete_status == 'completed'
    )
    
    print(f"🔍 All statuses completed: {all_statuses_completed}")
    print(f"   - Download: {doc.download_status} {'✅' if doc.download_status == 'completed' else '❌'}")
    print(f"   - Parse: {doc.parse_status} {'✅' if doc.parse_status == 'completed' else '❌'}")
    print(f"   - Index: {doc.index_status} {'✅' if doc.index_status == 'completed' else '❌'}")
    print(f"   - Telegram: {doc.telegram_status} {'✅' if doc.telegram_status == 'completed' else '❌'}")
    print(f"   - Delete: {doc.delete_status} {'✅' if doc.delete_status == 'completed' else '❌'}")
    
    # Check fix_document_status logic
    has_telegram_id = bool(doc.telegram_file_id)
    has_parsed_content = bool(doc.product and doc.product.parsed_content and doc.product.parsed_content.strip())
    
    print()
    print("=== FIX_DOCUMENT_STATUS LOGIC ===")
    print(f"🔍 Has Telegram File ID: {has_telegram_id}")
    print(f"🔍 Has Parsed Content: {has_parsed_content}")
    print(f"🔍 Should be completed (according to fix_document_status): {has_telegram_id and has_parsed_content}")
    
    if has_telegram_id and has_parsed_content:
        print("✅ According to fix_document_status logic, this document should have all statuses as 'completed'")
        if not all_statuses_completed:
            print("❌ But not all statuses are completed - this is the issue!")
    else:
        print("⚠️  According to fix_document_status logic, this document should be reset to pending")
    
    print()
    print("=== RECOMMENDATIONS ===")
    
    if has_telegram_id and has_parsed_content and not all_statuses_completed:
        print("🔧 RECOMMENDED ACTION: Run fix_document_status command to set all statuses to completed")
    elif not has_telegram_id or not has_parsed_content:
        print("🔧 RECOMMENDED ACTION: Document needs to be reprocessed through the pipeline")
    else:
        print("✅ Document appears to be in correct state")

if __name__ == "__main__":
    analyze_document_completion()
