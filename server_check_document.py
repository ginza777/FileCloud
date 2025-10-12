#!/usr/bin/env python3
"""
Server script to check document status
"""

import os
import sys
import django

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.files.models import Document

def check_document():
    """Check the specific document status"""
    
    document_id = "4c1ac486-79c7-4972-82d8-a5525b052c35"
    
    try:
        doc = Document.objects.get(id=document_id)
        print(f"Document ID: {doc.id}")
        print(f"Download Status: {doc.download_status}")
        print(f"Parse Status: {doc.parse_status}")
        print(f"Index Status: {doc.index_status}")
        print(f"Telegram Status: {doc.telegram_status}")
        print(f"Delete Status: {doc.delete_status}")
        print(f"Completed: {doc.completed}")
        print(f"Pipeline Running: {doc.pipeline_running}")
        print(f"Telegram File ID: {doc.telegram_file_id}")
        print(f"Created At: {doc.created_at}")
        print(f"Updated At: {doc.updated_at}")
        
        # Check product
        if hasattr(doc, 'product') and doc.product:
            product = doc.product
            print(f"Product ID: {product.id}")
            print(f"Product Title: {product.title}")
            print(f"Has Parsed Content: {bool(product.parsed_content)}")
            print(f"Parsed Content Length: {len(product.parsed_content) if product.parsed_content else 0}")
            print(f"Product Blocked: {product.blocked}")
            if product.blocked:
                print(f"Blocked Reason: {product.blocked_reason}")
        else:
            print("No product associated")
        
        # Check completion logic
        all_completed = (
            doc.download_status == 'completed' and
            doc.parse_status == 'completed' and
            doc.index_status == 'completed' and
            doc.telegram_status == 'completed' and
            doc.delete_status == 'completed'
        )
        
        print(f"All statuses completed: {all_completed}")
        
        # Check fix_document_status logic
        has_telegram_id = bool(doc.telegram_file_id)
        has_parsed_content = bool(doc.product and doc.product.parsed_content and doc.product.parsed_content.strip())
        
        print(f"Has Telegram File ID: {has_telegram_id}")
        print(f"Has Parsed Content: {has_parsed_content}")
        print(f"Should be completed (fix_document_status logic): {has_telegram_id and has_parsed_content}")
        
        if has_telegram_id and has_parsed_content and not all_completed:
            print("ISSUE: Document should be completed but statuses are not all completed")
        elif not has_telegram_id or not has_parsed_content:
            print("ISSUE: Document missing telegram_file_id or parsed_content")
        else:
            print("Document appears to be in correct state")
            
    except Document.DoesNotExist:
        print(f"Document {document_id} not found")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_document()
