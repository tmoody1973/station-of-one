import pytest

from station.gateway import GatewayError
from station.radio.extract import Extracted
from station.radio.resolve import MATCH_MIN, AppleRefused, match_score, resolve
from tests.fakes import FakeGateway, ok

CONN = "APPLE"


def song(sid, artist, name, album="Odyssey", date="2024-09-20", ms=300000, isrc="X"):
    return {"id": sid, "type": "songs", "attributes": {
        "artistName": artist, "name": name, "albumName": album, "releaseDate": date, "durationInMillis": ms, "isrc": isrc,
        "previews": [{"url": f"https://audio-ssl.itunes.apple.com/{sid}.m4a"}], "url": f"https://music.apple.com/us/song/{sid}",
        "artwork": {"url": "https://is1-ssl.mzstatic.com/image/thumb/a/{w}x{h}bb.jpg"}}}


def search(songs=(), albums=()):
    return ok({"results": {"songs": {"data": list(songs)}, "albums": {"data": list(albums)}}})


def gw_with(*responses, tracks=None):
    routes = {("GET", CONN, "/v1/catalog/us/search"): list(responses)}
    if tracks is not None:
        routes[("GET", CONN, "/v1/catalog/us/albums/")] = [ok({"data": tracks})]
    return FakeGateway(routes)


def want(artist="Nubya Garcia", title="Solstice", release="", year=None, version="", kind="track"):
    return Extracted(kind, artist, title, release, "", year, version)


def test_original_beats_remaster_and_live():  # Review Focus 2
    gw = gw_with(search([song("1", "Nubya Garcia", "Solstice (Live at the Barbican)"), song("2", "Nubya Garcia", "Solstice (2025 Remaster)"),
                         song("3", "Nubya Garcia", "Solstice")]))
    matches, status = resolve(gw, CONN, want(), "us")
    assert status == "resolved" and matches[0].song_id == "3"
    live, status = resolve(gw_with(search([song("3", "Nubya Garcia", "Solstice"), song("1", "Nubya Garcia", "Solstice (Live at the Barbican)")])),
                           CONN, want(version="Live at the Barbican"), "us")
    assert live[0].song_id == "1"


def test_year_and_album_disambiguate():  # Review Focus 3
    a = {"artistName": "Shabaka", "name": "End of Innocence", "albumName": "Perceive its Beauty", "releaseDate": "2024-04-12"}
    b = {"artistName": "Shabaka", "name": "End of Innocence", "albumName": "Something Else", "releaseDate": "2011-01-01"}
    w = want("Shabaka", "End of Innocence", year=2024)
    assert match_score(w, a) > match_score(w, b)


def test_below_threshold_is_held():
    matches, status = resolve(gw_with(search([song("9", "Another Artist", "Different Song")])), CONN, want(), "us")
    assert status == "held" and matches == []
    assert match_score(want(), {"artistName": "Nubya Garcia", "name": "Solstice"}) >= MATCH_MIN


def test_no_results_is_not_on_apple():
    assert resolve(gw_with(search()), CONN, want(), "us") == ([], "not_on_apple")


def test_release_picks_named_track_first():  # Review Focus 1
    album = {"id": "77", "type": "albums", "attributes": {"artistName": "Nubya Garcia", "name": "Odyssey", "releaseDate": "2024-09-20"}}
    tracks = [song("t1", "Nubya Garcia", "Dawn (feat. Esperanza Spalding)"), song("t2", "Nubya Garcia", "Odyssey"),
              song("t3", "Nubya Garcia", "Solstice")]
    matches, status = resolve(gw_with(search(albums=[album]), tracks=tracks), CONN,
                              want(title="", release="Odyssey", kind="release"), "us", excerpt="Standouts include Solstice.")
    assert status == "resolved" and [m.song_id for m in matches] == ["t3"]
    matches, _ = resolve(gw_with(search(albums=[album]), tracks=tracks), CONN, want(title="", release="Odyssey", kind="release"), "us")
    assert [m.song_id for m in matches] == ["t2"]   # no track named: the title track


def test_match_carries_preview_link_and_artwork():
    matches, _ = resolve(gw_with(search([song("3", "Nubya Garcia", "Solstice")])), CONN, want(), "us")
    m = matches[0]
    assert m.preview_url.endswith("3.m4a") and m.apple_url.startswith("https://music.apple.com/") and "300x300" in m.artwork_url


def test_apple_401_raises_a_clear_error():  # Review Focus 4
    gw = FakeGateway({("GET", CONN, "/v1/catalog/us/search"): [ok({}, status=401)]})
    with pytest.raises(AppleRefused, match="apple_check"):
        resolve(gw, CONN, want(), "us")


def test_deluxe_edition_is_not_an_edit():  # review I4
    w = want(title="", release="Odyssey", kind="release")
    probe = Extracted("track", "Nubya Garcia", "Odyssey", "Odyssey", "", None, "")
    assert match_score(probe, {"artistName": "Nubya Garcia", "name": "Odyssey (Deluxe Edition)", "albumName": "Odyssey (Deluxe Edition)"}) >= MATCH_MIN
    assert match_score(want(), {"artistName": "Nubya Garcia", "name": "Solstice (Radio Edit)"}) < MATCH_MIN
    assert match_score(want(), {"artistName": "Nubya Garcia", "name": "Solstice (Remastered 2025)"}) < MATCH_MIN


def test_requested_remix_missing_is_held_not_swapped():  # Rhythm Lab: the remix is the record
    w = Extracted("track", "Little Dragon", "Klapp Klapp", "", "", None, "Swindle Remix")
    assert match_score(w, {"artistName": "Little Dragon", "name": "Klapp Klapp"}) < MATCH_MIN
    assert match_score(w, {"artistName": "Little Dragon", "name": "Klapp Klapp (Swindle Remix)"}) >= MATCH_MIN


def test_dj_mix_versions_lose():
    w = Extracted("track", "Kelis", "Runnin'", "", "", None, "Machinedrum Remix")
    mixed = match_score(w, {"artistName": "Kelis", "name": "Runnin' (Machinedrum Remix) [Mixed]"})
    plain = match_score(w, {"artistName": "Kelis", "name": "Runnin' (Machinedrum Remix)"})
    assert plain > mixed and mixed < MATCH_MIN
