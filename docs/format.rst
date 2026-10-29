Specification Format
====================

Provenance
----------

.. code-block:: text

    "MUSE FITS Keyword Master" spreadsheet  (exported as CSV)
        ->  src/muse_fits_specifications/specs/keywords.csv
        ->  src/muse_fits_specifications/specs/keywords/*.yml  (python -m muse_fits_specifications.sheet)
        ->  loader, header validator and reference pages

The keyword sheet is the master source: the team edits the spreadsheet and exports it over ``keywords.csv``.
``python -m muse_fits_specifications.sheet`` converts the export into ``specs/keywords/``, one YAML file per sheet section, which the loader, the header validator and the generated reference pages all read, so they cannot drift apart.
All of it is committed: the YAML diff shows which topics an export changed, one keyword per block, however the spreadsheet ordered or quoted the CSV.
The :doc:`keywords` page shows the whole sheet with a column per level.
An earlier DKIST-style set of per-section YAML files, bootstrapped from the xlsx on 2026-08-18, was replaced by the sheet on 2026-09-22.

Layout
------

- ``specs/keywords.csv``: the sheet export, one row per keyword; installed, it is ``muse_fits_specifications.SHEET_PATH``.
- ``specs/keywords/``: generated from the sheet, never edited by hand; installed, it is ``muse_fits_specifications.KEYWORDS_PATH``.
  Each section of the sheet is one file named after its title, such as ``exposure-and-timing.yml`` (``untitled.yml`` for the rows above the first section row), and ``_sections.yml`` lists the files in sheet order, so the sheet sets the order.
  Renaming a section renames its file; two titles that give one file name are rejected.
  A keyword records the levels whose files carry it (``all``, ``CI`` or ``SG``), its type, its range or allowed values, its comment, notes and ISP mnemonic, and whether the FITS library owns it.
- ``specs/<level>/_meta.toml``: what the sheet lacks: spec name, version, title, source document and HDU layout.
  ``spec_version`` must be a quoted string, such as ``"0.1"``; the loader rejects a bare number.
  Each ``[[hdus]]`` table is one extension after the empty primary HDU, in file order: its ``name``, ``kind``, optional ``compression``, and optional ``family`` (``CI`` or ``SG``) for an extension that only that camera type's files have.
  ``per_camera = true`` marks a level whose CI and SG files differ; only such a level may hold CI- or SG-only keywords or HDUs.

Levels and Camera Types
-----------------------

A keyword is never optional: a level's files carry every keyword marked for that level.
A level whose ``_meta.toml`` sets ``per_camera = true`` (Levels 1 and 2) is loaded per camera type, as in ``load_spec("level1", "SG")``, and each camera type gets its own reference page.
The flag, not the sheet, decides this, so a weekly export cannot change which levels need a camera type: a CI- or SG-only row in any other level fails the check.
``muse_fits_specifications.families(level)`` says whether a level is split this way.
A keyword may have one row per camera type, as ``PC1_1`` does, because its meaning differs between CI and SG files.

Sheet Columns
-------------

.. list-table::
   :header-rows: 1

   * - Column
     - Meaning
   * - ``FITS KW``
     - The keyword: 1-8 characters of ``A-Z0-9_-``; padding is stripped.
       Blank or ``tbd`` marks an ISP field with no keyword assigned yet: such rows are never validated and are listed on the level page as unassigned.
       A row whose ``FITS KW`` starts with ``#`` is a section row: its ``Type`` cell names the section of the rows below it, and a blank ``Type`` makes it a spacer.
   * - ``Type``
     - ``str``, ``bool``, ``int``, ``float``, ``float32``, ``float64``, ``ISO 8601`` (a timestamp string), or a sized integer such as ``uint8``, ``uint16``, ``uint32`` or ``int16``.
       A sized integer's range bounds the row's limits and allowed values, and fills a blank limit.
       Blank means no type check.
       An integer value is accepted where a float is specified, not vice versa.
   * - ``ISP``
     - Not used.
   * - ``L0`` to ``L3``
     - ``X`` when every file of the level carries the card, ``CI`` or ``SG`` when only that camera type's files do, blank otherwise.
       A row marked for no level is parked: it stays in the YAML and on the :doc:`keywords` page but in no level.
   * - ``Lower Limit``
     - A number, the inclusive minimum; or ``;``-separated allowed values, such as ``8;16;32`` or ``CI; SG108``.
       Double quotes around a value are dropped, and a ``bool`` value is ``T`` or ``F``.
       A non-numeric ``Type`` can only list allowed values.
   * - ``Upper Limit``
     - The inclusive maximum, for a numeric ``Type`` without allowed values.
   * - ``FITS Comment``
     - The card comment.
   * - ``Comment``
     - Free-text notes.
   * - ``ISP mnemonic``
     - The ISP field the value comes from.

The sheet must contain exactly these columns, in any order, with no duplicates.
Nonblank rows must have one cell per column; level markers are case-insensitive.
Blank separator lines are allowed; quote comments containing commas when exporting CSV.

Sheet typos fail loudly: the converter raises ``SpecDefinitionError`` with the row number for malformed CSV, an illegal keyword, an unknown ``Type``, a limit without a ``Type``, an unparsable or non-finite limit, a lower limit above the upper one, a limit or value outside a sized integer's range, an upper limit beside allowed values, an unknown level marker, or a keyword listed twice for one level and camera type.
A malformed ``_meta.toml`` raises the same error, naming the file and field.
``python -m muse_fits_specifications`` runs every check: it fails when ``specs/keywords/`` is not what the sheet converts to, file by file, when the sheet marks a level that has no ``_meta.toml``, and when a level fails to load.
Pre-commit runs it whenever the sheet, the YAML, a ``_meta.toml`` or the converter changes, and the tests run it too.

Updating the Sheet
------------------

1. Export the spreadsheet as CSV over ``src/muse_fits_specifications/specs/keywords.csv``.
   ``.gitattributes`` normalizes the file's line endings, so an export from a different tool does not rewrite every line.
2. Run ``python -m muse_fits_specifications.sheet`` to regenerate ``specs/keywords/``; it also deletes the files of sections that are gone.
   A sheet error stops it with the row number: fix the row in the spreadsheet and export again.
3. Review ``git diff src/muse_fits_specifications/specs/keywords/``, which shows what the export changed, topic by topic.
4. Bump ``spec_version`` in each level's ``_meta.toml``, run ``pytest --pyargs muse_fits_specifications`` (the astropy round-trip test proves every mission keyword survives a compressed write and read), build the docs (``tox -e build_docs``), and commit the CSV, the YAML and the version bumps together.

Library-owned Cards
-------------------

Cards the FITS library writes and consumes itself are flagged ``library_owned`` by name and are never validated or generated:
``XTENSION``, ``BITPIX``, ``NAXIS*``, ``PCOUNT``, ``GCOUNT``, ``TFIELDS``, ``TTYPEn``, ``TFORMn``, ``Z*``, ``EXTNAME``, ``BZERO``, ``BSCALE``, ``CHECKSUM``, ``DATASUM``.
These cards describe the on-disk representation, but Astropy's ``CompImageHDU`` hides or rewrites them in ``hdul[1].header`` (verified with astropy 7.2, ``RICE_1``, and a file written with ``checksum=True``):

.. list-table::
   :header-rows: 1

   * - Cards
     - In ``hdul[1].header``
   * - ``TFIELDS``, ``Z*``, ``EXTNAME``, ``TTYPE1``, ``TFORM1``, ``CHECKSUM``, ``DATASUM``
     - Hidden.
   * - ``XTENSION``, ``BITPIX``, ``NAXIS``, ``NAXIS1``, ``NAXIS2``, ``PCOUNT``
     - Present with the decompressed image's values, not the on-disk ones.
   * - ``BZERO``, ``BSCALE``
     - Only written for unsigned data.

To inspect the cards actually written, open the raw table header with ``fits.open(path, disable_image_compression=True)``.
Astropy consumes the compression cards when decompressing the image.
It verifies existing ``CHECKSUM`` and ``DATASUM`` cards only when opened with ``fits.open(path, checksum=True)``; the default is ``False``.
Checksum failures produce warnings, and absent checksum cards are not reported as failures.
This package's header validator does not perform checksum verification.
See `Astropy's file-opening options <https://docs.astropy.org/en/stable/io/fits/api/files.html#astropy.io.fits.open>`_.
The test suite rebuilds this experiment so the rule cannot rot silently.

Current Known Caveats
---------------------

- The Level 2 and Level 3 HDU layouts are provisional: their ``_meta.toml`` files copy what the pipeline's placeholder writers produced on 2026-10-29.
- Allowed values are one set per row. ``CTYPE1`` lists ``WAVE`` and ``HPLN-TAN`` for every Level 1 and Level 2 file, so either passes for both camera types until the sheet gives it a row per camera type.
- ``ISO 8601`` keywords are checked as strings; the timestamp format itself is not checked.
