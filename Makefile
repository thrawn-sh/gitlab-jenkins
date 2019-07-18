all: verify

initialise:
	@echo [pip] installing requirements
	@pip install --quiet --requirement requirements.txt

verify: initialise
	@echo [linit] checking source
