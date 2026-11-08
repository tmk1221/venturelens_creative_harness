from brandkit.style_axes import axis_keys, load_style_axes


def test_loads_house_style_axes():
    data = load_style_axes()
    axes = data["axes"]
    for key in ("colour", "light", "lens", "composition", "texture_medium",
                "production_design", "people"):
        assert key in axes
        assert axes[key]["explanation"]
        assert 3 <= len(axes[key]["examples"]) <= 5


def test_axis_keys_matches_axes_mapping():
    data = load_style_axes()
    assert axis_keys(data) == list(data["axes"].keys())
