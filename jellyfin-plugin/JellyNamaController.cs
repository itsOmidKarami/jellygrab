using System.IO;
using System.Net.Mime;
using Microsoft.AspNetCore.Mvc;

namespace Jellyfin.Plugin.JellyNama;

[ApiController]
[Route("JellyNama")]
public class JellyNamaController : ControllerBase
{
    [HttpGet("inject.js")]
    [Produces("application/javascript")]
    public ActionResult GetInjectJs()
    {
        var stream = GetType().Assembly.GetManifestResourceStream(
            "Jellyfin.Plugin.JellyNama.Web.inject.js");
        if (stream is null)
        {
            return NotFound();
        }
        return File(stream, "application/javascript");
    }
}
