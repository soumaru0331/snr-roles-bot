import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bot import parse_role_list, parse_role_detail

# 実際のwikiのHTML構造に基づいたサンプル
SAMPLE_LIST_HTML = """
<html><body>
<a href="Impostor/%E3%82%A4%E3%83%93%E3%83%AB%E3%82%B2%E3%83%83%E3%82%B5%E3%83%BC.md">イビルゲッサー</a>
<a href="Crewmate/%E3%82%B7%E3%82%A7%E3%83%AA%E3%83%95.md">シェリフ</a>
<a href="Neutral/%E3%82%A2%E3%83%BC%E3%82%BD%E3%83%8B%E3%82%B9%E3%83%88.md">アーソニスト</a>
<a href="Ghost/%E3%82%B4%E3%83%BC%E3%82%B9%E3%83%88.md">ゴースト</a>
<a href="Modifier/%E3%83%A2%E3%83%87.md">モデ</a>
<a href="/home">ホーム</a>
<a href="#section">目次</a>
</body></html>
"""

SAMPLE_ROLE_HTML = """
<html><body>
<div class="container">
<h3>イビルゲッサー</h3>
<h3>陣営</h3>
インポスター陣営
<h3>役職説明</h3>
会議中に役職を推測してキルする能力を持つ。
外れると自分が死亡する。
<h3>ゲーム設定</h3>
最大回数などの設定がある。
</div>
</body></html>
"""

SAMPLE_ROLE_HTML_NO_SETTINGS = """
<html><body>
<div class="container">
<h3>テスト役職</h3>
<h3>役職説明</h3>
シンプルな説明テキスト。
</div>
</body></html>
"""


def test_parse_role_list_returns_roles():
    roles = parse_role_list(SAMPLE_LIST_HTML)
    assert len(roles) == 5


def test_parse_role_list_impostor_faction():
    roles = parse_role_list(SAMPLE_LIST_HTML)
    evil = next(r for r in roles if r["name"] == "イビルゲッサー")
    assert evil["faction"] == "インポスター"


def test_parse_role_list_crewmate_faction():
    roles = parse_role_list(SAMPLE_LIST_HTML)
    sheriff = next(r for r in roles if r["name"] == "シェリフ")
    assert sheriff["faction"] == "クルーメイト"


def test_parse_role_list_neutral_faction():
    roles = parse_role_list(SAMPLE_LIST_HTML)
    arsonist = next(r for r in roles if r["name"] == "アーソニスト")
    assert arsonist["faction"] == "ニュートラル"


def test_parse_role_list_wiki_url():
    roles = parse_role_list(SAMPLE_LIST_HTML)
    evil = next(r for r in roles if r["name"] == "イビルゲッサー")
    assert evil["wiki_url"].startswith("https://wiki.supernewroles.com")
    assert evil["wiki_url"].endswith("イビルゲッサー") or "Impostor" in evil["wiki_url"]


def test_parse_role_list_ignores_non_md_links():
    roles = parse_role_list(SAMPLE_LIST_HTML)
    names = [r["name"] for r in roles]
    assert "ホーム" not in names
    assert "目次" not in names


def test_parse_role_detail_description():
    desc, icon_url = parse_role_detail(SAMPLE_ROLE_HTML)
    assert "推測" in desc or "会議" in desc


def test_parse_role_detail_no_icon():
    desc, icon_url = parse_role_detail(SAMPLE_ROLE_HTML)
    assert icon_url == ""


def test_parse_role_detail_no_game_settings_in_desc():
    desc, icon_url = parse_role_detail(SAMPLE_ROLE_HTML)
    assert "最大回数" not in desc


def test_parse_role_detail_no_settings_section():
    desc, icon_url = parse_role_detail(SAMPLE_ROLE_HTML_NO_SETTINGS)
    assert "シンプルな説明" in desc
