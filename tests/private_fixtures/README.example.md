# Private fixture workflow

Place locally authorized PDFs in this directory only. Everything here is ignored
except this instructions file. Public and CI tests must use synthetic fixtures.

Never commit customer documents. Run private-fixture tests explicitly; their
absence must not fail the public suite.
