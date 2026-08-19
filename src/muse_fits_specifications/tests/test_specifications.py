"""
Checks for spec loading, spec self-validation, and header validation.
"""

from __future__ import annotations

import pytest

from muse_fits_specifications import (
    HeaderValidationError,
    KeywordSpec,
    Spec,
    SpecDefinitionError,
    ensure_valid,
    example_header,
    example_value,
    load_spec,
    validate,
)
from muse_fits_specifications.render import render_spec
from muse_fits_specifications.spec import _keyword


def _spec(**keywords: KeywordSpec) -> Spec:
    return Spec(
        name="test-spec",
        version=1,
        title="test",
        source_document="test",
        hdus=(),
        keywords=keywords,
    )


def test_both_levels_load_and_are_substantial():
    for level, minimum in (("level0", 250), ("level1", 200)):
        spec = load_spec(level)
        assert spec.name == f"muse-{level}"
        assert len(spec.keywords) > minimum
        assert any(kw.required for kw in spec.keywords.values())


def test_mission_identity_keywords():
    for level in ("level0", "level1"):
        camera = load_spec(level).keywords["CAMERA"]
        assert camera.required
        assert camera.values == ("CI", "CI171", "CI304", "SG108", "SG171", "SG284")
        date_obs = load_spec(level).keywords["DATE-OBS"]
        assert date_obs.format == "isot"
    assert load_spec("level0").keywords["QUALLEV0"].required
    assert load_spec("level1").keywords["QUALLEV1"].required


def test_structural_cards_are_not_required():
    for name in ("XTENSION", "ZCMPTYPE", "BZERO"):
        assert not load_spec("level0").keywords[name].required, name


def test_checksum_cards_are_required():
    for level in ("level0", "level1"):
        for name in ("CHECKSUM", "DATASUM"):
            assert load_spec(level).keywords[name].required, f"{level} {name}"


def test_example_header_conforms_to_its_own_spec():
    for level in ("level0", "level1"):
        spec = load_spec(level)
        header = example_header(spec)
        # Only the fits section (checksums) is absent: the library computes it.
        errors = validate(header, spec)
        assert all("CHECKSUM" in e or "DATASUM" in e for e in errors), errors
        assert header["CAMERA"] in spec.keywords["CAMERA"].values


def test_example_values_parse_typed():
    spec = load_spec("level0")
    assert example_value(spec.keywords["FSN"]) == 136374300
    assert example_value(spec.keywords["CAMERA"]) == "SG108"
    assert abs(example_value(spec.keywords["EXPTIME"]) - 0.298752815) < 1e-12
    assert example_value(KeywordSpec("X", required=True)) is None


def test_unknown_level_is_rejected():
    with pytest.raises(ValueError, match="unknown level"):
        load_spec("level3")


def test_bad_keyword_definitions_are_rejected():
    with pytest.raises(SpecDefinitionError):
        _keyword("BAD", {"required": True, "type": "int", "typo": 1}, "test", "s")
    with pytest.raises(SpecDefinitionError):
        _keyword("BAD", {"type": "int"}, "test", "s")
    with pytest.raises(SpecDefinitionError):
        _keyword("BAD", {"required": True, "type": "complex"}, "test", "s")


def test_keywords_carry_their_section():
    spec = load_spec("level1")
    assert spec.keywords["CAMERA"].section == "exposure"
    assert spec.keywords["CRVAL1"].section == "wcs"
    assert "isp-thermal" in spec.sections
    assert "wcs" not in load_spec("level0").sections


def test_missing_required_and_optional():
    spec = _spec(
        NEEDED=KeywordSpec("NEEDED", required=True),
        MAYBE=KeywordSpec("MAYBE", required=False),
    )
    assert validate({}, spec) == ["missing required keyword NEEDED"]
    assert validate({"NEEDED": 1}, spec) == []


def test_type_checks():
    spec = _spec(
        N=KeywordSpec("N", required=True, type="int"),
        X=KeywordSpec("X", required=True, type="float"),
        S=KeywordSpec("S", required=True, type="str"),
        B=KeywordSpec("B", required=True, type="bool"),
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


def test_values_and_format_checks():
    spec = _spec(
        CAMERA=KeywordSpec("CAMERA", required=True, type="str", values=("CI", "SG108")),
        T=KeywordSpec("T", required=True, type="str", format="isot"),
    )
    good = {"CAMERA": "SG108", "T": "2024-11-08T00:59:04.234"}
    assert validate(good, spec) == []
    assert "must be one of" in validate(good | {"CAMERA": "VBI"}, spec)[0]
    assert "ISO 8601" in validate(good | {"T": "yesterday"}, spec)[0]


def test_untyped_keyword_only_checks_presence():
    spec = _spec(FREE=KeywordSpec("FREE", required=True))
    assert validate({"FREE": object()}, spec) == []


def test_ensure_valid_raises_with_error_list():
    spec = _spec(NEEDED=KeywordSpec("NEEDED", required=True))
    ensure_valid({"NEEDED": 1}, spec)
    with pytest.raises(HeaderValidationError) as caught:
        ensure_valid({}, spec)
    assert caught.value.errors == ["missing required keyword NEEDED"]


def test_empty_header_reports_every_required_keyword():
    spec = load_spec("level0")
    required = sum(1 for kw in spec.keywords.values() if kw.required)
    assert len(validate({}, spec)) == required


def test_render_contains_keywords_and_escapes_markup():
    page = render_spec(load_spec("level1"))
    assert "   * - CAMERA\n     - yes" in page
    assert "one of CI, CI171, CI304, SG108, SG171, SG284" in page
    spec = _spec(P=KeywordSpec("P", required=True, comment="a|b*c"))
    assert "a\\|b\\*c" in render_spec(spec)
