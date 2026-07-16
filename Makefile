.PHONY: setup up down logs migrate seed backend backend-test robot-test mobile-test lint format robot-sim verify
setup:
	python -m venv .venv
	.venv/bin/pip install -e services/backend[dev] -e edge/robot[dev]
up:
	docker compose up -d
down:
	docker compose down
logs:
	docker compose logs -f
migrate:
	cd services/backend && alembic upgrade head
seed:
	python scripts/seed_demo_data.py
backend:
	cd services/backend && uvicorn rafeeq_backend.main:app --reload
backend-test:
	cd services/backend && python -m pytest
robot-test:
	cd edge/robot && python -m pytest
mobile-test:
	cd apps/mobile && flutter test
lint:
	python -m ruff check services/backend edge/robot scripts
	python -m mypy services/backend/src edge/robot/src
format:
	python -m ruff format services/backend edge/robot scripts
robot-sim:
	python scripts/run_robot_simulator.py
verify:
	python scripts/verify_environment.py

