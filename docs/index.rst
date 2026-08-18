MUSE FITS Specifications
========================

Machine-readable MUSE FITS keyword specifications and header validation, modeled on the DKIST Data Center's ``dkist-fits-specifications`` and ``dkist-header-validator``.

One directory of small per-section YAML files per data level — under ``src/muse_fits_specifications/specs/`` — is the single source of truth.
The loader, the header validator, and the keyword reference pages below all read the same YAML; the reference pages are regenerated on every docs build.

.. toctree::
   :maxdepth: 1

   format
   level0
   level1
   reference
   changelog

Quick Start
-----------

.. code-block:: python

    from astropy.io import fits
    from muse_fits_specifications import load_spec, validate, ensure_valid

    spec = load_spec("level0")
    with fits.open(path) as hdul:
        errors = validate(hdul[1].header, spec)   # list of problems, [] if valid
        ensure_valid(hdul[1].header, spec)        # raises HeaderValidationError

The validator accepts any mapping, so astropy is not a dependency of this package.
Keywords not in the spec are ignored; spec-file typos fail loudly at ``load_spec`` time.
