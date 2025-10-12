#!/bin/bash

# Script to connect to server and check document
expect << 'EOF'
spawn ssh -o StrictHostKeyChecking=no root@109.94.175.202
expect "password:"
send "sherzAmon2001A\r"
expect "# "
send "cd /root/FileFinder\r"
expect "# "
send "python manage.py shell -c \"from apps.files.models import Document; doc = Document.objects.get(id='4c1ac486-79c7-4972-82d8-a5525b052c35'); print(f'Document ID: {doc.id}'); print(f'Download: {doc.download_status}'); print(f'Parse: {doc.parse_status}'); print(f'Index: {doc.index_status}'); print(f'Telegram: {doc.telegram_status}'); print(f'Delete: {doc.delete_status}'); print(f'Completed: {doc.completed}'); print(f'Telegram File ID: {doc.telegram_file_id}'); print(f'Has Product: {bool(doc.product)}'); print(f'Product Parsed Content: {bool(doc.product and doc.product.parsed_content)}')\"\r"
expect "# "
send "exit\r"
expect eof
EOF
