from brewq import render
from brewq.columns import resolve
from brewq.model import Package


def package(
    name,
    type_,
    version,
    description,
    installs,
    installed=False,
    deprecated=False,
    disabled=False,
):
    return Package(
        name=name,
        type=type_,
        description=description,
        url=f"https://example.com/{name}",
        version=version,
        installs_30d=installs,
        installs_365d=installs * 10,
        installed=installed,
        deprecated=deprecated,
        disabled=disabled,
    )


pairs = [
    # Shortlist: related/same-family colors that looked closest so far.
    ("Soft Amber / Apricot", 179, 215),
    ("Seafoam / Pale Aqua", 115, 116),
    ("Lavender / Periwinkle", 183, 189),
    ("Periwinkle / Pale Blue", 147, 153),
    # Baseline and exploratory alternates.
    ("Current: Lavender / Seafoam", 183, 115),
    ("Ice Blue / Soft Cyan", 117, 116),
    ("Sky Blue / Bright Cyan", 75, 81),
    ("Violet / Light Violet", 141, 147),
    ("Mint / Seafoam", 121, 115),
]

pkgs = [
    package(
        "ripgrep",
        "formula",
        "14.1.1",
        "Search tool like grep and The Silver Searcher",
        965432,
    ),
    package(
        "visual-studio-code",
        "cask",
        "1.101.0",
        "Open-source code editor",
        812345,
    ),
    package(
        "postgresql@17",
        "formula",
        "17.5",
        "Object-relational database system",
        412345,
        installed=True,
    ),
    package(
        "google-chrome",
        "cask",
        "137.0.0",
        "Web browser",
        701234,
        installed=True,
    ),
    package(
        "legacy-formula",
        "formula",
        "1.0",
        "Deprecated formula example",
        1234,
        deprecated=True,
    ),
    package(
        "disabled-cask",
        "cask",
        "2.0",
        "Disabled cask example",
        5678,
        disabled=True,
    ),
]

cols = resolve(
    "name,version,installs,description", ["name", "version", "installs", "description"]
)

for label, formula, cask in pairs:
    render._COLOR_FORMULA = f"\033[38;5;{formula}m"
    render._COLOR_CASK = f"\033[38;5;{cask}m"
    print(f"\n{label}  formula={formula} cask={cask}")
    render.render_table(pkgs, cols)
