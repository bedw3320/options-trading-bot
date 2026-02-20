# Derivation Manifest

Machine-readable configuration for processing skills.

```yaml
schema_version: 3
arscontexta_version: 0.8.0
preset: research
domain: options-trading

dimensions:
  granularity: atomic
  organization: flat
  linking: explicit
  processing: heavy
  navigation: 3-tier
  maintenance: condition-based
  schema: moderate
  automation: full

vocabulary:
  note_type: claim
  processing_verb: reduce
  connection_verb: reflect
  navigation_unit: topic map
  collection_name: notes
  capture_zone: inbox
  primary_verb: extract

extraction_categories:
  - academic-claim
  - parameter-range
  - greek-dynamic
  - failure-mode
  - regime-filter
  - open-question
  - trade-mechanic
  - instrument-profile

schema_fields:
  required:
    - description
    - category
    - topics
    - created
  optional:
    - source
    - confidence
    - instruments
    - parameters
    - superseded_by
    - validated_by

confidence_levels:
  - proven        # Backed by multiple academic studies
  - likely        # Single study or strong practitioner consensus
  - experimental  # Untested hypothesis or single-source claim
  - outdated      # Superseded by newer evidence

starter_mocs:
  - options-trading-overview
  - greeks-and-volatility
  - risk-reversals
  - open-questions

platform:
  name: claude-code
  hooks: true
  semantic_search: false

self_space: false
personality: neutral-analytical
```
