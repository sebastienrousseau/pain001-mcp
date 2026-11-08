# Tool catalogue

Every tool the server registers, with the description an agent sees and the
arguments it accepts. Generated from the running server by
`scripts/tool_catalogue.py`; CI fails if this file drifts from the code.

29 tools. Every one returns JSON; a failure is an `{"error": ...}`
payload, never an exception.

## `list_message_types`

List every supported ISO 20022 pain message type and its human name.

Arguments: none

## `get_required_fields`

List only the required input field names for a pain message type.

Arguments: `message_type`

## `get_input_schema`

Return the full JSON Schema for a message type's flat input record.

Arguments: `message_type`

## `validate_records`

Validate flat records against a message type's input JSON Schema.

Arguments: `message_type`, `records`, `identifier_checks` (optional)

## `suggest_record_fix`

Suggest deterministic, review-only fixes to non-financial fields.

Arguments: `record`, `validation_error`, `message_type` (optional)

## `validate_identifier`

Validate a single financial identifier (IBAN or BIC).

Arguments: `kind`, `value`

## `generate_message`

Generate a validated ISO 20022 pain XML message from in-memory records.

Arguments: `message_type`, `records`, `identifier_checks` (optional)

## `list_supported_formats`

List the on-disk data formats the pain001 loader can read.

Arguments: none

## `generate_message_async`

Generate validated pain XML off the event loop, for large batches.

Arguments: `message_type`, `records`, `identifier_checks` (optional)

## `generate_message_from_file`

Generate validated pain XML from a CSV file on the local disk.

Arguments: `message_type`, `data_file_path`

## `parse_camt053`

Parse a camt.053 bank-statement XML file on disk into structured data.

Arguments: `xml_file_path`, `xsd_file_path` (optional)

## `parse_pain002`

Parse a pain.002 payment-status report file on disk into structured data.

Arguments: `xml_file_path`, `xsd_file_path` (optional)

## `inspect_template`

Return the CSV column headers the message type's bundled template uses.

Arguments: `message_type`

## `validate_payment_scheme`

Validate records against a payment-scheme rulebook (e.g. SEPA).

Arguments: `records`, `profile` (optional)

## `list_scheme_profiles`

List every payment-scheme rulebook profile the core ships.

Arguments: none

## `simulate_payment_batch`

Simulate and pre-flight a payment batch before XML generation.

Arguments: `message_type`, `records`, `scheme` (optional)

## `migrate_records`

Migrate flat payment records between two pain.001 schema versions.

Arguments: `records`, `from_version`, `to_version`

## `validate_xml_against_schema`

Validate a raw pain.001 / pain.008 XML string against its official XSD.

Arguments: `xml_content`, `message_type`

## `sanitize_to_iso20022_charset`

Sanitise one free-text field to a SWIFT / ISO 20022 character set.

Arguments: `value`, `charset` (optional)

## `convert_mt101`

Convert a legacy SWIFT MT101 message into pain.001-ready records.

Arguments: `mt101_text`

## `list_corpus_files`

List the example files pain001 ships: market scenarios and coverage sets.

Arguments: `kind` (optional), `country` (optional), `version` (optional)

## `get_corpus_file`

Return the XML of one validated example file from the market corpus.

Arguments: `scenario_id`, `version`, `variant` (optional)

## `get_corpus_provenance`

Return the provenance sidecar of one example file.

Arguments: `scenario_id`, `version`, `variant` (optional)

## `get_corpus_coverage`

Return the schema coverage verdict of one message type's coverage set.

Arguments: `version`

## `list_faces`

List the faces: the standards a pain.001 document can be projected into.

Arguments: none

## `project_face`

Project a pain.001 document into another standard's JSON shape.

Arguments: `xml_content`, `face`, `version` (optional), `bindings` (optional)

## `stage_payment_batch`

Stage a payment batch for simulation and a confirmed commit.

Arguments: `message_type`, `records`, `scheme` (optional)

## `simulate_clearing`

Simulate settlement and clearing network execution for a staged batch.

Arguments: `stage_id`, `clearing_system` (optional)

## `commit_payment_batch`

Commit a staged payment batch with its confirmation token.

Arguments: `stage_id`, `confirmation_token`, `output_file_path` (optional)
