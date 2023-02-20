
PROFILE = default
PROJECT_NAME = burrocracia
PYTHON_INTERPRETER = python

#################################################################################
# COMMANDS                                                                      #
#################################################################################

## Install Python Dependencies
requirements:
	$(PYTHON_INTERPRETER) -m pip install -U pip setuptools wheel
	$(PYTHON_INTERPRETER) -m pip install -r requirements.txt

## Delete all compiled Python files
clean:
	find . -type f -name "*.py[co]" -delete
	find . -type d -name "__pycache__" -delete


serve:
	$(PYTHON_INTERPRETER) index.py

container:
	@bash -c "docker build -t burrocracia:latest  ."
	@echo "Docker container built."

docker: container
	@bash -c "docker run -d -p 28009:5000 burrocracia"


