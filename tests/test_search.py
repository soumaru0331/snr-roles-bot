import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from bot import normalize_text, search_roles

SAMPLE_ROLES = [
    {"name": "イビルゲッサー", "name_en": "EvilGuesser", "faction": "インポスター", "category": "キラー", "description": "", "icon_url": "", "wiki_url": ""},
    {"name": "シェリフ", "name_en": "Sheriff", "faction": "クルーメイト", "category": "キラー", "description": "", "icon_url": "", "wiki_url": ""},
    {"name": "アーソニスト", "name_en": "Arsonist", "faction": "ニュートラル", "category": "キラー", "description": "", "icon_url": "", "wiki_url": ""},
    {"name": "ディメンションウォーカー", "name_en": "DimensionWalker", "faction": "ニュートラル", "category": "その他", "description": "", "icon_url": "", "wiki_url": ""},
    {"name": "波動砲", "faction": "インポスター", "description": "", "icon_url": "", "wiki_url": ""},
    {"name": "天秤", "faction": "ニュートラル", "description": "", "icon_url": "", "wiki_url": ""},
    {"name": "陰陽師", "faction": "ニュートラル", "description": "", "icon_url": "", "wiki_url": ""},
    {"name": "侍", "faction": "クルーメイト", "description": "", "icon_url": "", "wiki_url": ""},
]

def test_katakana_partial():
    results = search_roles(SAMPLE_ROLES, "イビルゲ")
    assert len(results) == 1
    assert results[0]["name"] == "イビルゲッサー"

def test_hiragana_full():
    results = search_roles(SAMPLE_ROLES, "いびるげっさー")
    assert len(results) == 1
    assert results[0]["name"] == "イビルゲッサー"

def test_hiragana_partial():
    results = search_roles(SAMPLE_ROLES, "いびるげ")
    assert len(results) == 1
    assert results[0]["name"] == "イビルゲッサー"

def test_romaji_partial():
    results = search_roles(SAMPLE_ROLES, "ibiruge")
    assert len(results) == 1
    assert results[0]["name"] == "イビルゲッサー"

def test_romaji_short():
    results = search_roles(SAMPLE_ROLES, "ibi")
    assert len(results) == 1
    assert results[0]["name"] == "イビルゲッサー"

def test_romaji_with_consonant_end():
    # "ibir" → "イビッ" → strip → "イビ" → matches
    results = search_roles(SAMPLE_ROLES, "ibir")
    assert len(results) == 1
    assert results[0]["name"] == "イビルゲッサー"

def test_romaji_with_long_vowel():
    # "arso" → "アッソ" → strip → "アソ" → matches "アーソニスト"
    results = search_roles(SAMPLE_ROLES, "arso")
    assert len(results) == 1
    assert results[0]["name"] == "アーソニスト"

def test_no_match():
    results = search_roles(SAMPLE_ROLES, "zzzzz")
    assert len(results) == 0

def test_multiple_match():
    # "sherifuto" は存在しないが "she" はシェリフにだけ一致
    results = search_roles(SAMPLE_ROLES, "she")
    names = [r["name"] for r in results]
    assert "シェリフ" in names

def test_romaji_mid_consonant():
    # "dim" → 末尾子音'm'を除去 → "di" → "ディ" → ディメンションウォーカーにヒット
    results = search_roles(SAMPLE_ROLES, "dim")
    assert len(results) == 1
    assert results[0]["name"] == "ディメンションウォーカー"

def test_romaji_dimen():
    results = search_roles(SAMPLE_ROLES, "dimen")
    assert len(results) == 1
    assert results[0]["name"] == "ディメンションウォーカー"

def test_kanji_hadou():
    results = search_roles(SAMPLE_ROLES, "hadou")
    assert any(r["name"] == "波動砲" for r in results)

def test_kanji_ten():
    results = search_roles(SAMPLE_ROLES, "ten")
    assert any(r["name"] == "天秤" for r in results)

def test_kanji_inyo():
    results = search_roles(SAMPLE_ROLES, "inyo")
    assert any(r["name"] == "陰陽師" for r in results)

def test_kanji_samurai():
    results = search_roles(SAMPLE_ROLES, "samu")
    assert any(r["name"] == "侍" for r in results)
