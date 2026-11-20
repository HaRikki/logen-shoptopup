#!/bin/bash
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env
pip install -r requirements.txt -q
python main.py
