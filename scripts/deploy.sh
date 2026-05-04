#!/bin/bash

# 프로젝트 디렉토리로 이동 (사용자 환경에 맞게 수정 필요)
PROJECT_DIR="~/auto-bonde-bot/trading_bot"

echo "🚀 [DEPLOY] 배포 프로세스 시작..."
cd $PROJECT_DIR || { echo "❌ 디렉토리를 찾을 수 없습니다."; exit 1; }

# 최신 코드 가져오기
echo "📥 [GIT] 최신 코드 Pull..."
git pull origin main

# 도커 컨테이너 재빌드 및 실행
echo "🐳 [DOCKER] 컨테이너 재빌드 및 실행..."
docker-compose down
docker-compose up -d --build

echo "✅ [SUCCESS] 배포가 완료되었습니다."
