import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from bot import normalize_text, search_roles

SAMPLE_ROLES = [
    {"name": "イビルゲッサー", "name_en": "EvilGuesser", "faction": "インポスター", "category": "キラー", "description": "", "icon_url": "", "wiki_url": ""},
    {"name": "シェリフ", "name_en": "Sheriff", "faction": "クルーメイト", "category": "キラー", "description": "", "icon_url": "", "wiki_url": ""},
    {"name": "アーソニスト", "name_en": "Arsonist", "faction": "ニュートラル", "category": "キラー", "description": "", "icon_url": "", "wiki_url": ""},
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

def test_english_partial():
    results = search_roles(SAMPLE_ROLES, "Evil")
    assert len(results) == 1
    assert results[0]["name"] == "イビルゲッサー"

def test_english_lowercase():
    results = search_roles(SAMPLE_ROLES, "evil")
    assert len(results) == 1
    assert results[0]["name"] == "イビルゲッサー"

def test_no_match():
    results = search_roles(SAMPLE_ROLES, "zzzzz")
    assert len(results) == 0

def test_multiple_match():
    results = search_roles(SAMPLE_ROLES, "r")
    names = [r["name"] for r in results]
    assert "シェリフ" in names
    assert "アーソニスト" in names
