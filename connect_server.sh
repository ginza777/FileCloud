#!/bin/bash

# Server connection script for FileFinder project
SERVER_IP="213.199.37.179"
USERNAME="root"
PASSWORD="sherzAmon2001A"

echo "Connecting to server $SERVER_IP as $USERNAME..."
echo "Note: You'll need to enter the password manually when prompted"

# Method 1: Direct SSH connection
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no $USERNAME@$SERVER_IP

# Alternative method if the above doesn't work:
# sshpass -p "$PASSWORD" ssh $USERNAME@$SERVER_IP