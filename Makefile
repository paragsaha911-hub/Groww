.PHONY: ingest chunk-exp query demo ui eval coverage sources sample-qa test dirs

dirs:
	@python -c "from app import config; config.ensure_dirs(); print('data dirs ready')"

ingest:
	@echo "[ingest] not implemented yet - Phase 4/5/8/9"

chunk-exp:
	@echo "[chunk-exp] not implemented yet - Phase 7"

query:
	@echo "[query] not implemented yet - Phase 12"

demo:
	@echo "[demo] not implemented yet - Phase 13"

ui:
	@echo "[ui] not implemented yet - Phase 13"

eval:
	@echo "[eval] not implemented yet - Phase 14"

coverage:
	@echo "[coverage] not implemented yet - Phase 14"

sources:
	@echo "[sources] not implemented yet - Phase 6"

sample-qa:
	@echo "[sample-qa] not implemented yet - Phase 15"

test:
	@python -m pytest -q
