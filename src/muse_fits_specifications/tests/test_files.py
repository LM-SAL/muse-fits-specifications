"""
Checks for building headers and generating and validating whole files.
"""

from __future__ import annotations

import warnings
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from muse_fits_specifications import KeywordSpec, Spec, load_spec, validate

fits = pytest.importorskip("astropy.io.fits")
np = pytest.importorskip("numpy")

from muse_fits_specifications.files import build_header, example_file, main, validate_file  # noqa: E402


def test_build_header_follows_the_sheet_order_and_comments():
    spec = load_spec("level0")
    header = build_header(
        spec, {"EXTRA": "x", "FSN": 7, "DATE-OBS": datetime(2027, 1, 2, 5, 4, 5, tzinfo=timezone(timedelta(hours=2)))}
    )
    assert list(header) == ["DATE-OBS", "FSN", "EXTRA"]  # sheet order, then the rest as given
    assert header["DATE-OBS"] == "2027-01-02T03:04:05"  # in UTC, with no offset
    assert build_header(spec, {"DATE": datetime(2027, 1, 2, tzinfo=UTC)})["DATE"] == "2027-01-02T00:00:00"
    assert header.comments["FSN"] == spec.keywords["FSN"].comment
    assert header.comments["EXTRA"] == ""
    assert validate(build_header(spec, fill=True), spec) == []
    with pytest.raises(ValueError, match="EXTNAME is library-owned"):
        build_header(spec, {"EXTNAME": "OTHER"})


def test_build_header_keys_ignore_case_like_fits_keywords():
    spec = load_spec("level0")
    header = build_header(spec, {"fsn": 7}, fill=True)
    assert [value for key, value in header.items() if key == "FSN"] == [7]
    with pytest.raises(ValueError, match="twice in different cases"):
        build_header(spec, {"fsn": 1, "FSN": 2})
    with pytest.raises(ValueError, match="EXTNAME is library-owned"):
        build_header(spec, {"extname": "OTHER"})


def test_numpy_scalars_are_their_python_values():
    spec = load_spec("level0")
    header = build_header(spec, {"FSN": np.uint32(7)}, fill=True)
    assert type(header["FSN"]) is int
    assert validate(header, spec) == []
    typed = Spec(
        "s",
        "1",
        "t",
        "d",
        (),
        {
            "N": KeywordSpec("N", "int", 0, 10),
            "X": KeywordSpec("X", "float"),
            "B": KeywordSpec("B", "bool"),
        },
    )
    assert validate({"N": np.int64(3), "X": np.float32(1.5), "B": np.True_}, typed) == []
    assert len(validate({"N": np.int64(11), "X": np.float32(1.5), "B": np.int64(1)}, typed)) == 2


def test_build_header_shortens_a_comment_to_fit_one_card():
    spec = Spec("s", "1", "t", "d", (), {"LONG": KeywordSpec("LONG", "str", comment="c" * 100)})
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # astropy warns when it has to truncate a card itself
        for length in range(75):  # through the longest one-card string and into CONTINUE cards
            card = build_header(spec, {"LONG": "v" * length}).cards["LONG"]
            assert len(card.image) % 80 == 0, length
        assert build_header(spec, {"LONG": "value"}).cards["LONG"].comment.startswith("ccc")
        assert build_header(spec, {"LONG": 1.5}).cards["LONG"].comment.startswith("ccc")


def test_example_file_round_trips_and_validates(tmp_path):
    spec = load_spec("level0")
    path = tmp_path / "level0.fits"
    example_file(spec, data=np.ones((3, 5), dtype=np.uint16), values={"FSN": 42}).writeto(path, checksum=True)
    with fits.open(path, checksum=True) as hdul:
        assert validate_file(hdul, spec) == []
        assert hdul[1].header["FSN"] == 42
        assert hdul[1].data.shape == (3, 5)
    assert validate_file(path, spec) == []


def test_the_command_line_writes_and_checks_files(tmp_path, capsys):
    path = tmp_path / "example.fits"
    assert main(["example", "level0", str(path)]) == 0
    assert main(["validate", "level0", str(path)]) == 0
    assert capsys.readouterr().out == ""
    with fits.open(path, mode="update", checksum=True) as hdul:  # rewrites the checksums
        del hdul[1].header["FSN"]
    assert main(["validate", "level0", str(path)]) == 1
    assert capsys.readouterr().out == "missing keyword FSN\n"
    stored = path.read_bytes()  # change one stored card behind astropy's back
    card = b"ISP_VER =                    0"
    assert stored.count(card) == 1
    path.write_bytes(stored.replace(card, card[:-1] + b"1"))
    assert main(["validate", "level0", str(path)]) == 1
    assert capsys.readouterr().out == "missing keyword FSN\nHDU 1 fails its CHECKSUM\n"
    (tmp_path / "not.fits").write_text("not FITS")
    for argv in (
        ["example", "level1", str(path), "--family", "SG"],  # a provisional layout
        ["example", "level0", str(path), "--family", "SG"],  # level0 does not differ by camera type
        ["validate", "level0", str(tmp_path / "missing.fits")],
        ["validate", "level0", str(tmp_path / "not.fits")],
    ):
        with pytest.raises(SystemExit):
            main(argv)


def _broken(change) -> list[str]:
    spec = load_spec("level0")
    hdul = example_file(spec)
    change(hdul)
    return validate_file(hdul, spec)


def test_validate_file_reports_layout_and_keyword_errors():
    data = np.zeros((4, 4), dtype=np.int16)
    assert _broken(lambda hdul: hdul.__setitem__(0, fits.PrimaryHDU(data))) == ["HDU 0 must be an empty primary HDU"]
    assert _broken(lambda hdul: hdul.append(fits.ImageHDU(data))) == [
        "expected an empty primary HDU plus COMPRESSED_IMAGE, got 3 HDUs"
    ]
    assert _broken(lambda hdul: setattr(hdul[1], "name", "OTHER")) == [
        "HDU 1 must be named COMPRESSED_IMAGE, got OTHER"
    ]

    def uncompressed(hdul):
        hdul[1] = fits.ImageHDU(data, header=hdul[1].header, name="COMPRESSED_IMAGE")

    assert _broken(uncompressed) == ["HDU 1 (COMPRESSED_IMAGE) must be a compressed-image, got ImageHDU"]

    def gzip(hdul):
        hdul[1] = fits.CompImageHDU(data, header=hdul[1].header, name="COMPRESSED_IMAGE", compression_type="GZIP_1")

    assert _broken(gzip) == ["HDU 1 (COMPRESSED_IMAGE) must use RICE_1, got GZIP_1"]
    assert _broken(lambda hdul: hdul[1].header.remove("FSN")) == ["missing keyword FSN"]
    assert _broken(lambda hdul: hdul.pop()) == ["expected an empty primary HDU plus COMPRESSED_IMAGE, got 1 HDUs"]


def test_hdu_names_ignore_case_and_take_the_camera():
    level2 = replace(load_spec("level2", "SG"), provisional=False)
    assert validate_file(example_file(level2), level2) == []  # astropy upper-cases "Fe XIX 108.355"
    level1 = replace(load_spec("level1", "SG"), provisional=False)
    hdul = example_file(level1, values={"CAMERA": "SG108"})
    assert hdul[1].name == "SG108"
    assert validate_file(hdul, level1) == []
    hdul[1].header["CAMERA"] = "SG171"
    assert "HDU 1 must be named SG171, got SG108" in validate_file(hdul, level1)


def test_checksums_are_checked_from_a_path(tmp_path):
    spec = load_spec("level0")
    path = tmp_path / "unsummed.fits"
    example_file(spec).writeto(path)
    assert validate_file(path, spec) == []
    assert validate_file(path, spec, checksums=True)[:2] == ["HDU 0 is missing CHECKSUM", "HDU 0 is missing DATASUM"]
    with pytest.raises(ValueError, match="from a path"), fits.open(path) as hdul:
        validate_file(hdul, spec, checksums=True)


def test_provisional_levels_cannot_be_generated_or_checked():
    assert not load_spec("level0").provisional
    spec = load_spec("level2", "SG")
    assert spec.provisional
    with pytest.raises(ValueError, match="provisional"):
        example_file(spec)
    with pytest.raises(ValueError, match="provisional"):
        validate_file(fits.HDUList([fits.PrimaryHDU()]), spec)
