wallet-action-markets/
│
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
│
├── config/
│   ├── market_spec.json
│   └── settings.py
│
├── data/
│   ├── raw/
│   ├── cache/
│   └── snapshots/
│
├── src/
│   ├── fetcher/
│   ├── resolver/
│   ├── market/
│   ├── settlement/
│   └── utils/
│
├── api/
│   └── app.py
│
├── tests/
│   ├── test_fetcher.py
│   ├── test_resolver.py
│   └── test_market.py
│
├── scripts/
│   ├── run_market.py
│   ├── replay_event.py
│   └── backfill_history.py
│
└── docs/
    ├── architecture.md
    └── decision_log.md
