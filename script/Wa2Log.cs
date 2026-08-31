using System;
using System.Collections.Generic;
using System.IO;

/// <summary>
/// Diagnostic log written into the app's Documents folder so it can be pulled
/// off the device with the Files app / iTunes file sharing.
///
/// Debugging a sideloaded iOS build is painful because there is no console
/// unless you tether the device to a Mac, so the app writes its own trace to
/// Documents/wa2-log.txt instead.
/// </summary>
public static class Wa2Log
{
	private const int FlushEvery = 40;

	private static string _path;
	private static readonly List<string> _pending = new();
	private static int _dropped;

	public static void Init(string directory)
	{
		try
		{
			Directory.CreateDirectory(directory);
			_path = Path.Combine(directory, "wa2-log.txt");
			File.WriteAllText(_path, string.Empty);
		}
		catch (Exception)
		{
			_path = null;
		}
	}

	public static void Write(string line)
	{
		if (string.IsNullOrEmpty(_path))
		{
			return;
		}

		lock (_pending)
		{
			_pending.Add(line);
			if (_pending.Count < FlushEvery)
			{
				return;
			}
		}

		Flush();
	}

	public static void Flush()
	{
		if (string.IsNullOrEmpty(_path))
		{
			return;
		}

		List<string> batch;
		lock (_pending)
		{
			if (_pending.Count == 0)
			{
				return;
			}
			batch = new List<string>(_pending);
			_pending.Clear();
		}

		try
		{
			File.AppendAllLines(_path, batch);
		}
		catch (Exception)
		{
			_dropped += batch.Count;
		}
	}

	public static string Summary()
	{
		return _dropped == 0 ? "ok" : "dropped=" + _dropped;
	}
}
