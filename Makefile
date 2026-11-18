.PHONY: prepare up down test scores logs
prepare:
	python3 scripts/provision.py
up:
	docker compose up -d --build
down:
	docker compose down
test:
	python3 -m unittest discover -s tests -v
scores:
	docker compose exec scoreboard scorewatch
logs:
	docker compose logs --tail 50
