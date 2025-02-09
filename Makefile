# Makefile
SHELL := /bin/bash

.PHONY: help
help:
	@echo "Commands:"
	@echo "style          : runs style formatting."
	@echo "down           : stops all running services, removes containers and volumes."
	@echo "up             : starts Docker daemon and Solr."
	@echo "schema         : sets up schema by uploading schema/field_types.json followed by schema/fields.json."
	@echo "populate   	  : populates Solr with the data files stored in /data/tech_videos_json."
	@echo "trec_eval      : downloads trec_eval source code and compiles it."
	@echo "test       	  : runs unit tests."
	@echo "update_configs : updates Solr's synonyms and stop words with custom files."
	@echo "reload_core    : reloads the Solr core to apply configuration changes."
	@echo "sys1    		  : runs all queries for system 1, gets the solr responses, runs trec_eval and generates p/r plots."
	@echo "sys2           : runs all queries for system 1, gets the solr responses, runs trec_eval and generates p/r plots."

.PHONY: style
style:
	isort src test --atomic
	black -l 100 src test
	flake8 src test

.PHONY: down
down:
	docker compose -f docker/docker-compose.yml down --remove-orphans -v

.PHONY: up
up:
	docker compose -f docker/docker-compose.yml up -d

.PHONY: update_configs
update_configs:
	docker cp ./solr_custom/synonyms.txt pri_solr:/var/solr/data/tech_videos/conf/synonyms.txt
	docker cp ./solr_custom/stopwords_en.txt pri_solr:/var/solr/data/tech_videos/conf/stopwords_en.txt

.PHONY: get_embeddings
get_embeddings:
	cd scripts/semantic_search && python3 get_embeddings.py && cd ../..

.PHONY: schema
schema:
	curl -X POST \
			-H 'Content-type:application/json' \
			--data-binary "@./docker/data/schema/field_types.json" \
			http://localhost:8983/solr/tech_videos/schema

	curl -X POST \
		-H 'Content-type:application/json' \
		--data-binary "@./docker/data/schema/schema.json" \
		http://localhost:8983/solr/tech_videos/schema

.PHONY: reload_core
reload_core:
	curl "http://localhost:8983/solr/admin/cores?action=RELOAD&core=tech_videos"

.PHONY: populate
populate:
	docker exec -it pri_solr bin/solr post -c tech_videos /data/video_collection/*.json

.PHONY: populate_semantic
populate_semantic:
	docker exec -it pri_solr bin/solr post -c tech_videos /data/video_collection_semantic/*.json

.PHONY: trec_eval
trec_eval:
	git clone https://github.com/usnistgov/trec_eval.git src/trec_eval
	cd src/trec_eval && make
	cd ../..

.PHONY: embedding_1
embedding_1:
	python3 ./scripts/semantic_search/query_embedding.py --query retrieval_config/queries/query1_sys2.json --uri http://localhost:8983/solr --collection tech_videos

.PHONY: embedding_2
embedding_2:
	python3 ./scripts/semantic_search/query_embedding.py --query retrieval_config/queries/query2_sys2.json --uri http://localhost:8983/solr --collection tech_videos

.PHONY: embedding_3
embedding_3:
	python3 ./scripts/semantic_search/query_embedding.py --query retrieval_config/queries/query3_sys2.json --uri http://localhost:8983/solr --collection tech_videos

.PHONY: sys1
sys1:
	./scripts/retrieval_eval/run_sys1_pipeline.sh

.PHONY: sys2
sys2:
	./scripts/retrieval_eval/run_sys2_pipeline.sh

.PHONY: sys2_semantic
sys2_semantic:
	./scripts/retrieval_eval/run_sys2_pipeline_semantic.sh