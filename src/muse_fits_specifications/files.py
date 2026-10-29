"""
Build headers, and generate and check whole MUSE FITS files, against a loaded spec.

Needs astropy: ``pip install "muse-fits-specifications[fits]"``. Files can be generated
and checked only for a level whose HDU layout is settled (``Spec.provisional`` false),
which is Level 0 today. The sheet does not yet say which HDU of a multi-HDU file carries
each keyword, so the keywords go in the first extension's header, as Level 0 has them.

``python -m muse_fits_specifications.files example level0 out.fits`` writes a conforming
example file, and ``python -m muse_fits_specifications.files validate level0 in.fits``
prints every way a file breaks the spec.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

try:
    import numpy as np
    from astropy.io import fits
except ImportError as error:
    msg = 'muse_fits_specifications.files needs astropy: pip install "muse-fits-specifications[fits]"'
    raise ImportError(msg) from error

from .spec import FAMILIES, LEVELS, SpecDefinitionError, example_header, families, load_spec
from .validation import validate

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from os import PathLike

    from .spec import HduSpec, Spec

_CARD_WIDTH = 80
_VALUE_END = 30  # a fixed-format value fills columns 11 to 30; a comment follows it
_CHECKSUM_VALID, _CHECKSUM_MISSING = 1, 2
# CompImageHDU subclasses ImageHDU, so an image is anything but a compressed image.
_KINDS: dict[str, Callable[[Any], bool]] = {
    "compressed-image": lambda hdu: isinstance(hdu, fits.CompImageHDU),
    "image": lambda hdu: isinstance(hdu, fits.ImageHDU) and not isinstance(hdu, fits.CompImageHDU),
    "table": lambda hdu: isinstance(hdu, fits.BinTableHDU),
}


def _card(name: str, value: object, comment: str) -> fits.Card:
    """
    A card with as much of ``comment`` as fits beside its value on one 80-character
    line.
    """
    if isinstance(value, datetime):
        # FITS times carry no offset: an aware datetime is written in UTC.
        value = (value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value).isoformat()
    elif isinstance(value, np.generic):
        value = value.item()
    bare = fits.Card(name, value).image
    # A value longer than one card continues on CONTINUE cards and keeps no comment.
    room = 0 if len(bare) > _CARD_WIDTH else _CARD_WIDTH - max(len(bare.rstrip()), _VALUE_END) - len(" / ")
    return fits.Card(name, value, comment[:room] if room > 0 else "")


def build_header(spec: Spec, values: Mapping[str, Any] | None = None, *, fill: bool = False) -> fits.Header:
    """
    A FITS header holding ``values`` in sheet order, with the sheet's comments.

    A keyword of ``spec`` missing from ``values`` is left out, so
    :func:`~muse_fits_specifications.validation.validate` reports it, unless ``fill`` is true,
    which takes its :func:`~muse_fits_specifications.spec.example_header` value. Keys
    ``spec`` does not define follow in the order given, without a comment, for cards the
    sheet lacks so far. Keys are upper-cased, as FITS keywords ignore case, and numpy
    scalars become Python values. A ``datetime`` is written as ISO 8601, in UTC when it
    is aware. Library-owned cards are refused: the FITS library writes them.
    """
    given = dict(values or {})
    values = {name.upper(): value for name, value in given.items()}  # FITS keywords ignore case
    if len(values) != len(given):
        msg = f"values name a keyword twice in different cases: {sorted(given)}"
        raise ValueError(msg)
    defaults = example_header(spec) if fill else {}
    header = fits.Header()
    for name, kw in spec.keywords.items():
        if kw.library_owned:
            continue
        if name in values:
            header.append(_card(name, values.pop(name), kw.comment))
        elif name in defaults:
            header.append(_card(name, defaults[name], kw.comment))
    for name, value in values.items():
        if name in spec.keywords:
            msg = f"{name} is library-owned: the FITS library writes it"
            raise ValueError(msg)
        header.append(_card(name, value, ""))
    return header


def _hdu_name(declared: HduSpec, keywords: Mapping[str, Any]) -> str:
    """
    The HDU's EXTNAME, which astropy upper-cases; ``{CAMERA}`` stands for the CAMERA
    card.
    """
    return declared.name.replace("{CAMERA}", str(keywords.get("CAMERA", ""))).upper()


def _require_settled(spec: Spec) -> None:
    if spec.provisional:
        msg = f"{spec.name}'s HDU layout is provisional, so its files cannot be generated or checked yet"
        raise ValueError(msg)


def example_file(spec: Spec, data: np.ndarray | None = None, values: Mapping[str, Any] | None = None) -> fits.HDUList:
    """
    A conforming file: an empty primary HDU, then ``spec``'s HDUs in order.

    The first extension carries :func:`build_header` of ``values`` with ``fill`` on, and
    every image HDU holds ``data``, a small zero image by default. Write it with
    ``writeto(path, checksum=True)``.
    """
    _require_settled(spec)
    data = np.zeros((4, 4), dtype=np.int16) if data is None else data
    hdus: list[fits.hdu.base.ExtensionHDU] = []
    keywords = build_header(spec, values, fill=True)
    for declared in spec.hdus:
        header = keywords if not hdus else None
        name = _hdu_name(declared, keywords)
        if declared.kind == "compressed-image":
            options = {"compression_type": declared.compression} if declared.compression else {}
            hdus.append(fits.CompImageHDU(data, header=header, name=name, **options))
        elif declared.kind == "image":
            hdus.append(fits.ImageHDU(data, header=header, name=name))
        else:
            msg = f"cannot generate a {declared.kind!r} HDU ({declared.name})"
            raise ValueError(msg)
    return fits.HDUList([fits.PrimaryHDU(), *hdus])


def validate_file(file: str | PathLike[str] | fits.HDUList, spec: Spec, *, checksums: bool = False) -> list[str]:
    """
    Return every way ``file`` breaks ``spec``'s HDU layout or keywords; empty means
    valid.

    Checks for an empty primary HDU, then exactly ``spec``'s HDUs in order (name, kind
    and compression), then :func:`~muse_fits_specifications.validation.validate` on the first
    extension's header. ``checksums=True``, for a path only, also requires a correct
    CHECKSUM and DATASUM on every HDU as stored.
    """
    _require_settled(spec)
    if isinstance(file, fits.HDUList):
        if checksums:
            msg = "checksums are verified from a path, on the file as stored"
            raise ValueError(msg)
        return _validate_hdul(file, spec)
    with fits.open(file) as hdul:
        errors = _validate_hdul(hdul, spec)
    if checksums:
        # Compressed HDUs keep their checksums on the stored table, which this view shows.
        with fits.open(file, disable_image_compression=True) as stored:
            for position, hdu in enumerate(stored):
                for verify, card in ((hdu.verify_checksum, "CHECKSUM"), (hdu.verify_datasum, "DATASUM")):
                    state = verify()
                    if state == _CHECKSUM_MISSING:
                        errors.append(f"HDU {position} is missing {card}")
                    elif state != _CHECKSUM_VALID:
                        errors.append(f"HDU {position} fails its {card}")
    return errors


def _validate_hdul(hdul: fits.HDUList, spec: Spec) -> list[str]:
    errors = []
    if not isinstance(hdul[0], fits.PrimaryHDU) or hdul[0].header.get("NAXIS", 0) != 0:
        errors.append("HDU 0 must be an empty primary HDU")
    names = ", ".join(hdu.name for hdu in spec.hdus)
    if len(hdul) != len(spec.hdus) + 1:
        errors.append(f"expected an empty primary HDU plus {names}, got {len(hdul)} HDUs")
    keywords = hdul[1].header if len(hdul) > 1 else {}
    for position, (actual, declared) in enumerate(zip(hdul[1:], spec.hdus, strict=False), 1):
        if actual.name.upper() != (name := _hdu_name(declared, keywords)):
            errors.append(f"HDU {position} must be named {name}, got {actual.name}")
        if not _KINDS[declared.kind](actual):
            errors.append(f"HDU {position} ({declared.name}) must be a {declared.kind}, got {type(actual).__name__}")
        elif declared.compression and actual.compression_type != declared.compression:
            errors.append(
                f"HDU {position} ({declared.name}) must use {declared.compression}, got {actual.compression_type}"
            )
    if len(hdul) > 1:
        errors += validate(hdul[1].header, spec)
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    """
    ``example LEVEL PATH`` writes a conforming file; ``validate LEVEL PATH`` prints each
    error and exits 1 when there are any.

    ``--family CI|SG`` picks the camera type of a level that differs by it. ``validate``
    also requires correct checksums.
    """
    parser = argparse.ArgumentParser(prog="python -m muse_fits_specifications.files")
    commands = parser.add_subparsers(dest="command", required=True)
    for command, description in (
        ("example", "write a conforming example file"),
        ("validate", "print every way a file breaks the spec"),
    ):
        sub = commands.add_parser(command, help=description)
        sub.add_argument("level", choices=LEVELS)
        sub.add_argument("path")
        sub.add_argument("--family", choices=FAMILIES)
    args = parser.parse_args(argv)
    if args.family and families(args.level) == (None,):
        parser.error(f"{args.level} does not differ between CI and SG files; leave out --family")
    try:
        spec = load_spec(args.level, args.family)
        if args.command == "example":
            example_file(spec).writeto(args.path, checksum=True)
            return 0
        errors = validate_file(args.path, spec, checksums=True)
    except (OSError, ValueError, SpecDefinitionError) as error:  # a missing or non-FITS file is an OSError
        parser.error(str(error))
    sys.stdout.write("".join(f"{error}\n" for error in errors))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
