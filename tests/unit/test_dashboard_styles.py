from smartcrypto.app import styles


def test_dashboard_css_forces_full_width_layout() -> None:
    css = styles.base_css()
    assert 'stMainBlockContainer' in css
    assert 'max-width: none' in css
    assert 'width: 100%' in css
