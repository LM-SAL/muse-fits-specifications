MUSE FITS Specifications
========================

Machine-readable MUSE FITS keyword specifications and header validation, modeled on the DKIST Data Center's ``dkist-fits-specifications`` and ``dkist-header-validator``.

The mission keyword sheet, ``src/muse_fits_specifications/specs/keywords.csv``, is the source of truth for the keywords; each level's ``_meta.toml`` adds its name, version and HDU layout.
The loader, the header validator, and the keyword reference pages below all read the same files; the reference pages are regenerated on every docs build.

.. toctree::
   :maxdepth: 1
   :glob:

   Format <format>
   keywords
   level*
   reference
   changelog

Quick Start
-----------

In a Python 3.12 or newer environment, install the current draft from the repository.
Astropy is needed for this example to read a FITS file:

.. code-block:: bash

    git clone https://github.com/LM-SAL/muse-fits-specifications.git
    cd muse-fits-specifications
    python -m pip install . astropy

Replace ``observation_level0.fits`` below with the path to your Level 0 file.
For a Level 1 file, use ``load_spec("level1")``.
The example checks the compressed image extension's header and prints every validation error:

.. code-block:: python

    from astropy.io import fits
    from muse_fits_specifications import load_spec, validate

    spec = load_spec("level0")
    with fits.open("observation_level0.fits", checksum=True) as hdul:
        errors = validate(hdul[1].header, spec)

    if errors:
        print("\n".join(errors))
    else:
        print("Header passes the draft's keyword checks.")

For example, a missing frame sequence number produces:

.. code-block:: text

    missing keyword MSQ_FSN

Use ``ensure_valid(header, spec)`` instead of ``validate`` if you want a ``HeaderValidationError`` on failure.
The checks cover keyword presence, types, and numeric limits defined in the current draft.
Unassigned fields are not checked; a passing result does not imply the specification is complete.

``checksum=True`` separately asks Astropy to verify existing ``CHECKSUM`` and ``DATASUM`` cards.
Checksum failures are reported as Astropy warnings, not entries in ``errors``; checksum checking is off by default.

The validator accepts any mapping, so astropy is not a dependency of this package.
Keywords not in the spec are ignored; sheet typos fail loudly at ``load_spec`` time.

Reading the Sheet
-----------------

The installed package carries the sheet itself, and ``SHEET_PATH`` points at it:

.. code-block:: python

    import csv
    from muse_fits_specifications import SHEET_PATH

    with SHEET_PATH.open(encoding="utf-8-sig") as sheet:
        rows = list(csv.DictReader(sheet))

The :doc:`keywords` page shows the same file and offers it for download.
