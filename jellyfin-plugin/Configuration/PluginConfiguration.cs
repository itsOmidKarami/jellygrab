using MediaBrowser.Model.Plugins;

namespace Jellyfin.Plugin.JellyGrab.Configuration;

public class PluginConfiguration : BasePluginConfiguration
{
    public PluginConfiguration()
    {
        SidecarUrl = "http://localhost:8765";
    }

    /// <summary>The base URL of the JellyGrab sidecar (FastAPI service).</summary>
    public string SidecarUrl { get; set; }
}
