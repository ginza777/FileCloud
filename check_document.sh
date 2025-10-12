#!/bin/bash

# Script to check document status on remote server
sshpass -p 'sherzAmon2001A' ssh -T -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@109.94.175.202 << 'EOF'
cd /root/FileFinder
python manage.py shell -c "
from apps.files.models import Document
try:
    doc = Document.objects.get(id='4c1ac486-79c7-4972-82d8-a5525b052c35')
    print(f'Document ID: {doc.id}')
    print(f'Document status: {doc.status}')
    print(f'Document processing_status: {doc.processing_status}')
    print(f'Document created_at: {doc.created_at}')
    print(f'Document updated_at: {doc.updated_at}')
    print(f'Document file_path: {doc.file_path}')
    print(f'Document file_size: {doc.file_size}')
    print(f'Document mime_type: {doc.mime_type}')
    print(f'Document is_processed: {doc.is_processed}')
    print(f'Document has_errors: {doc.has_errors}')
    if hasattr(doc, 'error_message'):
        print(f'Document error_message: {doc.error_message}')
except Document.DoesNotExist:
    print('Document not found')
except Exception as e:
    print(f'Error: {e}')
"
EOF
