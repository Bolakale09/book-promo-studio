"""The Android app signs in with a token instead of typing the password into the web form."""
from streamlit.testing.v1 import AppTest

from ui import common


def _gate():
    import streamlit as st

    from ui import common
    st.write("in" if common.app_signed_in("test-pass") else "out")


def _run(token=None):
    at = AppTest.from_function(_gate, default_timeout=60)
    if token is not None:
        at.query_params["bps_token"] = token
    at.run()
    return at


def test_token_matches_the_android_hmac():
    # Same value as Prefs.tokenFor("secret") in the Android app.
    assert common.app_token("secret") == "d70174038bd87ec6e2dc494e5925811e5add017ce76b6978957ee803777d84eb"


def test_valid_token_signs_in_and_is_removed_from_the_address():
    at = _run(common.app_token("test-pass"))
    assert at.markdown[0].value == "in"
    assert "bps_token" not in at.query_params


def test_wrong_or_missing_token_does_not_sign_in():
    assert _run(common.app_token("other-pass")).markdown[0].value == "out"
    assert _run().markdown[0].value == "out"
