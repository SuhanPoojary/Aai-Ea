@echo off
echo AegisSupport 2.0 quick start
 echo 1. Start PostgreSQL: docker compose up -d postgres
 echo 2. In a terminal: cd backend ^&^& py -3.11 -m venv .venv ^&^& .venv\Scripts\activate ^&^& pip install -r requirements.txt ^&^& uvicorn main:app --reload --port 8000
 echo 3. In another terminal: cd frontend ^&^& npm install ^&^& npm run dev
 pause
