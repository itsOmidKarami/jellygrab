using MediaBrowser.Model.Plugins;

namespace Jellyfin.Plugin.JellyGrab.Configuration;

public class PluginConfiguration : BasePluginConfiguration
{
    public PluginConfiguration()
    {
        // Matches the sidecar's service name in the shipped docker-compose.yml.
        // Bare-metal / non-Docker installs should override this in the plugin config UI.
        SidecarUrl = "http://jellygrab:8765";
    }

    /// <summary>The base URL of the JellyGrab sidecar (FastAPI service).</summary>
    public string SidecarUrl { get; set; }
}
