# muse-fits-specifications

Machine-readable MUSE FITS keyword specifications and header validation.

The mission keyword sheet, kept in `src/muse_fits_specifications/specs/keywords.csv`, is the source of truth for the mission's FITS keywords; each level's `_meta.toml` adds the spec name, version, title, source document and HDU layout.
The loader, the header validator, and the generated keyword reference docs all read the same files, so they cannot drift apart.
To update the spec, export the sheet over that file, review `git diff`, and commit: the pre-commit hook and the tests reject a malformed row with its row number.
`muse_fits_specifications.SHEET_PATH` points at the installed copy of the sheet for reading it directly.

This is modeled on the DKIST Data Center's [`dkist-fits-specifications`](https://bitbucket.org/dkistdc/dkist-fits-specifications) and [`dkist-header-validator`](https://bitbucket.org/dkistdc/dkist-header-validator).

## Development setup

You need git and Python 3.12 or newer.

1. Clone/fork the repository and move into it:

   ```bash
   git clone https://github.com/LM-SAL/muse-fits-specifications.git
   cd muse-fits-specifications
   ```

2. Create a virtual environment and activate it.
   A virtual environment keeps this project's packages apart from everything else on your machine.

3. Install the package in editable mode together with the test and docs tools, and turn on the pre-commit checks:

   ```bash
   python -m pip install -e ".[test,docs]" tox
   ```

   Editable mode (`-e`) makes Python import the code straight from this directory, so your edits take effect without reinstalling.

5. Check that everything works:

   ```bash
   pytest --pyargs muse_fits_specifications
   ```

To build the documentation, run `tox -e build_docs` and open `docs/_build/html/index.html`.
