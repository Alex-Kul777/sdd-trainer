# Makefile for SDD Trainer development tasks
.PHONY: help test test-cov test-unit test-integration test-smoke clean

help:
	@echo "Available commands:"
	@echo "  make test             - Run all tests"
	@echo "  make test-cov         - Run tests with coverage report"
	@echo "  make test-unit        - Run unit tests only"
	@echo "  make test-integration - Run integration tests only"
	@echo "  make test-smoke       - Run smoke tests"
	@echo "  make clean            - Remove temporary files"

test:
	pytest -v

test-cov:
	pytest --cov=sdd_trainer --cov-report=html --cov-report=term
	@echo "Coverage report: open htmlcov/index.html"

test-unit:
	pytest -m "unit" -v

test-integration:
	pytest -m "integration" -v

test-smoke:
	pytest -m "smoke" -v

clean:
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
