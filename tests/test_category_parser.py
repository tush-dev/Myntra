from pathlib import Path

from app.scrapers.parsers import parse_category_ads


def test_sponsored_result_ordering_and_first_three_rule() -> None:
    html = Path("tests/fixtures/category_page.html").read_text(encoding="utf-8")
    ads = parse_category_ads(html)
    assert [ad.title for ad in ads] == ["Ad One", "Ad Two", "Ad Three"]
    assert ads[0].position == 1
    assert ads[1].url == "https://www.myntra.com/tshirts/2"


def test_fewer_than_three_sponsored_results() -> None:
    html = '<script>window.__myx = {"searchData":{"results":{"plaProducts":[{"isPLA":true,"productName":"Only","price":1}]}}};</script>'
    ads = parse_category_ads(html)
    assert len(ads) == 1


def test_no_sponsored_results_and_malformed_html() -> None:
    assert parse_category_ads('<script>window.__myx = {"searchData":{"results":{"plaProducts":[]}}};</script>') == []
    assert parse_category_ads("<html>not json</html>") == []

