MUSE FITS Specifications
========================

Machine-readable MUSE FITS keyword specifications and header validation, modeled on the DKIST Data Center's ``dkist-fits-specifications`` and ``dkist-header-validator``.

The mission keyword sheet, ``src/muse_fits_specifications/specs/keywords.csv``, is the source of truth for the keywords; it is converted into one YAML file per section under ``specs/keywords/``, and each level's ``_meta.toml`` adds its name, version and HDU layout.
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
    python -m pip install ".[fits]"

Replace ``observation_level0.fits`` below with the path to your Level 0 file.
For a Level 1 file, use ``load_spec("level1", "SG")`` or ``load_spec("level1", "CI")``: those levels differ by camera type.
The example checks the file's HDU layout and the compressed image extension's header, and prints every error:

.. code-block:: python

    from astropy.io import fits
    from muse_fits_specifications import load_spec
    from muse_fits_specifications.files import validate_file

    spec = load_spec("level0")
    with fits.open("observation_level0.fits", checksum=True) as hdul:
        errors = validate_file(hdul, spec)

    if errors:
        print("\n".join(errors))
    else:
        print("Header passes the draft's keyword checks.")

For example, a missing frame sequence number produces:

.. code-block:: text

    missing keyword FSN

From a shell, ``python -m muse_fits_specifications.files validate level0 observation_level0.fits`` prints the same errors, and also requires a correct ``CHECKSUM`` and ``DATASUM`` on every HDU, and ``python -m muse_fits_specifications.files example level0 example.fits`` writes a file that passes, to test a Level 0 writer against.
Files can be generated and checked only for levels whose HDU layout is settled, Level 0 today; the others are provisional.
To check one header without astropy, use ``validate(header, spec)``, or ``ensure_valid(header, spec)`` for a ``HeaderValidationError`` on failure.
``files.build_header(spec, values)`` builds a header in sheet order with the sheet's comments, for writers of every level.
The checks cover keyword presence, types, numeric limits and allowed values defined in the current draft.
Unassigned fields are not checked; a passing result does not imply the specification is complete.

``checksum=True`` separately asks Astropy to verify existing ``CHECKSUM`` and ``DATASUM`` cards.
Checksum failures are reported as Astropy warnings, not entries in ``errors``; checksum checking is off by default.

The header validator accepts any mapping, so astropy is needed only for ``muse_fits_specifications.files`` (the ``fits`` extra).
Keywords not in the spec are ignored; sheet typos fail loudly when the sheet is converted and in the check that pre-commit and the tests run.

Reading the Sheet
-----------------

The installed package carries the sheet and the YAML generated from it; ``SHEET_PATH`` and ``KEYWORDS_PATH`` point at them.
Tools outside Python can read the YAML directly, in the order ``_sections.yml`` gives:

.. code-block:: python

    import yaml
    from muse_fits_specifications import KEYWORDS_PATH

    names = yaml.safe_load((KEYWORDS_PATH / "_sections.yml").read_text(encoding="utf-8"))
    sections = [yaml.safe_load((KEYWORDS_PATH / name).read_text(encoding="utf-8")) for name in names]

The :doc:`keywords` page shows the same rows and offers the sheet for download.
