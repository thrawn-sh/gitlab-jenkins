all: verify

initialise:
	@echo [pip] installing requirements
	@pipenv install

verify: initialise
	@echo [linit] checking source
