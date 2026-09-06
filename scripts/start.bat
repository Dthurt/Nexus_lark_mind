@echo off
cd /d %~dp0\..
if not exist .env copy .env.example .env
if not exist data mkdir data
if not exist logs mkdir logs
docker compose up --build -d
docker compose ps
echo Web UI: http://localhost:8000
echo Kernel: http://localhost:8001/health
echo Orchestrator: http://localhost:8002/health
