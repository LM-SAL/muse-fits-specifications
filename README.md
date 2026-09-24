# muse-fits-specifications

Machine-readable MUSE FITS keyword specifications and header validation.

One directory of small per-section YAML files per data level is the single source of truth for the mission's FITS keyword contract.
The loader, the header validator, and the generated keyword reference docs all read the same YAML, so they cannot drift apart.

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

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   On Windows, run `py -m venv .venv`, then `.\.venv\Scripts\Activate.ps1` in PowerShell or `.venv\Scripts\activate` in Command Prompt.
   Your prompt now starts with `(.venv)`. Activate the environment again in every new terminal; `deactivate` leaves it.

3. Install the package in editable mode together with the test and docs tools, and turn on the pre-commit checks:

   ```bash
   python -m pip install -e ".[test,docs]" tox pre-commit
   pre-commit install
   ```

   Editable mode (`-e`) makes Python import the code straight from this directory, so your edits take effect without reinstalling.
   `pre-commit install` makes git run the commit-stage hooks (formatting and linting) before every commit.

4. Check that everything works:

   ```bash
   pytest --pyargs muse_fits_specifications
   ```

To build the documentation, run `tox -e build_docs` and open `docs/_build/html/index.html`.
