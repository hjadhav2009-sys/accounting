# Private Fixture Workflow

`tests/private_fixtures/` is ignored except for `README.example.md`. A developer
may place specifically authorized local PDFs there and run opt-in tests. Tests
must skip cleanly when fixtures are absent, must not print extracted private
fields, and must never make public CI depend on those files. Sanitized/synthetic
fixtures are required for committed tests.
