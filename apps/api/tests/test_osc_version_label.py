"""OSC 0015: Review shows OUR version number (from the file name / slate), never the upload count."""
from apps.api.schemas.asset import AssetVersionResponse
from apps.api.services.osc_version_label import version_label


def test_house_file_names():
    assert version_label("HarmonSoS_2026-10-05_SP_v10.mp4") == "v10"
    assert version_label("01_INTRODUCTION_2026-10-04_SP_v11_nov3.mov") == "v11"
    assert version_label("HarmonSoS_2026-10-04_SP_v8_ALT-B_Homeward.mp4") == "v8"
    assert version_label("HarmonSoS_2026-10-03_SP_v3_review.mp4") == "v3"
    assert version_label("osc-review-test-v2.mp4") == "v2"


def test_wip_renders_say_so():
    assert version_label("02_FREEDOM_2026-10-04_SP_v9_wip2.mov") == "v9 wip2"


def test_no_vn_falls_back_to_the_upload_count():
    assert version_label("Final Mix.wav") is None
    assert version_label("dev-notes.mov") is None       # 'dev' is not a version
    assert version_label("") is None
    assert version_label(None) is None


def test_the_last_vn_wins_and_leading_zeros_drop():
    assert version_label("show_v1_cut_v04.mov") == "v4"


def test_a_non_string_label_never_breaks_a_response():
    # Mock versions in tests hand pydantic a MagicMock attribute; it must read as None.
    class V:
        id = "00000000-0000-0000-0000-000000000001"
        asset_id = "00000000-0000-0000-0000-000000000002"
        version_number = 3
        processing_status = "ready"
        created_by = "00000000-0000-0000-0000-000000000003"
        created_at = "2026-10-05T00:00:00Z"
        osc_label = object()
    assert AssetVersionResponse.model_validate(V()).osc_label is None
