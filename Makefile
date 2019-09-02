all: verify

initialise:
	@echo [pip] installing requirements
	@pipenv install --dev

verify: initialise
	@echo [linit] checking source
	@pipenv run flake8 --ignore=E501 gitlab_jenkins.py
