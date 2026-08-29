using Godot;

/// <summary>
/// Minimal stand-in for the gde_gozen <c>VideoPlayback</c> node.
///
/// Why this file exists:
/// <para>
/// The upstream project depends on the gde_gozen addon (FFmpeg based video
/// playback), but <c>addons/gde_gozen/</c> is listed in .gitignore, so the
/// sources are never published. <c>script/Wa2EngineMain.cs</c> references the
/// <c>VideoPlayback</c> type directly and <c>main.tscn</c> attaches it to the
/// <c>VideoStreamPlayer</c> node, so a fresh clone does not compile at all
/// (CS0246: The type or namespace name 'VideoPlayback' could not be found)
/// and the exported .pck ends up with no game code.
/// </para>
/// <para>
/// The real addon is a GDExtension with native FFmpeg binaries. It has no iOS
/// build, and it cannot work inside the iOS sandbox anyway. So we ship this
/// API-compatible stub instead: the game compiles, and movie playback becomes
/// a no-op. <c>Wa2EngineMain.GetVideoPath()</c> additionally reports "no video
/// file" on iOS, so the engine takes its normal "movie missing" path and skips
/// straight past the OP/LOGO movies instead of waiting on a player that never
/// produces a frame.
/// </para>
/// </summary>
public partial class VideoPlayback : Control
{
	[Signal]
	public delegate void VideoEndedEventHandler();

	[Signal]
	public delegate void VideoLoadedEventHandler();

	/// <summary>Kept so <c>main.tscn</c> can still assign the property.</summary>
	[Export]
	public bool AudioSpeedToSync { get; set; } = true;

	/// <summary>True only while a movie is actually rendering (never, here).</summary>
	public bool IsPlaying { get; private set; }

	/// <summary>Frame counter; 0 means "nothing was decoded".</summary>
	public int CurrentFrame { get; private set; }

	public override void _Ready()
	{
		Hide();
	}

	public void SetVideoPath(string path)
	{
		CurrentFrame = 0;
		IsPlaying = false;

		// Emit on the next idle frame: Wa2EngineMain.PlayMovie() calls
		// SetVideoPath() and then awaits VideoLoaded, so the signal has to fire
		// *after* the caller has connected.
		Callable.From(EmitLoaded).CallDeferred();
	}

	/// <summary>
	/// Always returns a small positive duration. Wa2EngineMain feeds this into
	/// Wa2Timer.Start(), and a 0 there makes the timer compute 0/0 = NaN, which
	/// never reports "done" and would hang the script forever.
	/// </summary>
	public double GetVideoLength()
	{
		return 0.2;
	}

	public void Play()
	{
		CurrentFrame = 1;
		IsPlaying = false;
		Callable.From(EmitEnded).CallDeferred();
	}

	public void Close()
	{
		IsPlaying = false;
		CurrentFrame = 0;
		Hide();
	}

	private void EmitLoaded()
	{
		EmitSignal(SignalName.VideoLoaded);
	}

	private void EmitEnded()
	{
		IsPlaying = false;
		EmitSignal(SignalName.VideoEnded);
	}
}
