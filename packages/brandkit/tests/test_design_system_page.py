"""T41: the rendered design-system page carries an "At a glance" block -- colours by role with
their plain names, and the approved look when `assets/approved-look-*.png` exists. Temp copy
of the demo kit; the shipped kit is never written."""
import shutil

from brandkit import design_system

from .conftest import DEMO_KIT_DIR


def test_render_shows_named_colours_and_the_approved_look(tmp_path):
    folder = tmp_path / "kit" / "design-system"
    shutil.copytree(DEMO_KIT_DIR / "design-system", folder)

    page = design_system.render_html(folder)
    assert "At a glance" in page
    assert 'data-colour-role="primary"' in page and "deep forest green" in page
    assert "approved-look" not in page

    (folder / "assets" / "approved-look-4x5.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    page = design_system.render_html(folder)
    assert '<img class="look" src="assets/approved-look-4x5.png"' in page
    assert not (folder / "index.html").exists()
