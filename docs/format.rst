Specification Format
====================

Provenance
----------

.. code-block:: text

    MUSEMW251165 ("MUSE FITS Keywords.xlsx")
                  →  src/muse_fits_specifications/specs/<level>/*.yml

The YAML files were bootstrapped on 2026-08-18 from the mission keyword spreadsheet ("MUSE FITS Keywords.xlsx", based on MUSEMW251165).

Layout
------

Each level is a directory of small per-section YAML files (like the DKIST ``spec122/schemas/`` layout): ``_meta.yml`` holds the spec-wide fields (name, version, source document, HDU layout); every other file holds one section's keywords.
A keyword defined in two sections of the same level is a load-time error.

Level 0 sections: ``fits``, ``compression``, ``observatory``, ``exposure``, ``downlink``, ``statistics``, ``isp``, plus the ISP telemetry split by subsystem — ``isp-camera``, ``isp-pointing``, ``isp-mechanisms``, ``isp-sequencer``, ``isp-thermal``.
Level 1 adds ``readout``, ``wcs``, ``pointing``, and ``data``.
The ISP subsystem assignment keys off the mnemonic prefixes (``M_AEC_*``, ``M_ISS_*``, ``M_TC_*``, …).

Keyword Fields
--------------

.. list-table::
   :header-rows: 1

   * - Field
     - Meaning
   * - ``required``
     - Must be present in a conforming header.
       Structural cards owned by the FITS library and keywords with unresolved ICD questions are recorded but not required.
   * - ``type``
     - One of ``bool``/``int``/``float``/``str``.
       Omitted when the source document does not pin the type down; omitted means no type check.
       An ``int`` value is accepted where ``float`` is specified, not vice versa.
   * - ``values``
     - Closed set of allowed values.
   * - ``format``
     - ``isot`` marks an ISO 8601 timestamp string.
   * - ``source``
     - The ISP mnemonic or other upstream source of the value.
   * - ``comment`` / ``example``
     - Documentation, verbatim from the source document.

Spec-file typos fail loudly: the loader validates the spec files themselves at ``load_spec`` time and raises ``SpecDefinitionError``.

Current Known Caveats
---------------------

- **Types were inferred** from the spreadsheet's example values; a keyword with no example carries no type and is only checked for presence.
  Type false positives during validation are findings to fold back into the YAML.
- **Structural cards** (tile-compression bookkeeping, ``CHECKSUM``/``DATASUM``, ``BZERO``/``BSCALE``, …) are recorded but never required: astropy owns them and hides some of them behind its ``CompImageHDU`` abstraction.
- Keywords whose spreadsheet comments carry unresolved ``???`` questions (``CRS_TYPE``, ``TSRN``…, ``FLAT_REC``, …) are optional until the ICD settles them.
- ``TSRN``/``TERN``/``TSCN``/``TECN`` are indexed keywords (N=1..8) kept literal; expansion is not modeled.
- Level 2 has no sheet in the source document yet; the spec grows a ``specs/level2/`` directory when the mission defines it.
