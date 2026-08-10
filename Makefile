.PHONY: setup data demo test report api clean

export PYTHONPATH := src

setup:
	pip3 install -r requirements.txt

data:
	python3 -m marketstore.data.generate

real-data:
	python3 -m marketstore.data.yfinance_puller

real-data-vintage:
	python3 -c "from marketstore.data.yfinance_puller import build_vintage_history; \
	build_vintage_history(['AAPL','MSFT','GOOG','AMZN','NVDA','META','TSLA','JPM'])"

demo:
	python3 scripts/demo.py

test:
	pytest tests/ -q

report:
	python3 scripts/make_report.py

api:
	uvicorn marketstore.serving.api:app --reload

live-yfinance:
	LIVE_PROVIDER=yfinance LIVE_POLL_INTERVAL=15 uvicorn marketstore.serving.api:app --reload

live-finnhub:
	@test -n "$(FINNHUB_API_KEY)" || (echo "Set FINNHUB_API_KEY env var (free at finnhub.io)" && exit 1)
	LIVE_PROVIDER=finnhub FINNHUB_API_KEY=$(FINNHUB_API_KEY) uvicorn marketstore.serving.api:app --reload

clean:
	rm -rf data_raw/*.parquet results/* .pytest_cache __pycache__ \
	  src/marketstore/__pycache__ src/marketstore/**/__pycache__
