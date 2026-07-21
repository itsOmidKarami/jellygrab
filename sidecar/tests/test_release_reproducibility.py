from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).parents[2]


def test_plugin_builds_exclude_the_git_revision():
    project = ElementTree.parse(ROOT / "jellyfin-plugin/Jellyfin.Plugin.JellyGrab.csproj")

    values = project.findall(".//IncludeSourceRevisionInInformationalVersion")

    assert [value.text for value in values] == ["false"]


def test_release_manifest_timestamp_comes_from_the_pull_request():
    workflow = (ROOT / ".github/workflows/update-release-manifest.yml").read_text()

    assert 'TIMESTAMP="${{ github.event.pull_request.created_at }}"' in workflow
    assert "date -u" not in workflow
