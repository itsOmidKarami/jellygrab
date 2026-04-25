using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using MediaBrowser.Common.Configuration;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.JellyNama;

/// <summary>
/// Patches Jellyfin web's index.html to load JellyNama's inject.js into every page,
/// so we can augment the built-in search view. Same pattern used by Jellyscrub etc.
/// </summary>
public class InjectScriptService : IHostedService
{
    private const string Marker = "<!-- JellyNamaInject -->";
    private const string ScriptTag = "<script defer src=\"/JellyNama/inject.js\"></script>";

    private readonly IApplicationPaths _appPaths;
    private readonly ILogger<InjectScriptService> _logger;

    public InjectScriptService(IApplicationPaths appPaths, ILogger<InjectScriptService> logger)
    {
        _appPaths = appPaths;
        _logger = logger;
    }

    public Task StartAsync(CancellationToken cancellationToken)
    {
        try
        {
            var indexPath = Path.Combine(_appPaths.WebPath, "index.html");
            if (!File.Exists(indexPath))
            {
                _logger.LogWarning("JellyNama: index.html not found at {Path}", indexPath);
                return Task.CompletedTask;
            }

            var html = File.ReadAllText(indexPath);
            if (html.Contains(Marker, StringComparison.Ordinal))
            {
                return Task.CompletedTask;
            }

            var bodyEnd = html.LastIndexOf("</body>", StringComparison.OrdinalIgnoreCase);
            if (bodyEnd < 0)
            {
                _logger.LogWarning("JellyNama: </body> not found in index.html, skipping inject");
                return Task.CompletedTask;
            }

            var patched = html.Insert(bodyEnd, Marker + ScriptTag);
            File.WriteAllText(indexPath, patched);
            _logger.LogInformation("JellyNama: injected inject.js into {Path}", indexPath);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "JellyNama: failed to inject script into index.html");
        }

        return Task.CompletedTask;
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;
}
