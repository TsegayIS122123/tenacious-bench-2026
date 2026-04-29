.PHONY: setup install generate-dataset filter-tasks check-contamination train evaluate test clean validate-schema

# Setup and installation
setup:
	@echo "🔧 Setting up environment..."
	pip install uv
	uv pip install -r requirements.txt
	@echo "✅ Setup complete"

install: setup

# Act II: Dataset authoring
generate-dataset:
	@echo "📊 Generating tasks with multi-LLM pipeline..."
	python scripts/generate_tasks.py --modes all --target 300

filter-tasks:
	@echo "🔍 Filtering tasks with LLM-as-judge..."
	python scripts/filter_tasks.py --threshold 3

# Contamination prevention
check-contamination:
	@echo "🛡️ Running contamination checks..."
	python contamination_check.py --n-gram 8 --embedding-threshold 0.85 --time-shift

# Act IV: Training
train:
	@echo "🏋️ Training LoRA adapter..."
	python scripts/run_training.py --config configs/training_config.yaml

# Act IV: Evaluation
evaluate:
	@echo "📈 Running ablations..."
	python ablations/run_ablations.py --held-out tenacious_bench_v0.1/held_out/

# Statistical significance
bootstrap:
	@echo "📊 Bootstrap significance test..."
	python ablations/bootstrap_stats.py --iterations 1000

# Evidence graph
build-evidence-graph:
	@echo "🔗 Building evidence graph..."
	python scripts/build_evidence_graph.py

# Validation
validate-schema:
	@echo "✅ Validating schema.json..."
	python -c "import json; json.load(open('schema.json'))"
	@echo "✅ Schema valid"

test-agreement:
	@echo "🤝 Running inter-rater agreement test..."
	python scripts/inter_rater_test.py --n-tasks 30

# Utility
clean:
	@echo "🧹 Cleaning cache and temp files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov
	@echo "✅ Clean complete"

# Create .env from example (safely)
init-env:
	@if [ ! -f .env ]; then cp .env.example .env; echo "✅ Created .env from example. Edit to add your API keys."; else echo "⚠️ .env already exists"; fi

# Full pipeline (Day 1-7)
full-pipeline: setup init-env validate-schema generate-dataset filter-tasks check-contamination train evaluate bootstrap build-evidence-graph
	@echo "🎉 Full pipeline complete!"

# Help
help:
	@echo "Available commands:"
	@echo "  make setup              - Install dependencies"
	@echo "  make generate-dataset   - Build Tenacious-Bench"
	@echo "  make filter-tasks       - Quality filtering"
	@echo "  make check-contamination - Prevent data leakage"
	@echo "  make train              - LoRA training"
	@echo "  make evaluate           - Run ablations"
	@echo "  make bootstrap          - Statistical significance"
	@echo "  make build-evidence-graph - Traceability"
	@echo "  make test-agreement     - Inter-rater reliability"
	@echo "  make full-pipeline      - Run everything"