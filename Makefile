# Transfer Predictions — data build & governance targets.
# Every ingest module also runs its offline _check() with no args:
#   python3 -m ingest.<name>
PY := PYTHONPATH="$(CURDIR)" python3

.PHONY: audit data warehouse data-index checks clean-warehouse

## audit — data contracts (the regression guard for silent column drops)
audit:
	$(PY) -m validate.audit

## checks — every module's offline self-check (fast, no network/disk build)
checks:
	@for m in ingest.understat ingest.crosswalk ingest.crosswalk_players \
	          ingest.players_master ingest.fbref_perf ingest.contracts \
	          ingest.injuries ingest.wages ingest.wages_fifa ingest.data_index \
	          ingest.warehouse impact.usage impact.wowy impact.xg_model \
	          impact.talent impact.evidence validate.talent_gate; do \
	  printf "%-26s " $$m; $(PY) -m $$m 2>&1 | grep -v Warning | tail -1; \
	done

## data — rebuild the canonical layer in dependency order (slow; network + rds)
data:
	$(PY) -m ingest.crosswalk_players build
	$(PY) -m ingest.players_master build
	$(PY) -m ingest.fbref_perf build
	$(PY) -m ingest.contracts build
	$(PY) -m ingest.injuries build
	$(PY) -m ingest.wages_fifa build
	$(MAKE) warehouse
	$(MAKE) data-index

## warehouse — assemble the single-source-of-truth DuckDB over built artifacts
warehouse:
	$(PY) -m ingest.warehouse build

## data-index — regenerate DATA_INDEX.md + per-folder data/*/README.md
data-index:
	$(PY) -m ingest.data_index build
	$(PY) -m ingest.data_index readmes

clean-warehouse:
	rm -f data/warehouse.duckdb data/understat/shots.parquet
