"""
Checks for sheet conversion, loading, header validation, and rendering.
"""

from __future__ import annotations

import csv
import io
import shutil
from dataclasses import replace

import pytest

from muse_fits_specifications import (
    FAMILIES,
    KEYWORDS_PATH,
    SHEET_PATH,
    HeaderValidationError,
    KeywordSpec,
    Spec,
    SpecDefinitionError,
    ensure_valid,
    example_header,
    families,
    load_spec,
    validate,
)
from muse_fits_specifications.render import level_pages, main, render_sheet, render_spec
from muse_fits_specifications.sheet import _LIBRARY_OWNED, check, convert, dump, section_file, write
from muse_fits_specifications.spec import _collect, _meta, _parse_meta, defined_levels

SHEET_HEADER = "FITS KW,Type,ISP,L0,L1,L2,L3,Lower Limit,Upper Limit,FITS Comment,Comment,ISP mnemonic"


def _line(name="KW", kind="", lower="", upper="", *, levels=("X", "", "", ""), comment="", notes="", mnemonic=""):
    out = io.StringIO()
    csv.writer(out).writerow([name, kind, "", *levels, lower, upper, comment, notes, mnemonic])
    return out.getvalue().rstrip("\r\n")


def _keywords(*lines: str) -> list[dict]:
    return [kw for section in convert([SHEET_HEADER, *lines]) for kw in section["keywords"]]


def _spec(**keywords: KeywordSpec) -> Spec:
    return Spec(
        name="test-spec",
        version="1",
        title="test",
        source_document="test",
        hdus=(),
        keywords=keywords,
    )


def test_every_level_loads_from_the_yaml():
    assert defined_levels() == ("level0", "level1", "level2", "level3")
    pages = level_pages()
    assert [docname for docname, _ in pages] == [
        "level0",
        "level1-ci",
        "level1-sg",
        "level2-ci",
        "level2-sg",
        "level3",
    ]
    assert len({spec.version for _, spec in pages}) == 1  # every sheet export bumps every level
    level0 = load_spec("level0")
    assert level0.name == "muse-level0"
    assert list(level0.keywords)[:3] == ["XTENSION", "BITPIX", "NAXIS"]  # sheet order
    assert level0.sections[:2] == ("", "Basic file and observation metadata")


def test_packaged_yaml_matches_the_packaged_sheet():
    assert SHEET_PATH.read_text(encoding="utf-8-sig").startswith("FITS KW,Type,")
    assert (KEYWORDS_PATH / "_sections.yml").read_text(encoding="utf-8").startswith("# Generated from keywords.csv")
    assert check() == 0


def test_yaml_is_one_file_per_section_in_sheet_order(tmp_path):
    sections = convert(
        [
            SHEET_HEADER,
            _line("XTENSION", "str"),
            "###,Exposure and timing,,,,,,,,,,",
            _line("EXPTIME", "float"),
            "###,World Coordinate System (WCS),,,,,,,,,,",
            _line("CTYPE1", "str"),
            "###,Empty,,,,,,,,,,",
        ]
    )
    files = dump(sections)
    assert files["_sections.yml"].splitlines()[1:] == [
        "- untitled.yml",
        "- exposure-and-timing.yml",
        "- world-coordinate-system-wcs.yml",
    ]
    assert files["exposure-and-timing.yml"].splitlines()[1:3] == ["section: Exposure and timing", "keywords:"]
    (tmp_path / "removed-section.yml").write_text("stale")
    (tmp_path / "notes.txt").write_text("kept")
    write(tmp_path, files)
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted([*files, "notes.txt"])
    assert section_file("") == "untitled.yml"


def test_sections_whose_titles_give_one_file_name_are_rejected():
    with pytest.raises(SpecDefinitionError, match="row 5: section 'Exposure and Timing' has the same file name"):
        convert(
            [
                SHEET_HEADER,
                "###,Exposure and timing,,,,,,,,,,",
                _line("A"),
                "###,Other,,,,,,,,,,",  # empty, so dropped
                "###,Exposure and Timing,,,,,,,,,,",
                _line("B"),
            ]
        )
    with pytest.raises(SpecDefinitionError, match="the rows above the first section row"):
        convert([SHEET_HEADER, _line("A"), "###,Untitled,,,,,,,,,,", _line("B")])


def test_levels_whose_ci_and_sg_files_differ_load_per_camera_type():
    assert families("level0") == families("level3") == (None,)
    assert families("level1") == families("level2") == FAMILIES
    with pytest.raises(ValueError, match="family='CI'"):
        load_spec("level1")
    with pytest.raises(ValueError, match="unknown camera family"):
        load_spec("level1", "XX")
    assert load_spec("level0", "SG").family is None
    assert dict(load_spec("level0", "SG").keywords) == dict(load_spec("level0").keywords)
    ci, sg = load_spec("level1", "CI").keywords, load_spec("level1", "SG").keywords
    assert ci["PC1_1"].comment != sg["PC1_1"].comment  # one keyword, a row per camera type
    assert "PC1_2" in ci
    assert "PC1_2" not in sg
    assert [hdu.name for hdu in load_spec("level2", "SG").hdus] == ["SCI", "DQ", "AUX", "WAVELENGTH"]
    assert [hdu.name for hdu in load_spec("level2", "CI").hdus] == ["SCI", "DQ", "AUX"]


def test_unknown_or_undefined_levels_are_rejected(monkeypatch):
    with pytest.raises(ValueError, match="unknown level"):
        load_spec("level7")
    monkeypatch.setattr("muse_fits_specifications.spec.defined_levels", lambda: ("level0",))
    with pytest.raises(SpecDefinitionError, match="does not exist; add it to define level3"):
        _meta.__wrapped__("level3")


def test_sheet_rows_are_typed():
    level0 = load_spec("level0").keywords
    fsn = level0["FSN"]
    assert (fsn.type, fsn.minimum, fsn.maximum, fsn.values) == ("int", 0, 4294967295, None)
    assert (fsn.section, fsn.library_owned) == ("ISP mnemonic", False)
    assert level0["NAXIS1"].maximum == 4294967295  # the sheet gives only the minimum; uint32 fills the rest
    assert level0["BITPIX"].values == (8, 16, 32, 64, -32, -64)
    assert (level0["DATE-OBS"].type, level0["DATE-OBS"].format) == ("str", "isot")
    assert load_spec("level1", "SG").keywords["CAMERA"].values == ("CI", "SG108", "SG171", "SG284")


def test_library_owned_cards_are_flagged():
    level0 = load_spec("level0").keywords
    for name in ("XTENSION", "ZCMPTYPE", "TTYPE1", "EXTNAME", "CHECKSUM", "DATASUM", "BZERO"):
        assert level0[name].library_owned, name
    assert not level0["FSN"].library_owned
    assert not load_spec("level1", "SG").keywords["WCSAXES"].library_owned


def test_sheet_conversion():
    sections = convert(
        [
            SHEET_HEADER,
            _line("XTENSION", "str", "BINTABLE;", comment="ext"),
            "###,,,,,,,,,,,",
            "###,Timing,,,,,,,,,,",
            _line("FSN ", "uint32", levels=("X", "x", "", ""), comment="frame, number", notes="note", mnemonic="M1"),
            _line("PC1_1", "float64", levels=("", "SG", "CI", "")),
            _line("PC1_1", "float64", levels=("", "CI", "", "")),
            _line("TBD", "uint8", mnemonic="M2"),
            _line("PARKED", "ISO 8601", levels=("", "", "", "")),
            ",,,,,,,,,,,",  # blank separator rows are skipped
            "",
        ]
    )
    assert [section["section"] for section in sections] == ["", "Timing"]
    xtension, fsn, sg, ci, tbd, parked = (kw for section in sections for kw in section["keywords"])
    assert xtension == {
        "name": "XTENSION",
        "levels": {"level0": "all"},
        "type": "str",
        "values": ["BINTABLE"],
        "comment": "ext",
        "library_owned": True,
    }
    assert fsn == {
        "name": "FSN",
        "levels": {"level0": "all", "level1": "all"},
        "type": "int",
        "minimum": 0,
        "maximum": 4294967295,
        "mnemonic": "M1",
        "comment": "frame, number",
        "notes": "note",
    }
    assert (sg["levels"], ci["levels"]) == ({"level1": "SG", "level2": "CI"}, {"level1": "CI"})
    assert (tbd["name"], tbd["maximum"], tbd["mnemonic"]) == ("", 255, "M2")
    assert parked == {"name": "PARKED", "levels": {}, "type": "str", "format": "isot"}


@pytest.mark.parametrize(
    ("kind", "lower", "values"),
    [
        ("str", 'SG; "Corrected DN";', ["SG", "Corrected DN"]),
        ("int16", "8;16;-32", [8, 16, -32]),
        ("float", "0.5;1", [0.5, 1.0]),
        ("bool", "T", [True]),
    ],
)
def test_lower_limit_can_list_allowed_values(kind, lower, values):
    (kw,) = _keywords(_line("KW", kind, lower))
    assert kw["values"] == values
    assert "minimum" not in kw
    assert "maximum" not in kw


@pytest.mark.parametrize(
    "line",
    [
        _line("kw", "str"),  # lowercase
        _line("TOOLONGKW", "str"),  # nine characters
        _line("KW", "ISO"),  # unknown type
        _line("KW", "", "0"),  # limit without a type
        _line("KW", "int", "zero"),  # non-numeric limit
        _line("KW", "int", "1.5"),  # fractional limit on an integer
        _line("KW", "int", "5", "1"),  # lower above upper
        _line("KW", "uint8", "0", "256"),  # beyond the type's range
        _line("KW", "int16", "8;65536"),  # an allowed value beyond the type's range
        _line("KW", "str", "A", "B"),  # upper limit on a string
        _line("KW", "int", "1;2", "3"),  # upper limit with allowed values
        _line("KW", "bool", "yes"),  # bool values are T or F
        _line("KW", "str", ";"),  # an empty list of values
        _line("KW", "str", '""'),  # a quoted empty value
        _line("KW", "int", "1_000"),  # Python reads it as 1000; a sheet number never has an underscore
        _line("KW", "float", "nan"),  # non-finite limits
        _line("KW", "float", "", "inf"),
        _line("KW", "str", levels=("Y", "", "", "")),  # unknown level marker
        "KW,str",  # truncated row
        _line("KW", "str") + ",extra",  # extra cell
        'KW,str,,X,,,,,,"unfinished,note',  # malformed CSV quoting
    ],
)
def test_bad_sheet_rows_are_rejected(line):
    with pytest.raises(SpecDefinitionError, match="row 2"):
        _keywords(line)


def test_a_keyword_is_listed_once_per_level_and_camera_type():
    with pytest.raises(SpecDefinitionError, match="row 3: KW is already listed for level1 on row 2"):
        _keywords(_line(levels=("", "X", "", "")), _line(levels=("", "SG", "", "")))
    assert len(_keywords(_line(levels=("", "CI", "", "")), _line(levels=("", "SG", "", "")))) == 2
    assert len(_keywords(_line(levels=("", "", "", "")), _line(levels=("", "", "", "")))) == 2  # parked rows
    assert len(_keywords(_line("TBD"), _line(""))) == 2  # unassigned fields


def test_missing_sheet_columns_are_rejected():
    with pytest.raises(SpecDefinitionError, match="Type"):
        convert(["L0,FITS KW", "X,KW"])


@pytest.mark.parametrize(
    ("header", "message"),
    [
        (SHEET_HEADER.replace("L0,", ""), "missing columns.*L0"),
        (SHEET_HEADER + ",Extra", "unexpected columns"),
        (SHEET_HEADER + ",", "unexpected columns"),
        (SHEET_HEADER + ",Type", "duplicate columns"),
        (SHEET_HEADER + ",FITS  KW", "duplicate columns"),  # whitespace in headers is collapsed
    ],
)
def test_invalid_sheet_columns_are_rejected(header, message):
    with pytest.raises(SpecDefinitionError, match=message):
        convert([header])


GOOD_META = (
    'spec = "s"\nspec_version = "0.1"\ntitle = "t"\nsource_document = "d"\n[[hdus]]\nname = "A"\nkind = "image"\n'
)


def test_good_meta_parses():
    assert _parse_meta(GOOD_META, "meta")["hdus"] == [{"name": "A", "kind": "image"}]
    assert _parse_meta("per_camera = true\n" + GOOD_META + 'family = "SG"\n', "meta")["hdus"][0]["family"] == "SG"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("spec_version = \n", "meta: invalid TOML"),
        (GOOD_META.replace('spec_version = "0.1"', "spec_version = 0.1"), "spec_version must be a quoted string"),
        (GOOD_META.replace('title = "t"\n', ""), "title must be"),
        (GOOD_META.split("[[hdus]]", maxsplit=1)[0], "hdus"),
        (GOOD_META.replace('kind = "image"\n', ""), "name and kind"),
        (GOOD_META + "compression = 1\n", "name and kind"),
        (GOOD_META + 'family = "XX"\n', "name and kind"),
        (GOOD_META + 'family = "SG"\n', "needs per_camera = true"),
        ('per_camera = "yes"\n' + GOOD_META, "per_camera must be true or false"),
    ],
)
def test_bad_meta_is_rejected(text, message):
    with pytest.raises(SpecDefinitionError, match=message):
        _parse_meta(text, "meta")


def test_collect_picks_one_level_and_camera_type():
    rows = [
        ({"level0": "all"}, KeywordSpec("KW")),
        ({"level0": "all", "level1": "SG"}, KeywordSpec("KW", comment="sg")),
        ({"level1": "CI"}, KeywordSpec("KW", comment="ci")),
    ]
    with pytest.raises(SpecDefinitionError, match="twice"):
        _collect(rows, "level0")
    assert _collect(rows, "level1", "SG")[0]["KW"].comment == "sg"
    assert _collect(rows, "level1", "CI")[0]["KW"].comment == "ci"
    with pytest.raises(SpecDefinitionError, match="no keywords"):
        _collect(rows, "level2")
    # A level loaded without a camera type is not split, so a CI- or SG-only row there is an error.
    with pytest.raises(SpecDefinitionError, match="KW is SG-only in level1, but"):
        _collect(rows, "level1")


def test_missing_keywords():
    spec = _spec(NEEDED=KeywordSpec("NEEDED"), OTHER=KeywordSpec("OTHER"))
    assert validate({}, spec) == ["missing keyword NEEDED", "missing keyword OTHER"]
    assert validate({"NEEDED": 1, "OTHER": "x"}, spec) == []


def test_type_checks():
    spec = _spec(
        N=KeywordSpec("N", type="int"),
        X=KeywordSpec("X", type="float"),
        S=KeywordSpec("S", type="str"),
        B=KeywordSpec("B", type="bool"),
    )
    good = {"N": 3, "X": 1.5, "S": "ok", "B": True}
    assert validate(good, spec) == []
    # ints are acceptable where floats are specified, not vice versa
    assert validate(good | {"X": 2}, spec) == []
    assert len(validate(good | {"N": 2.5}, spec)) == 1
    assert len(validate(good | {"N": True}, spec)) == 1
    assert len(validate(good | {"X": float("nan")}, spec)) == 1
    assert len(validate(good | {"S": 7}, spec)) == 1
    assert len(validate(good | {"B": 1}, spec)) == 1


def test_range_checks_are_inclusive():
    spec = _spec(N=KeywordSpec("N", "int", 0, 10), X=KeywordSpec("X", "float", -1.5, None))
    assert validate({"N": 0, "X": -1.5}, spec) == []
    assert validate({"N": 10, "X": 1e9}, spec) == []
    assert "N must be >= 0" in validate({"N": -1, "X": 0}, spec)[0]
    assert "N must be <= 10" in validate({"N": 11, "X": 0}, spec)[0]
    assert "X must be >= -1.5" in validate({"N": 0, "X": -2}, spec)[0]
    assert "must be an integer" in validate({"N": "9", "X": 0}, spec)[0]


def test_allowed_values():
    spec = _spec(S=KeywordSpec("S", "str", values=("CI", "SG")), N=KeywordSpec("N", "int", values=(1, 2)))
    assert validate({"S": "SG", "N": 2}, spec) == []
    assert validate({"S": "XX", "N": 2}, spec) == ["S must be one of ['CI', 'SG'], got 'XX'"]
    assert "N must be an integer" in validate({"S": "CI", "N": True}, spec)[0]  # True == 1 in Python


def test_untyped_keyword_only_checks_presence():
    spec = _spec(FREE=KeywordSpec("FREE"))
    assert validate({"FREE": object()}, spec) == []


def test_library_owned_cards_are_not_validated():
    spec = _spec(ZIMAGE=KeywordSpec("ZIMAGE", type="bool", library_owned=True), N=KeywordSpec("N", type="int"))
    assert validate({"N": 1}, spec) == []
    assert validate({"N": 1, "ZIMAGE": "not a bool"}, spec) == []


def test_ensure_valid_raises_with_error_list():
    spec = _spec(NEEDED=KeywordSpec("NEEDED"))
    ensure_valid({"NEEDED": 1}, spec)
    with pytest.raises(HeaderValidationError) as caught:
        ensure_valid({}, spec)
    assert caught.value.errors == ["missing keyword NEEDED"]


def test_example_header_conforms_to_its_own_spec():
    for _, spec in level_pages():
        header = example_header(spec)
        assert validate(header, spec) == []
        assert not any(spec.keywords[name].library_owned for name in header)
    assert example_header(load_spec("level1", "SG"))["CAMERA"] == "CI"  # the first allowed value


def test_library_owned_matches_astropy():
    """
    The permanent form of the check that astropy hides only cards we skip.
    """
    fits = pytest.importorskip("astropy.io.fits")
    np = pytest.importorskip("numpy")
    spec = load_spec("level0")
    hdu = fits.CompImageHDU(np.zeros((3, 4), dtype=np.int16), compression_type="RICE_1", name="COMPRESSED_IMAGE")
    hdu.header.update(example_header(spec))
    buf = io.BytesIO()
    fits.HDUList([fits.PrimaryHDU(), hdu]).writeto(buf, checksum=True)
    with fits.open(io.BytesIO(buf.getvalue())) as hdul:
        image_header = hdul[1].header.copy()
    assert validate(image_header, spec) == []
    with fits.open(io.BytesIO(buf.getvalue()), disable_image_compression=True) as hdul:
        hidden = [key for key in hdul[1].header if key and key not in image_header]
    assert hidden  # astropy really does hide cards from hdul[1].header
    assert all(_LIBRARY_OWNED.fullmatch(key) for key in hidden), hidden


def test_render_spec_groups_keywords_by_section_and_escapes_markup():
    page = render_spec(load_spec("level1", "SG"))
    assert page.startswith("Level 1 (SG)\n============\n")
    assert "Basic file and observation metadata\n^^^^^" in page
    assert "   * - CAMERA\n     - str\n     - CI; SG108; SG171; SG284\n" in page
    assert "     - str (ISO 8601)\n" in page
    assert "Unassigned" not in page
    assert "   * - NAXIS1\n     - int\n     - 1 to 4294967295\n" in render_spec(load_spec("level0"))
    spec = replace(_spec(P=KeywordSpec("P", comment="a|b*c")), unassigned=(KeywordSpec("", "int", mnemonic="M"),))
    page = render_spec(spec)
    assert "a\\|b\\*c" in page
    assert "Unassigned ISP fields (1)" in page


def test_render_sheet_has_a_column_per_level():
    page = render_sheet(
        [({"level0": "all", "level1": "SG"}, KeywordSpec("KW", "int", 0, 9)), ({}, KeywordSpec("PARKED"))]
    )
    assert "   * - L0\n     - L1\n     - L2\n     - L3\n     - Keyword" in page
    assert "   * - X\n     - SG\n     -\n     -\n     - KW\n     - int\n     - 0 to 9\n" in page
    assert "   * -\n     -\n     -\n     -\n     - PARKED\n" in page
    assert ":download:`Download the keyword sheet <keywords.csv>`." in page


def test_main_writes_the_sheet_and_one_page_per_level_and_camera_type(tmp_path):
    (tmp_path / "level9.rst").write_text("stale page from a level that is no longer defined")
    assert main([str(tmp_path)]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "keywords.csv",
        "keywords.rst",
        "level0.rst",
        "level1-ci.rst",
        "level1-sg.rst",
        "level2-ci.rst",
        "level2-sg.rst",
        "level3.rst",
    ]


def test_check_rejects_a_stale_yaml_and_a_marked_but_undefined_level(monkeypatch, tmp_path):
    copy = tmp_path / "keywords"
    shutil.copytree(str(KEYWORDS_PATH), copy)
    monkeypatch.setattr("muse_fits_specifications.sheet.KEYWORDS_PATH", copy)
    untitled = copy / "untitled.yml"
    untitled.write_text(untitled.read_text(encoding="utf-8").replace("XTENSION", "XTENSIO", 1), encoding="utf-8")
    with pytest.raises(SpecDefinitionError, match=r"does not match specs/keywords.csv \(untitled.yml\)"):
        check()
    shutil.copy(str(KEYWORDS_PATH / "untitled.yml"), untitled)
    (copy / "old-section.yml").write_text("stale")
    with pytest.raises(SpecDefinitionError, match=r"\(old-section.yml\)"):
        check()
    monkeypatch.undo()
    monkeypatch.setattr("muse_fits_specifications.sheet.defined_levels", lambda: ("level0", "level1", "level2"))
    with pytest.raises(SpecDefinitionError, match="level3"):
        check()
