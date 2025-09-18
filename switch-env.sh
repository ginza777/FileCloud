#!/bin/bash

if [ "$1" == "dev" ]; then
    echo "Switching to development environment..."
    cp .env.development .env
    echo "Development environment activated"
elif [ "$1" == "prod" ]; then
    echo "Switching to production environment..."
    cp .env.production .env
    echo "Production environment activated"
else
    echo "Usage: ./switch-env.sh [dev|prod]"
    exit 1
fi
