using Godot;

/// <summary>
/// Placeholder for the weather overlay script.
///
/// <c>scene/weather.tscn</c> references <c>res://script/Weather.cs</c>, but
/// upstream never committed the file, so every headless import and export logs
/// "Cannot load C# script file 'res://script/Weather.cs'". Nothing in the game
/// ever instantiates that scene (the game drives weather through
/// <c>Wa2EngineMain.WeatherParticles</c> instead), so an empty Node2D script is
/// enough to keep the project clean.
/// </summary>
public partial class Weather : Node2D
{
	public override void _Ready()
	{
		Hide();
	}
}
