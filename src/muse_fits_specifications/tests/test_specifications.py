"""
Checks for sheet loading, sheet self-validation, header validation, and rendering.
"""

from __future__ import annotations

import io

import pytest

from muse_fits_specifications import (
    SHEET_PATH,
    HeaderValidationError,
    KeywordSpec,
    Spec,
    SpecDefinitionError,
    ensure_valid,
    example_header,
    load_spec,
    validate,
)
from muse_fits_specifications.render import main, render_sheet, render_spec
from muse_fits_specifications.spec import _LIBRARY_OWNED, _collect, _parse_meta, defined_levels, load_sheet
from muse_fits_specifications.spec import main as check_sheet
from muse_fits_specifications.spec import parse_sheet

SHEET_HEADER = "ISP,L0,L1,L2,L3,FITS  KW,Type,Lower Limit,Upper Limit,FITS Comment,Comment"


def _rows(*lines: str):
    return parse_sheet([SHEET_HEADER, *lines])


def _spec(**keywords: KeywordSpec) -> Spec:
    return Spec(
        name="test-spec",
        version="1",
        title="test",
        source_document="test",
        hdus=(),
        keywords=keywords,
    )


def test_levels_load_from_the_sheet():
    assert defined_levels() == ("level0", "level1")
    level0, level1 = load_spec("level0"), load_spec("level1")
    assert level0.name == "muse-level0"
    assert level0.version == level1.version != ""  # every sheet export bumps both
    assert f"version {level0.version}." in render_spec(level0)
    assert list(level0.keywords)[:3] == ["XTENSION", "BITPIX", "NAXIS"]  # sheet order


def test_sheet_path_is_the_packaged_csv():
    assert SHEET_PATH.name == "keywords.csv"
    assert SHEET_PATH.read_text(encoding="utf-8-sig").startswith("ISP,L0,L1,L2,L3,")


def test_levels_without_rows_or_meta_are_rejected():
    with pytest.raises(SpecDefinitionError, match="level2"):
        load_spec("level2")
    with pytest.raises(ValueError, match="unknown level"):
        load_spec("level7")


def test_sheet_rows_are_typed():
    fsn = load_spec("level0").keywords["MSQ_FSN"]
    assert (fsn.type, fsn.minimum, fsn.maximum, fsn.comment) == ("int", 0, 4294967295, "FSN")
    assert not fsn.library_owned
    offset = load_spec("level0").keywords["MGTPOFFX"]
    assert (offset.minimum, offset.maximum) == (-32768, 32767)
    assert load_spec("level0").keywords["FILENAME"].type == "str"
    cdelt = load_spec("level1").keywords["CDELT1"]
    assert (cdelt.type, cdelt.minimum, cdelt.maximum) == ("float", None, None)
    assert "CDELT1" not in load_spec("level0").keywords


def test_library_owned_cards_are_flagged():
    level0 = load_spec("level0").keywords
    for name in ("XTENSION", "ZCMPTYPE", "TTYPE1", "EXTNAME", "CHECKSUM", "DATASUM", "BZERO"):
        assert level0[name].library_owned, name
    assert not level0["MSQ_FSN"].library_owned
    assert not load_spec("level1").keywords["WCSAXES"].library_owned


def test_sheet_parsing_rules():
    ((levels, kw),) = _rows(",X,x,,,MSQ_FSN ,Integer,0,10,FSN,note")
    assert levels == {"level0", "level1"}
    assert kw == KeywordSpec("MSQ_FSN", "int", 0, 10, "FSN", "note")
    (_, tbd), (_, blank) = _rows(",X,,,,TBD,Integer,,,MNEMONIC,", ",X,,,,,Float,-1.5,,,")
    assert tbd.name == blank.name == ""
    assert (tbd.comment, blank.minimum) == ("MNEMONIC", -1.5)
    assert _rows(",,,,,,,,,,") == []  # blank separator rows are skipped
    assert _rows("", "   ") == []
    assert _rows(",X,,,,KW,,,,,")[0][1].type is None
    assert _rows(',X,,,,KW,String,,,"comment, with comma",note')[0][1].comment == "comment, with comma"


@pytest.mark.parametrize(
    "line",
    [
        ",X,,,,msq_fsn,Integer,,,,",  # lowercase
        ",X,,,,TOOLONGKW,Integer,,,,",  # nine characters
        ",X,,,,KW,Complex,,,,",  # unknown type
        ",X,,,,KW,String,0,,,",  # limit on a string
        ",X,,,,KW,Integer,zero,,,",  # non-numeric limit
        ",X,,,,KW,Integer,5,1,,",  # lower above upper
        ",X,,,,KW",  # truncated row
        ",X,,,,KW,Integer,,,,,extra",  # extra cell
        ",Y,,,,KW,Integer,,,,",  # invalid level marker
        "Y,X,,,,KW,Integer,,,,",  # invalid ISP marker
        ",X,,,,KW,Float,nan,,,",  # non-finite limit
        ",X,,,,KW,Float,,inf,,",  # non-finite limit
        ",,,,,KW,Integer,,,,",  # not marked for any level
        ',X,,,,KW,String,,,"unfinished,note',  # malformed CSV quoting
    ],
)
def test_bad_sheet_rows_are_rejected(line):
    with pytest.raises(SpecDefinitionError, match="row 2"):
        _rows(line)


def test_missing_sheet_columns_are_rejected():
    with pytest.raises(SpecDefinitionError, match="Type"):
        parse_sheet(["L0,FITS KW", "X,KW"])


@pytest.mark.parametrize(
    ("header", "message"),
    [
        (SHEET_HEADER.replace("L0,", ""), "missing columns.*L0"),
        (SHEET_HEADER + ",Extra", "unexpected columns"),
        (SHEET_HEADER + ",", "unexpected columns"),
        (SHEET_HEADER + ",Type", "duplicate columns"),
        (SHEET_HEADER + ",FITS KW", "duplicate columns"),
    ],
)
def test_invalid_sheet_columns_are_rejected(header, message):
    with pytest.raises(SpecDefinitionError, match=message):
        parse_sheet([header])


GOOD_META = (
    'spec = "s"\nspec_version = "0.1"\ntitle = "t"\nsource_document = "d"\n[[hdus]]\nname = "A"\nkind = "image"\n'
)


def test_good_meta_parses():
    assert _parse_meta(GOOD_META, "meta")["hdus"] == [{"name": "A", "kind": "image"}]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("spec_version = \n", "meta: invalid TOML"),
        (GOOD_META.replace('spec_version = "0.1"', "spec_version = 0.1"), "spec_version must be a quoted string"),
        (GOOD_META.replace('title = "t"\n', ""), "title must be"),
        (GOOD_META.split("[[hdus]]", maxsplit=1)[0], "hdus"),
        (GOOD_META.replace('kind = "image"\n', ""), "name and kind"),
        (GOOD_META + "compression = 1\n", "name and kind"),
    ],
)
def test_bad_meta_is_rejected(text, message):
    with pytest.raises(SpecDefinitionError, match=message):
        _parse_meta(text, "meta")


def test_duplicate_keyword_in_a_level_is_rejected():
    rows = _rows(",X,,,,KW,Integer,,,,", ",X,X,,,KW,Integer,,,,")
    with pytest.raises(SpecDefinitionError, match="twice"):
        _collect(rows, "level0")
    assert list(_collect(rows, "level1")[0]) == ["KW"]
    with pytest.raises(SpecDefinitionError, match="no keywords"):
        _collect(rows, "level2")


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
    for level in ("level0", "level1"):
        spec = load_spec(level)
        header = example_header(spec)
        assert validate(header, spec) == []
        assert not any(spec.keywords[name].library_owned for name in header)
    assert example_header(load_spec("level0"))["MGTPOFFX"] == -32768


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


def test_render_lists_keywords_and_unassigned_fields_and_escapes_markup():
    page = render_spec(load_spec("level0"))
    assert "   * - MSQ\\_FSN\n     - int\n     - 0\n     - 4294967295\n     - FSN" in page
    assert "Unassigned ISP fields (" in page
    assert "   * - CCSDS\\_SECONDS\n     - int\n     - 0\n     - 4294967295" in page
    assert "Unassigned" not in render_spec(load_spec("level1"))
    spec = _spec(P=KeywordSpec("P", comment="a|b*c"))
    assert "a\\|b\\*c" in render_spec(spec)


def test_render_sheet_mirrors_the_sheet_with_a_column_per_level():
    page = render_sheet(load_sheet())
    assert "   * - L0\n     - L1\n     - L2\n     - L3\n     - Keyword" in page
    assert "   * - X\n     -\n     -\n     -\n     - MSQ\\_FSN\n     - int" in page  # level 0 only
    assert "   * -\n     - X\n     -\n     -\n     - WCSAXES" in page
    # an unassigned row keeps its place, with a blank keyword cell
    assert "     -\n     - int\n     - 0\n     - 4294967295\n     - CCSDS\\_SECONDS" in page


def test_main_writes_the_sheet_page_and_one_page_per_defined_level(tmp_path):
    (tmp_path / "level3.rst").write_text("stale page from a level that is no longer defined")
    assert main([str(tmp_path)]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == ["keywords.csv", "keywords.rst", "level0.rst", "level1.rst"]


def test_check_sheet_passes_and_rejects_a_marked_but_undefined_level(monkeypatch):
    assert check_sheet() == 0
    rows = load_sheet()
    monkeypatch.setattr(
        "muse_fits_specifications.spec.load_sheet", lambda: (*rows, (frozenset({"level3"}), KeywordSpec("KW")))
    )
    with pytest.raises(SpecDefinitionError, match="level3"):
        check_sheet()
