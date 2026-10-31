import re
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).parents[2]


def test_plugin_builds_exclude_git_dependent_metadata():
    project = ElementTree.parse(ROOT / "jellyfin-plugin/Jellyfin.Plugin.JellyGrab.csproj")

    revision_settings = project.findall(".//IncludeSourceRevisionInInformationalVersion")
    debug_settings = project.findall(".//DebugType")

    assert [setting.text for setting in revision_settings] == ["false"]
    assert [setting.text for setting in debug_settings] == ["none"]
    assert [setting.get("Condition") for setting in debug_settings] == [
        "'$(Configuration)' == 'Release'"
    ]


def test_release_manifest_timestamp_comes_from_the_pull_request():
    workflow = (ROOT / ".github/workflows/update-release-manifest.yml").read_text()

    assert 'TIMESTAMP="${{ github.event.pull_request.created_at }}"' in workflow
    assert "date -u" not in workflow


def test_plugin_abi_matrices_stay_in_sync():
    version = re.compile(r'jellyfin: "([\d.]+)"')
    build = version.findall((ROOT / ".github/workflows/build-plugin.yml").read_text())
    release = version.findall((ROOT / ".github/workflows/release-plugin.yml").read_text())
    manifest_workflow = (ROOT / ".github/workflows/update-release-manifest.yml").read_text()

    assert build == release == ["10.10.7", "10.11.8", "12.0.0"]
    for jellyfin in build:
        assert f"scripts/package-plugin.sh {jellyfin} " in manifest_workflow
        assert f"jellygrab-jellyfin-{jellyfin}.zip" in manifest_workflow
