from smartcrypto.app import session


def test_page_options_include_expected_pages() -> None:
    assert session.PAGE_OPTIONS == [
        "Resumo",
        "Mercado",
        "Operações",
        "Configuração",
        "NTFY",
        "Proteção",
        "DB",
        "IA & Rollout",
    ]


def test_auto_refresh_pages_cover_operational_tabs() -> None:
    assert {"Resumo", "Mercado", "Operações", "Proteção", "DB"} == session.AUTO_REFRESH_PAGES
