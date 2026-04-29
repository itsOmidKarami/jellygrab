using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;

namespace Jellyfin.Plugin.JellyGrab;

[ApiController]
[Route("JellyGrab")]
public class JellyGrabController : ControllerBase
{
    private readonly IHttpClientFactory _httpClientFactory;

    public JellyGrabController(IHttpClientFactory httpClientFactory)
    {
        _httpClientFactory = httpClientFactory;
    }

    [HttpGet("inject.js")]
    [Produces("application/javascript")]
    public ActionResult GetInjectJs()
    {
        var stream = GetType().Assembly.GetManifestResourceStream(
            "Jellyfin.Plugin.JellyGrab.Web.inject.js");
        if (stream is null)
        {
            return NotFound();
        }
        return File(stream, "application/javascript");
    }

    // Catch-all reverse proxy for the sidecar API. Browser hits
    // /JellyGrab/api/<path> on Jellyfin; we forward to {SidecarUrl}/api/<path>
    // over the internal Docker network and stream the response back.
    [Route("api/{**path}")]
    [AcceptVerbs("GET", "POST", "PUT", "DELETE", "PATCH")]
    public async Task<IActionResult> ProxyApi(string path, CancellationToken ct)
    {
        var config = Plugin.Instance?.Configuration;
        var sidecarBase = config?.SidecarUrl?.TrimEnd('/');
        if (string.IsNullOrWhiteSpace(sidecarBase))
        {
            return Problem(
                statusCode: (int)HttpStatusCode.BadGateway,
                title: "SidecarUrl is not configured");
        }

        var targetUrl = $"{sidecarBase}/api/{path ?? string.Empty}{Request.QueryString.Value}";
        using var upstream = new HttpRequestMessage(new HttpMethod(Request.Method), targetUrl);

        if (HttpMethods.IsPost(Request.Method) || HttpMethods.IsPut(Request.Method) || HttpMethods.IsPatch(Request.Method))
        {
            upstream.Content = new StreamContent(Request.Body);
            if (Request.ContentType is { } ct0)
            {
                upstream.Content.Headers.TryAddWithoutValidation("Content-Type", ct0);
            }
        }

        var client = _httpClientFactory.CreateClient("JellyGrab");

        HttpResponseMessage response;
        try
        {
            response = await client.SendAsync(upstream, HttpCompletionOption.ResponseHeadersRead, ct);
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException)
        {
            Response.StatusCode = (int)HttpStatusCode.BadGateway;
            Response.ContentType = "application/json";
            await Response.WriteAsync($"{{\"error\":\"sidecar unreachable: {WebUtility.HtmlEncode(ex.Message)}\"}}", ct);
            return new EmptyResult();
        }

        try
        {
            Response.StatusCode = (int)response.StatusCode;
            if (response.Content.Headers.ContentType is { } ctHeader)
            {
                Response.ContentType = ctHeader.ToString();
            }

            await using var upstreamStream = await response.Content.ReadAsStreamAsync(ct);
            await upstreamStream.CopyToAsync(Response.Body, ct);
            return new EmptyResult();
        }
        finally
        {
            response.Dispose();
        }
    }
}
