using System;
using System.Collections.Generic;
using Jellyfin.Plugin.JellyNama.Configuration;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Common.Plugins;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;

namespace Jellyfin.Plugin.JellyNama;

public class Plugin : BasePlugin<PluginConfiguration>, IHasWebPages
{
    public Plugin(IApplicationPaths applicationPaths, IXmlSerializer xmlSerializer)
        : base(applicationPaths, xmlSerializer)
    {
        Instance = this;
    }

    public override string Name => "JellyNama";

    public override Guid Id => Guid.Parse("3a8d4f2e-7c1b-4e6a-9f8d-2b5e1a9c4d7e");

    public override string Description =>
        "Search 30nama.com for Persian movies/series and download them directly into your Jellyfin library via a sidecar service.";

    public static Plugin? Instance { get; private set; }

    public IEnumerable<PluginPageInfo> GetPages() => new[]
    {
        new PluginPageInfo
        {
            Name = Name,
            EmbeddedResourcePath = $"{GetType().Namespace}.Configuration.configPage.html",
            DisplayName = Name,
            EnableInMainMenu = true,
            MenuIcon = "cloud_download",
        },
        new PluginPageInfo
        {
            Name = "JellyNamaJs",
            EmbeddedResourcePath = $"{GetType().Namespace}.Web.jellynama.js",
        },
    };
}
