using System;
using System.Collections.Generic;
using Jellyfin.Plugin.JellyGrab.Configuration;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Common.Plugins;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;

namespace Jellyfin.Plugin.JellyGrab;

public class Plugin : BasePlugin<PluginConfiguration>, IHasWebPages
{
    public Plugin(IApplicationPaths applicationPaths, IXmlSerializer xmlSerializer)
        : base(applicationPaths, xmlSerializer)
    {
        Instance = this;
    }

    public override string Name => "JellyGrab";

    public override Guid Id => Guid.Parse("826a65d9-ec1d-4ff7-b4b6-d5ee1dd199d2");

    public override string Description =>
        "A Jellyfin companion plugin that adds a downloader page wired to the JellyGrab sidecar service.";

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
            Name = "JellyGrabJs",
            EmbeddedResourcePath = $"{GetType().Namespace}.Web.jellygrab.js",
        },
    };
}
