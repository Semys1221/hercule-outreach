ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
export PYTHONPATH := $(ROOT):$(ROOT)/scraper:$(ROOT)/clean
VENV := $(ROOT).venv/bin/python

.PHONY: venv dev-scraper dev-clean scraper scrapper cleaner test test-scraper clean-cli-credits

venv:
	python3 -m venv $(ROOT).venv
	$(VENV) -m pip install -q --upgrade pip
	$(VENV) -m pip install -q -r $(ROOT)requirements.txt

dev-scraper:
	cd $(ROOT)scraper && streamlit run app.py

dev-clean:
	cd $(ROOT)clean && streamlit run app.py

scraper: dev-scraper

scrapper: dev-scraper

cleaner: dev-clean

test-scraper:
	cd $(ROOT)scraper && python -m pytest tests/ -q

test: test-scraper

clean-cli-credits:
	cd $(ROOT)clean && python cli.py credits
