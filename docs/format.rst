Specification Format
====================

Provenance
----------

.. code-block:: text

    "MUSE FITS Keyword Master" spreadsheet  (exported as CSV)
                  ->  src/muse_fits_specifications/specs/keywords.csv

The keyword sheet is the master source; the :doc:`keywords` page shows it whole, with an X column per level.
The loader, the header validator and the generated keyword reference pages all read the same file, so they cannot drift apart.
An earlier DKIST-style set of per-section YAML files, bootstrapped from the xlsx on 2026-08-18, was replaced by the sheet on 2026-09-22.

Layout
------

- ``specs/keywords.csv``: one row per keyword; installed, it is ``muse_fits_specifications.SHEET_PATH``.
  An ``X`` in a level column (``L0``..``L3``) means the card is present in every file of that level; a keyword is never optional.
  The ``ISP`` column duplicates ``L0`` and is ignored.
- ``specs/<level>/_meta.toml``: what the sheet lacks: spec name, version, title, source document and HDU layout.
  A level without one cannot be loaded; add the file when a level is defined, and its page will appear on the next build.
  ``spec_version`` must be a quoted string, such as ``"0.1"``; the loader rejects a bare number.

Sheet Columns
-------------

.. list-table::
   :header-rows: 1

   * - Column
     - Meaning
   * - ``FITS KW``
     - The keyword. Trailing padding is stripped.
       Blank or ``tbd`` marks an ISP field with no keyword assigned yet: such rows are skipped by validation and listed on the level page as unassigned.
   * - ``Type``
     - ``Integer``/``String``/``Float``/``Boolean``; blank means no type check.
       An integer value is accepted where ``Float`` is specified, not vice versa.
   * - ``Lower Limit`` / ``Upper Limit``
     - Inclusive numeric range; only allowed with a numeric ``Type``.
   * - ``FITS Comment``
     - The card comment. On ISP rows this is the ISP mnemonic.
   * - ``Comment``
     - Free-text notes.

The sheet must contain exactly the documented columns, including ``ISP`` and ``L0`` through ``L3``, with no duplicate columns.
Nonblank rows must have one cell per column, and level markers must be ``X`` (case-insensitive) or blank.
Blank separator lines are allowed; quote comments containing commas when exporting CSV.

Sheet typos fail loudly: ``load_spec`` raises ``SpecDefinitionError`` for malformed CSV, an illegal keyword (anything but 1-8 characters of ``A-Z0-9_-``), an unknown ``Type``, a limit on a non-numeric type, an unparsable or non-finite limit, a lower limit above the upper one, a row marked for no level, or a keyword listed twice for one level.
A malformed ``_meta.toml`` raises the same error, naming the file and field.
Row errors include their row number; duplicate-keyword errors identify the keyword and level.
``python -m muse_fits_specifications`` runs every check and also fails when the sheet marks a level that has no ``_meta.toml``; pre-commit runs it whenever a file under ``specs/`` changes.
Documentation builds render only the defined levels.

Updating the Sheet
------------------

1. Export the spreadsheet as CSV over ``src/muse_fits_specifications/specs/keywords.csv``.
2. ``git diff`` shows the change row by row.
   ``.gitattributes`` normalizes the file's line endings, so an export from a different tool does not rewrite every line.
3. Commit: the pre-commit hook runs ``python -m muse_fits_specifications`` against the source tree and rejects a malformed row with its row number.
   Run ``pytest --pyargs muse_fits_specifications`` too; the astropy round-trip test proves every mission keyword survives a compressed write and read.
4. Bump ``spec_version`` in each level's ``_meta.toml``, build the docs (``tox -e build_docs``) and commit.

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

- Most level 0 rows are ISP fields without a FITS keyword yet (plus one ``tbd``); they are listed as unassigned until the sheet names them.
- Levels 2 and 3 have columns in the sheet but no rows and no ``_meta.toml`` yet.
- The sheet has no columns for allowed values, example values or timestamp format, so those checks do not exist; add a column and the loader can grow the check.
- One row per keyword means one type and one range across all levels; give a keyword two rows if that ever differs.
