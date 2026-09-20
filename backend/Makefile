# Operator-only model setup. Not part of the application build.
# Usage: make export-model APPROVE=1   (APPROVE=1 records that you reviewed the model licenses)
EXPORT_VENV ?= .venv-export
EXPORT_PYTHON ?= $(EXPORT_VENV)/bin/python
MODELS_DIR ?= ../models
APPROVE_FLAG = $(if $(APPROVE),--approve,)

.PHONY: export-model
export-model: $(EXPORT_PYTHON)
	SSL_CERT_FILE=$$($(EXPORT_PYTHON) -c "import certifi; print(certifi.where())") $(EXPORT_PYTHON) scripts/export_person_detector.py --output-dir $(MODELS_DIR) $(APPROVE_FLAG)
	$(EXPORT_PYTHON) scripts/fetch_face_model.py --output-dir $(MODELS_DIR) $(APPROVE_FLAG)

$(EXPORT_VENV)/bin/python:
	python3.14 -m venv $(EXPORT_VENV)
	$(EXPORT_VENV)/bin/python -m pip install -e ".[vision]" -r requirements-model-export.txt certifi
