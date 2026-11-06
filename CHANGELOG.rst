0.1.0 (unreleased)
==================

- Initial draft specification: the mission keyword sheet ("MUSE FITS Keyword Master", packaged as ``specs/keywords.csv``) is the single source of truth for all levels.
- A converter that validates the sheet, a loader, a header validator (presence, type, inclusive limits; cards astropy owns are skipped), a conforming example header for generators, ``SHEET_PATH`` for reading the packaged sheet, a ``python -m muse_fits_specifications`` sheet check run by pre-commit, and build-time-generated keyword reference docs.
