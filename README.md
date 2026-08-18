# muse-fits-specifications

Machine-readable MUSE FITS keyword specifications and header validation.

One directory of small per-section YAML files per data level is the single source of truth for the mission's FITS keyword contract.
The loader, the header validator, and the generated keyword reference docs all read the same YAML, so they cannot drift apart.

The mechanism is modeled on the DKIST Data Center's [`dkist-fits-specifications`](https://bitbucket.org/dkistdc/dkist-fits-specifications) and [`dkist-header-validator`](https://bitbucket.org/dkistdc/dkist-header-validator).

## License

BSD 3-clause; see `LICENSE`.
