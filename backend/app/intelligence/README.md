# intelligence/

Pure, deterministic, DB-free language understanding. Returns Pydantic objects.

- `extraction.py`     transcript -> ExtractedReport (equipment code, symptoms, impact, safety, location)
- `classification.py` symptoms -> issue category
- `prioritization.py` ordered rule table -> priority + rule id + explanation
- `missing_fields.py` required-field check -> follow-up questions
- `response.py`       templated spoken/text responses per language
- `config/*.yaml`     taxonomy, priority rules, required fields, response templates

No LLM is used. Implemented in Phase 3.
